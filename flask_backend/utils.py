from flask import Flask, jsonify
from flask_cors import CORS
import hashlib
from flask_mail import Mail, Message
import os
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from google.oauth2 import service_account
from googleapiclient.discovery import build
import requests
from flask_backend.models import *

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
DOMAIN = os.getenv("DOMAIN")
MOODLE_URL = "http://host.docker.internal" # Este endereço diz ao Docker: "Sai do contentor e vai buscar o localhost da máquina real".
TOKEN = os.getenv("MOODLE_TOKEN")

app = Flask(__name__)
CORS(app) # Isto permite que o Moodle aceda à API

# Flask-Mail Configuration
app.config["MAIL_SERVER"] = "smtp.gmail.com"  # Use your SMTP provider
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")  # Your no-reply email address
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_USERNAME") 
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")  # App-specific password

app.config["SQLALCHEMY_DATABASE_URI"] = f'postgresql://{os.getenv("POSTGRES_USER")}:{os.getenv("POSTGRES_PASSWORD")}@db/{os.getenv("POSTGRES_DB")}'
app.config["JWT_SECRET_KEY"] = "super-secret-key"  # Change in production!
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

mail = Mail(app)

db.init_app(app)
migrate = Migrate(app, db)  # For database migrations
jwt = JWTManager(app)

def get_moodle_user_data(user_id):
    # 1. Usa o IP direto e verifica se precisas de porta (ex: :80)
    function = "core_user_get_users"
    
    app.logger.info(f"--- INÍCIO DA BUSCA MOODLE ---")
    app.logger.info(f"ID: {user_id} | URL: {MOODLE_URL}")

    params = {
        'wstoken': TOKEN,
        'wsfunction': function,
        'moodlewsrestformat': 'json',
        'criteria[0][key]': 'id',
        'criteria[0][value]': user_id
    }

    try:
        # 2. Adiciona um timeout para o código não ficar "pendurado" para sempre
        response = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data=params, timeout=5)
        response_data = response.json()
        app.logger.info(f"Resposta bruta do Moodle: {response_data}")

        if 'users' in response_data and len(response_data['users']) > 0:
            user = response_data['users'][0]
            return {
                "nome": user['firstname'],
                "apelido": user['lastname'],
                "email": user['email'],
            }
        
        app.logger.warning(f"Utilizador {user_id} não encontrado no Moodle.")
        return None
            
    except Exception as e:
        # 3. Usa o logger para o erro também, para teres a certeza que vês na consola
        app.logger.error(f"ERRO CRÍTICO ao ligar ao Moodle: {str(e)}")
        return None
    
def get_moodle_contents(course_id):
    function = "core_course_get_contents"
    app.logger.info(f"--- INÍCIO DA BUSCA DE CONTEÚDOS MOODLE --- | Course ID: {course_id}")
    params = {
        'wstoken': TOKEN,
        'wsfunction': function,
        'moodlewsrestformat': 'json',
        'courseid': course_id
    }
    
    try:
        response = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data=params, timeout=5)
        contents = response.json()
        #app.logger.info(f"Resposta bruta do Moodle para conteúdos: {contents}")
        
        # Se o Moodle retornar um erro no JSON (ex: token inválido)
        if isinstance(contents, dict) and "exception" in contents:
            app.logger.error(f"Erro na API Moodle: {contents['message']}")
            return None

        app.logger.info(f"Conteúdos obtidos com sucesso para o curso {course_id}")
        return contents

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Erro na requisição ao Moodle: {e}")
        return None
    
def extract_visible_resources(moodle_json):
    allowed_materials = []
    
    # Percorrer cada secção (Geral, aula 0, aula 1...)
    for section in moodle_json:
        # Percorrer cada módulo dentro da secção
        for module in section.get('modules', []):
            
            # Filtro 1: É um recurso (ficheiro)?
            # Filtro 2: Está visível para o aluno?
            if module['modname'] == 'resource' and module['visible'] == 1:
                
                # Extraímos o ID e o Nome
                resource_info = {
                    'moodle_id': module['id'],
                    'display_name': module['name'],
                    # Opcional: extrair o nome real do ficheiro se existir
                    'filename': module['contents'][0]['filename'] if 'contents' in module else module['name']
                }
                allowed_materials.append(resource_info)
                
    return allowed_materials

def get_moodle_courses_by_field(field, value):
    function = "core_course_get_courses_by_field"
    app.logger.info(f"--- INÍCIO DA BUSCA DE CURSOS MOODLE --- | Field: {field}, Value: {value}")
    params = {
        'wstoken': TOKEN,
        'wsfunction': function,
        'moodlewsrestformat': 'json',
        'field': field,
        'value': value
    }
    
    try:
        response = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data=params, timeout=5)
        courses = response.json()
        app.logger.info(f"Resposta bruta do Moodle para cursos: {courses}")
        
        # Se o Moodle retornar um erro no JSON (ex: token inválido)
        if isinstance(courses, dict) and "exception" in courses:
            app.logger.error(f"Erro na API Moodle: {courses['message']}")
            return None

        app.logger.info(f"Cursos obtidos com sucesso para {field}={value}")
        return courses

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Erro na requisição ao Moodle: {e}")
        return None