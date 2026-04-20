import requests

def create_moodle_user(moodle_id, email):
    response = requests.post("http://flask-server:8080/api/create_moodle_user/", json={"moodle_id": moodle_id, "email": email})
    return response.json() if response.status_code == 200 else {}

def send_password_reset_email(email):
    response = requests.post("http://flask-server:8080/api/send_password_reset_email/" + email)
    return response.json() if response.status_code == 200 else {}

def save_reset_token(email, token):
    response = requests.post("http://flask-server:8080/api/save_reset_token", json={"email": email, "token": token})
    return response.json() if response.status_code == 200 else {}

def fetch_reset_token(token):
    response = requests.get("http://flask-server:8080/api/fetch_reset_token/" + token)
    return response.json() if response.status_code == 200 else {}

def delete_reset_token(token):
    response = requests.delete("http://flask-server:8080/api/delete_reset_token/" + token)
    return response.json() if response.status_code == 200 else {}

def fetch_user(user_email):
    response = requests.get("http://flask-server:8080/api/get_user/" + user_email)
    return response.json() if response.status_code == 200 else {}

def fetch_student(student_email):
    response = requests.get("http://flask-server:8080/api/get_student/" + student_email)
    return response.json() if response.status_code == 200 else {}

def fetch_teacher(teacher_email):
    response = requests.get("http://flask-server:8080/api/get_teacher/" + teacher_email)
    return response.json() if response.status_code == 200 else {}

def fetch_other(other_email):
    response = requests.get("http://flask-server:8080/api/get_other/" + other_email)
    return response.json() if response.status_code == 200 else {}

def get_progress(student_email):
    user = fetch_user(student_email)
    if not user:
        return {}
    user_id = str(user.get("id"))
    response = requests.get("http://flask-server:8080/api/get_user_progress/" + user_id)
    return response.json() if response.status_code == 200 else {}

def save_progress(user_id, data):
    response = requests.post("http://flask-server:8080/api/save_user_progress/" + str(user_id), json=data)
    return response.json() if response.status_code == 200 else {}

def fetch_classes():
    response = requests.get("http://flask-server:8080/api/classes")
    return response.json() if response.status_code == 200 else {}

def fetch_class_progress(class_id):
    response = requests.get("http://flask-server:8080/api/class_progress/" + str(class_id))
    return response.json() if response.status_code == 200 else {}

def fetch_progress():
    response = requests.get("http://flask-server:8080/api/progress")
    return response.json() if response.status_code == 200 else {}

def fetch_teacher_classes(teacher_email):
    response = requests.get("http://flask-server:8080/api/teacher_classes/" + teacher_email)
    return response.json() if response.status_code == 200 else {}

def fetch_message_history(user_email):
    user = fetch_user(user_email)
    if not user:
        return {}
    user_id = user.get("id")
    response = requests.get("http://flask-server:8080/api/message_history/" + str(user_id))
    return response.json() if response.status_code == 200 else {}

def save_message_history(user_email, data):
    user = fetch_user(user_email)
    if not user:
        return {}
    user_id = user.get("id")
    response = requests.post("http://flask-server:8080/api/save_message_history/" + str(user_id), json=data)
    return response.json() if response.status_code == 200 else {}

def authenticate_user(email, password):
    response = requests.post("http://flask-server:8080/api/authenticate", json={"email": email, "password": password})
    return response.json() if response.status_code == 200 else {}

def register_student(name, email, password, up, course, year, class_id):
    response = requests.post("http://flask-server:8080/api/register_student", json={"name": name, "email": email, "password": password, "up": up, "course": course, "year": year, "class_id": class_id})
    return response.json() if response.status_code == 200 else {}

def register_teacher(name, email, password, classes):
    response = requests.post("http://flask-server:8080/api/register_teacher", json={"name": name, "email": email, "password": password, "classes": classes})
    return response.json() if response.status_code == 200 else {}

def register_other(name, email, password, role, job, company, graduation_year, graduation_area):
    response = requests.post("http://flask-server:8080/api/register_other", json={"name": name, "email": email, "password": password, "role": role, "job": job, "company": company, "graduation_year": graduation_year, "graduation_area": graduation_area})
    return response.json() if response.status_code == 200 else {}

def verify_user(email, verification_code):
    user = fetch_user(email)
    if not user:
        return {}
    response = requests.post("http://flask-server:8080/api/verify_user", json={"email": email, "verification_code": verification_code})
    return response.json() if response.status_code == 200 else {}

def reset_password(email, new_password):
    response = requests.post("http://flask-server:8080/api/reset_password", json={"email": email, "new_password": new_password})
    return response.json() if response.status_code == 200 else {response.text}

def send_confirmation_email(email):
    response = requests.post("http://flask-server:8080/api/send_confirmation_email/" + email)
    return response.json() if response.status_code == 200 else {}

def send_reset_password_email(email):
    response = requests.post("http://flask-server:8080/api/send_reset_password_email/" + email)
    return response.json() if response.status_code == 200 else {}

def has_filled_form(email, spreadsheet_id, update_db=False):
    response = requests.get("http://flask-server:8080/api/has_filled_form/" + email, json={"spreadsheet_id": spreadsheet_id, "update_db": update_db})
    return response.json() if response.status_code == 200 else {}

def fetch_topics():
    response = requests.get("http://flask-server:8080/api/topics")
    return response.json() if response.status_code == 200 else {}

def save_topic(topic):
    response = requests.post("http://flask-server:8080/api/save_topic/" + topic)
    return response.json() if response.status_code == 200 else {}

def get_topic(topic_id):
    response = requests.get("http://flask-server:8080/api/get_topic/" + str(topic_id))
    return response.json() if response.status_code == 200 else {}

def get_topic_id_to_name_mapping():
    response = requests.get("http://flask-server:8080/api/get_topic_id_to_name_mapping")
    return response.json() if response.status_code == 200 else {}