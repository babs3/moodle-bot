from time import sleep
from flask import request
import random
from datetime import datetime, timezone, timedelta
import json
from flask_backend.utils import *

@app.route('/')
def index():
    return "Flask está a correr na porta 8080!"

@app.route('/chat', methods=['POST'])
def chat():    
    data = request.json
    app.logger.info(f"Received data: {data}")
    moodle_id = data.get('user_id') # Recebe o "2" do teu Javascript
    print(f"Received message from user_id: {moodle_id}")
    app.logger.info(f"Received userID: {moodle_id}")
    user_message = data.get('message')

    # Busca os dados reais no Moodle
    info_utilizador = get_moodle_user_data(moodle_id)
    
    # Aqui podes pôr a tua lógica ou chamar o Rasa via REST
    user_email = info_utilizador.get("email") if info_utilizador else "EMAIL@EXAMPLE.COM"
    username = info_utilizador.get("nome") if info_utilizador else "NOME_"

    url = "http://rasa:5005/webhooks/rest/webhook"
    current_time = datetime.now(timezone.utc).isoformat() #datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "sender": user_email,
        "message": user_message, #user_input,
        "metadata": {"username": username,"input_time":current_time, "selected_class_name": "class_name", "selected_class_number": "3", "selected_group":"01", "teacher_question": ""}
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        messages = response.json()

        bot_reply = ""
        buttons = []

        for message in messages:
            if "text" in message:
                bot_reply += f"\n\n {message['text']}"
        #    if "buttons" in message:
        #        buttons = message["buttons"]

        #return bot_reply.strip(), buttons  # Return both text and buttons
        return jsonify([{"text": f"{bot_reply.strip()}"}])

    except requests.RequestException as e:
        print(f"⚠️ Error connecting to Rasa: {e}")
        return None
    

@app.route("/api/save_reset_token", methods=["POST"])
def save_reset_token():
    data = request.json
    email = data.get("email")
    token = data.get("token")
    
    expiry = datetime.now(timezone.utc) + timedelta(hours=0, minutes=30)  # Token valid for 30 minutes
    
    if not email or not token or not expiry:
        return jsonify({"error": "Missing fields"}), 400
    entry = PasswordResetTokens(email=email, token=token, expiry=expiry)
    db.session.add(entry)
    db.session.commit()
    return jsonify({"message": "Reset token saved successfully"}), 200

@app.route("/api/send_password_reset_email/<email>", methods=["POST"])
def send_password_reset_email(email):
    # get token from database
    token_entry = PasswordResetTokens.query.filter_by(email=email).order_by(PasswordResetTokens.expiry.desc()).first()
    if not token_entry:
        return jsonify({"error": "No valid reset token found"}), 404
    token = token_entry.token
    reset_link = f"http://{DOMAIN}/reset_password?token={token}"
    send_reset_password_email(reset_link, email)
    

@app.route("/api/fetch_reset_token/<token>", methods=["GET"])
def fetch_reset_token(token):
    token_entry = PasswordResetTokens.query.filter_by(token=token).first()
    if not token_entry:
        return jsonify({"error": "Token not found"}), 404
    if token_entry.expiry < datetime.now(timezone.utc):
        return jsonify({"error": "Token has expired"}), 400
    
    return jsonify({"email": token_entry.email}), 200

@app.route("/api/delete_reset_token/<token>", methods=["DELETE"])
def delete_reset_token(token):
    token_entry = PasswordResetTokens.query.filter_by(token=token).first()
    if not token_entry:
        return jsonify({"error": "Token not found"}), 404
    db.session.delete(token_entry)
    db.session.commit()
    return jsonify({"message": "Token deleted successfully"}), 200

@app.route("/api/classes", methods=["GET"])
def get_classes():
    classes = Classes.query.all()
    return jsonify([{"id": c.id, "code": c.code, "number": c.number, "group": c.group, "course": c.course} for c in classes])

@app.route("/api/teacher_classes/<email>", methods=["GET"])
def get_teacher_classes(email):
    teacher = Teacher.query.join(Users).filter(Users.email == email).first()
    if not teacher:
        return jsonify({"error": "Teacher not found"}), 404
    
    teacher_classes = teacher.classes.split(",")
    
    # Query Classes table for matching codes
    classes = Classes.query.all()
    filtered_classes = [cls for cls in classes if str(cls.id) in teacher_classes]
    
    return jsonify([{"id": c.id, "code": c.code, "number": c.number, "group": c.group} for c in filtered_classes])

@app.route("/api/class_progress/<class_id>", methods=["GET"])
def get_class_progress(class_id):
    progress = UserProgress.query.filter(UserProgress.class_id == class_id).all()
    return jsonify([{"user_id": p.user_id, "class_id":class_id, "question": p.question, "response": p.response, "topic_id": p.topic_id, "pdfs": p.pdfs, "timestamp": p.timestamp} for p in progress])

@app.route("/api/progress", methods=["GET"])
def get_progress():
    progress = UserProgress.query.all()
    return jsonify([{"user_id": p.user_id, "class_id":None, "question": p.question, "response": p.response, "topic_id": p.topic_id, "pdfs": p.pdfs, "timestamp": p.timestamp} for p in progress])

@app.route("/api/get_user_progress/<user_id>", methods=["GET"])
def get_user_progress(user_id):
    progress = UserProgress.query.filter(UserProgress.user_id == int(user_id)).all()
    return jsonify([{"class_id": p.class_id, "question": p.question, "response": p.response, "topic_id": p.topic_id, "pdfs": p.pdfs, "timestamp": p.timestamp} for p in progress])

@app.route("/api/save_user_progress/<user_id>", methods=["POST"])
def save_user_progress(user_id):
    data = request.json
    topic_name = data["topic"]

    if topic_name is not None:
        topic_obj = Topics.query.filter(Topics.topic == topic_name).first()
        if topic_obj:
            topic_id = topic_obj.id
        else:
            # create new topic
            new_topic = Topics(topic=topic_name)
            db.session.add(new_topic)
            db.session.commit()
            topic_id = new_topic.id  # we can get the id directly from the object
    else:
        topic_id = None

    progress = UserProgress(
        user_id=user_id,
        class_id=data["class_id"],
        question=data["question"],
        response=data["response"],
        topic_id=topic_id,
        pdfs=data["pdfs"],
        response_time=data["response_time"],
        timestamp=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    db.session.add(progress)
    db.session.commit()

    return jsonify({"message": "Progress saved"})

@app.route("/api/get_topic_id_to_name_mapping", methods=["GET"])
def get_topic_id_to_name_mapping():
    """
    Returns a dictionary mapping topic_id -> topic_name.
    Example: {1: "linear algebra", 2: "machine learning"}
    """
    topics = Topics.query.all()
    return jsonify({topic.id: topic.topic for topic in topics})


@app.route("/api/get_student/<email>", methods=["GET"])
def get_student(email):
    student = Student.query.join(Users).filter(Users.email == email).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404
    return jsonify({"id":str(student.id), "user_id": student.user_id, "student_up": student.up, "course": student.course, "year": student.year, "class_id": student.class_id})

@app.route("/api/get_teacher/<email>", methods=["GET"])
def get_teacher(email):
    teacher = Teacher.query.join(Users).filter(Users.email == email).first()
    if not teacher:
        return jsonify({"error": "Teacher not found"}), 404
    return jsonify({"id":str(teacher.id), "user_id": teacher.user_id, "classes": teacher.classes, "is_approved": teacher.is_approved})

@app.route("/api/get_other/<email>", methods=["GET"])
def get_other(email):
    other = Other.query.join(Users).filter(Users.email == email).first()
    if not other:
        return jsonify({"error": "Other not found"}), 404
    return jsonify({"id":str(other.id), "user_id": other.user_id, "role": other.role, "job": other.job, "company": other.company, "graduation_year": other.graduation_year, "graduation_area": other.graduation_area, "class_": other.class_})

@app.route("/api/get_user/<email>", methods=["GET"])
def get_user(email):
    user = Users.query.filter(Users.email == email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"id": user.id, "name": user.name, "role": user.role, "email": user.email, "otp": user.otp, "is_verified": user.is_verified, "form_filled": user.form_filled})

@app.route('/api/topics', methods=['GET'])
def get_topics():
    topics = Topics.query.all()
    return jsonify([{"id": t.id, "topic": t.topic} for t in topics])

@app.route('/api/save_topic/<topic>', methods=['POST'])
def save_topic(topic):
    topic = Topics(topic=topic)
    db.session.add(topic)
    db.session.commit()
    return jsonify({"message": "Topic saved"})

@app.route('/api/get_topic/<topic_id>', methods=['GET'])
def get_topic(topic_id):
    topic_id == int(topic_id)
    topic = Topics.query.filter(Topics.id == topic_id).first()
    if not topic:
        return jsonify({"error": "Topic not found"}), 404
    return jsonify({"id": topic.id, "topic": topic.topic})

@app.route("/api/message_history/<user_id>", methods=["GET"])
def get_message_history(user_id):
    history = MessageHistory.query.filter(MessageHistory.user_id == user_id).all()
    return jsonify([{"question": h.question, "response": h.response, "timestamp": h.timestamp} for h in history])

@app.route("/api/authenticate", methods=["POST"])
def authenticate():
    data = request.json
    user = Users.query.filter(Users.email == data["email"], Users.password == data["password"]).first()
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401
    return jsonify({"id": user.id, "name": user.name, "role": user.role, "email": user.email, "otp": user.otp, "is_verified": user.is_verified})

@app.route("/api/save_message_history/<user_id>", methods=["POST"])
def save_message_history(user_id):
    data = request.json
    history = MessageHistory(user_id=user_id, question=data["question"], response=data["response"], timestamp=datetime.now(timezone.utc)+ timedelta(hours=1))  # now properly parsed
    db.session.add(history)
    db.session.commit()
    return jsonify({"message": "History saved"})

@app.route("/api/register_student", methods=["POST"])
def register_student():
    data = request.json
    
    # Generate confirmation otp
    confirmation_otp = f"{random.randint(100000, 999999)}"
    # Store user with `is_verified=False`
    user = Users(name=data["name"], role="Student", email=data["email"], password=data["password"], otp=confirmation_otp)
    db.session.add(user)
    db.session.commit()
    
    if data["class_id"] == "No Class":
        data["class_id"] = None
    student = Student(user_id=user.id, up=int(data["up"]), course=data["course"], year=data["year"], class_id=data["class_id"])
    db.session.add(student)
    db.session.commit()
    
    return send_confirmation_email(data["email"], confirmation_otp)


@app.route("/confirm/<otp>", methods=["GET"]) # TODO check if this is used
def confirm_email(otp):
    user = Users.query.filter_by(otp=otp).first()
    if not user:
        return "<h2>❌ Invalid or expired otp</h2>", 400

    try:
        user.is_verified = True
        db.session.commit()
        return "<h2>✅ Email confirmed successfully! You can now log in.</h2>", 200
    except Exception as e:
        db.session.rollback()
        return f"<h2>❌ Database Error: {str(e)}</h2>", 500

@app.route("/api/verify_user", methods=["POST"])
def verify_user():
    data = request.json
    user = Users.query.filter_by(email=data["email"]).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    if str(user.otp) == data["verification_code"]:
        user.is_verified = "True"
        db.session.commit()
        return jsonify({"message": "User verified successfully"}), 200
    else:
        return jsonify({"error": "Invalid verification code"}), 400


@app.route("/api/register_teacher", methods=["POST"])
def register_teacher():
    data = request.json
    
    # Generate confirmation otp
    confirmation_otp = f"{random.randint(100000, 999999)}"
    # Store user with `is_verified=False`
    user = Users(name=data["name"], role="Teacher", email=data["email"], password=data["password"], otp=confirmation_otp)
    db.session.add(user)
    db.session.commit()

    classes = ",".join(data["classes"].split(","))

    teacher = Teacher(user_id=user.id, classes=classes)
    db.session.add(teacher)
    db.session.commit()
    
    send_confirmation_email(data["email"], confirmation_otp)
    
    # Send approval email
    return send_email_to_admin_about_teacher_request(user)

@app.route("/api/register_other", methods=["POST"])
def register_other():
    data = request.json
    
    # Generate confirmation otp
    confirmation_otp = f"{random.randint(100000, 999999)}"
    # Store user with `is_verified=False`
    user = Users(name=data["name"], role="Other", email=data["email"], password=data["password"], otp=confirmation_otp)
    db.session.add(user)
    db.session.commit()

    other = Other(user_id=user.id, role=data["role"], job=data["job"], company=data["company"], graduation_year=data["graduation_year"], graduation_area=data["graduation_area"])
    db.session.add(other)
    db.session.commit()
    
    return send_confirmation_email(data["email"], confirmation_otp)

@app.route("/api/send_confirmation_email/<email>", methods=["POST"]) #setOTP()
def send_confirmation_email_route(email):
    user = Users.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Generate new OTP
    confirmation_otp = f"{random.randint(100000, 999999)}"
    user.otp = confirmation_otp
    db.session.commit()

    # Send confirmation email
    return send_confirmation_email(email, confirmation_otp)

@app.route('/api/reset_password', methods=['POST'])
def reset_password():
    data = request.json
    email = data.get("email")
    new_password = data.get("new_password")
    user = Users.query.filter_by(email=email).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    user.password = hash_password(new_password)
    db.session.commit() 
    return jsonify({"success": True, "message": "✅ Password updated successfully!"}), 200

@app.route("/api/has_filled_form/<email>", methods=["GET"])
def has_filled_form_route(email):
    data = request.json
    
    spreadsheet_id = data.get("spreadsheet_id")
    update_db = data.get("update_db", False)
    
    if not spreadsheet_id:
        return jsonify({"error": "Spreadsheet ID is required"}), 400
    
    email = email.lower()
    if email in get_form_emails(spreadsheet_id):
        if update_db:
            # update user's form_filled status in the database
            user = Users.query.filter_by(email=email).first()
            if not user:
                return jsonify({"error": "User not found"}), 404
            user.form_filled = "True"
            db.session.commit()
        return jsonify({"filled": True}), 200
    else:
        return jsonify({"filled": False}), 200


if __name__ == "__main__":
    # wait for models.py to be imported
    sleep(5)
    seed_database()
    app.run(host='0.0.0.0', port=8080, debug=True)
    
