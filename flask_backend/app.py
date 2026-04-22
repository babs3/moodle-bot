from time import sleep
from flask import request
import random
from datetime import datetime, timezone, timedelta
import json
from flask_backend.utils import *

@app.route('/')
def index():
    # test here use core_course_get_courses_by_field
    course_data = get_moodle_courses_by_field("shortname", "SCI")
    if course_data.get('courses'):
        # Extrai o ID do primeiro curso encontrado
        course_id = course_data['courses'][0]['id']
        course_fullname = course_data['courses'][0]['fullname']
        app.logger.info(f"Curso encontrado: {course_fullname} (ID: {course_id})")
    else:
        app.logger.warning("Nenhum curso encontrado para este utilizador.")
        course_id = None
    
    return f"<h1>Course ID: {course_id}</h1><p><strong>Course Name:</strong> {course_fullname}</p>" # "Flask está a correr na porta 8080!"

@app.route('/chat', methods=['POST'])
def chat():    
    data = request.json
    moodle_id = data.get('user_id') # Recebe o "2" do teu Javascript
    app.logger.info(f"Received message from user_id: {moodle_id}")
    user_message = data.get('message')

    # Busca os dados reais no Moodle
    info_utilizador = get_moodle_user_data(moodle_id)
    # Busca contents do Moodle
    moodle_contents = get_moodle_contents(2) # TODO: get course_id from user

    if moodle_contents is None:
        app.logger.error("Failed to fetch Moodle contents.")
    else:
        resources = extract_visible_resources(moodle_contents)
        app.logger.info(f"Recursos autorizados: {resources}")
        # lista com os filenames dos recursos autorizados, ex: ["slides1.pdf", "exercicio2.pdf"]
        filenames = [resource.get("filename") for resource in resources]

    
    # Aqui podes pôr a tua lógica ou chamar o Rasa via REST
    user_email = info_utilizador.get("email") if info_utilizador else "EMAIL@EXAMPLE.COM"
    username = info_utilizador.get("nome") if info_utilizador else "NOME_"

    url = "http://rasa:5005/webhooks/rest/webhook"
    current_time = datetime.now(timezone.utc).isoformat() #datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "sender": user_email,
        "message": user_message, #user_input,
        "metadata": {"username": username,"input_time":current_time, "user_id": moodle_id, "authorized_resources": filenames}
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        messages = response.json()

        bot_reply = ""

        for message in messages:
            if "text" in message:
                bot_reply += f"\n\n {message['text']}"
                
        return jsonify([{"text": f"{bot_reply.strip()}"}])

    except requests.RequestException as e:
        print(f"⚠️ Error connecting to Rasa: {e}")
        return None
    
@app.route("/api/get_moodle_user/<email>", methods=["GET"])
def get_moodle_user(email):
    moodle_user = MoodleUsers.query.filter(MoodleUsers.email == email).first()
    if not moodle_user:
        return jsonify({"error": "Moodle user not found"}), 404
    return jsonify({"id":str(moodle_user.id), "moodle_id": moodle_user.moodle_id, "email": moodle_user.email}) # "name": moodle_user.name

@app.route("/api/save_moodle_progress", methods=["POST"])
def save_moodle_progress():
    data = request.json
    user_id = data.get("user_id")
    app.logger.info(f"Saving Moodle progress for user_id: {user_id} with data: {data}")
    
    progress = MoodleUserHistory(
        moodle_user_id=int(user_id),
        question=data["question"],
        response=data["response"],
        pdfs=data["pdfs"],
        timestamp=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    db.session.add(progress)
    db.session.commit()
    
    if not progress:
        return jsonify({"error": "Failed to save Moodle progress"}), 500

    return jsonify({"message": "Moodle progress saved"}), 200

@app.route("/api/create_moodle_user", methods=["POST"])
def create_moodle_user():
    data = request.json
    app.logger.info(f"Creating Moodle user with data: {data}")
    
    moodle_user = MoodleUsers(moodle_id=int(data["moodle_id"]), email=data["email"])
    db.session.add(moodle_user)
    db.session.commit()
    
    # return the error if needed, to now what happen:
    if not moodle_user:
        return jsonify({"error": "Failed to create Moodle user"}), 500
    
    return jsonify({"message": "Moodle user created successfully"}), 200

@app.route("/api/save_moodle_user_history/<user_id>", methods=["POST"])
def save_moodle_user_history(user_id):
    data = request.json
    history = MoodleUserHistory(moodle_user_id=user_id, question=data["question"], response=data["response"], timestamp=datetime.now())
    db.session.add(history)
    db.session.commit()
    return jsonify({"message": "Moodle user history saved successfully"}), 200


if __name__ == "__main__":
    # wait for models.py to be imported
    sleep(5)
    app.run(host='0.0.0.0', port=8080, debug=True)
    
