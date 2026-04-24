import logging
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
from bs4 import BeautifulSoup
from flask_backend.models import *

MOODLE_URL = "http://host.docker.internal" # Este endereço diz ao Docker: "Sai do contentor e vai buscar o localhost da máquina real".
TOKEN = os.getenv("MOODLE_TOKEN")
COURSE_SHORTNAME = os.getenv("MOODLE_COURSE_SHORTNAME")

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
CORS(app) # Isto permite que o Moodle aceda à API

app.config["SQLALCHEMY_DATABASE_URI"] = f'postgresql://{os.getenv("POSTGRES_USER")}:{os.getenv("POSTGRES_PASSWORD")}@db/{os.getenv("POSTGRES_DB")}'
app.config["JWT_SECRET_KEY"] = "super-secret-key"  # Change in production!
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)  # For database migrations
jwt = JWTManager(app)

def check_moodle_user_in_db(moodle_id, email):
    # Ver se o utilizador já existe na nossa BD, se não existir, criar
    moodle_user = MoodleUsers.query.filter_by(moodle_id=moodle_id).first()
    if not moodle_user:
        moodle_user = MoodleUsers(moodle_id=moodle_id, email=email)
        db.session.add(moodle_user)
        db.session.commit()
        app.logger.info(f"Created new Moodle user in DB: {email} (ID: {moodle_id})")
    else:
        app.logger.info(f"Moodle user already exists in DB: {email} (ID: {moodle_id})")

def analisar_desempenho_aluno(quiz_data):
    erros = []
    
    for q in quiz_data.get('questions', []):
        # Convertemos primeiro para string com str(), e só depois fazemos o replace
        mark_str = str(q.get('mark', '0'))
        max_mark_str = str(q.get('maxmark', '0'))

        mark = float(mark_str.replace(',', '.'))
        max_mark = float(max_mark_str.replace(',', '.'))
        
        # Se o aluno não teve a nota máxima na pergunta
        if mark < max_mark:
            soup = BeautifulSoup(q['html'], 'html.parser')
            
            # 1. Extrair o texto da pergunta
            qtext_div = soup.find('div', class_='qtext')
            pergunta_texto = qtext_div.get_text(strip=True) if qtext_div else "Não encontrado"
            
            # Gerar o tema da pergunta
            
            
            # 2. Extrair a resposta que o aluno deu
            # O Moodle guarda a resposta selecionada em inputs 'checked' ou campos de texto
            resposta_aluno = "Sem resposta"
            
            if q['type'] in ['multichoice', 'truefalse']:
                # Procura o label associado ao rádio/checkbox marcado
                checked_input = soup.find('input', checked=True)
                if checked_input:
                    # Tenta encontrar o texto da opção ao lado do input
                    label = soup.find('label', {'for': checked_input.get('id')})
                    if label:
                        resposta_aluno = label.get_text(strip=True)
            
            elif q['type'] == 'shortanswer':
                input_text = soup.find('input', type='text')
                if input_text:
                    resposta_aluno = input_text.get('value', 'Vazio')

            # 3. Extrair a resposta correta (Feedback do Moodle)
            right_answer_div = soup.find('div', class_='rightanswer')
            resposta_correta = right_answer_div.get_text(strip=True) if right_answer_div else "Não disponível"
            # retirar o "Resposta correta: " do início da resposta correta
            resposta_correta = resposta_correta.replace("Resposta correta: ", "")

            erros.append({
                'slot': q['slot'],
                'tipo': q['type'],
                'question': pergunta_texto,
                'student_answer': resposta_aluno,
                'correct_answer': resposta_correta #,
                #'nota_obtida': mark,
                #'nota_maxima': max_mark
            })
            
    return erros


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
        #app.logger.info(f"Resposta bruta do Moodle: {response_data}")

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

def get_quiz_attempt_review(attempt_id):
    """
    Obtém os detalhes de uma tentativa de quiz, incluindo perguntas e respostas.
    """
    function = "mod_quiz_get_attempt_review"
    app.logger.info(f"--- INÍCIO DA REVISÃO DE TENTATIVA --- | Attempt ID: {attempt_id}")
    
    params = {
        'wstoken': TOKEN,
        'wsfunction': function,
        'moodlewsrestformat': 'json',
        'attemptid': attempt_id,
        # 'page': -1  # Opcional: -1 retorna todas as páginas de perguntas de uma vez
    }
    
    try:
        response = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data=params, timeout=10)
        review_data = response.json()
        
        # Verificação de erro na resposta da API
        if isinstance(review_data, dict) and "exception" in review_data:
            app.logger.error(f"Erro na API Moodle (Review): {review_data['message']}")
            return None

        app.logger.info(f"Dados da tentativa {attempt_id} obtidos com sucesso.")
        return review_data

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Erro na requisição ao Moodle: {e}")
        return None
    
def get_quiz_id_by_name(course_id, quiz_name):
    """
    Procura o ID de um questionário dentro de um curso através do nome.
    """
    function = "mod_quiz_get_quizzes_by_courses"
    app.logger.info(f"--- PROCURANDO ID DO QUIZ: '{quiz_name}' no curso {course_id} ---")
    
    params = {
        'wstoken': TOKEN,
        'wsfunction': function,
        'moodlewsrestformat': 'json',
        'courseids[0]': course_id  # A API espera um array de IDs
    }

    try:
        response = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data=params, timeout=10)
        data = response.json()

        if isinstance(data, dict) and "exception" in data:
            app.logger.error(f"Erro na API: {data['message']}")
            return None

        # A resposta contém uma chave 'quizzes' que é uma lista
        quizzes = data.get('quizzes', [])
        
        for quiz in quizzes:
            # Compara o nome (podes usar .strip().lower() para ser mais flexível)
            if quiz['name'].strip().lower() == quiz_name.strip().lower():
                app.logger.info(f"Quiz encontrado! ID: {quiz['id']}")
                return quiz['id']

        app.logger.warning(f"Nenhum questionário com o nome '{quiz_name}' foi encontrado.")
        return None

    except Exception as e:
        app.logger.error(f"Erro ao procurar quiz por nome: {e}")
        return None
    
def get_user_quizzes_by_course(course_id, user_id):
    """
    Obtém a lista de quizzes de um curso e verifica quais o aluno já tentou.
    """
    function = "mod_quiz_get_quizzes_by_courses"
    app.logger.info(f"--- BUSCANDO QUIZZES DO CURSO PARA O USUÁRIO --- | Course ID: {course_id} | User ID: {user_id}")
    
    params = {
        'wstoken': TOKEN,
        'wsfunction': function,
        'moodlewsrestformat': 'json',
        'courseids[0]': course_id
    }

    try:
        response = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data=params, timeout=10)
        data = response.json()

        if isinstance(data, dict) and "exception" in data:
            app.logger.error(f"Erro na API Moodle: {data['message']}")
            return None

        quizzes = data.get('quizzes', [])
        app.logger.info(f"Total de quizzes encontrados no curso: {len(quizzes)}")
        
        return quizzes

    except Exception as e:
        app.logger.error(f"Erro ao obter quizzes do curso: {e}")
        return None
    
def get_last_attempt_id(quiz_id, user_id):
    """
    Obtém o ID da última tentativa de um aluno num questionário específico.
    """
    function = "mod_quiz_get_user_quiz_attempts"
    app.logger.info(f"--- BUSCANDO TENTATIVAS --- | Quiz ID: {quiz_id} | User ID: {user_id}")
    
    params = {
        'wstoken': TOKEN,
        'wsfunction': function,
        'moodlewsrestformat': 'json',
        'quizid': quiz_id,
        'userid': user_id,
        'status': 'finished'  # apenas as finalizadas
    }
    
    try:
        response = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data=params, timeout=10)
        data = response.json()
        
        if isinstance(data, dict) and "exception" in data:
            app.logger.error(f"Erro na API Moodle: {data['message']}")
            return None

        attempts = data.get('attempts', [])
        
        if not attempts:
            app.logger.warning(f"Nenhuma tentativa encontrada para o User {user_id} no Quiz {quiz_id}")
            return None

        # Ordenar tentativas pelo ID (a mais recente terá o ID maior)
        # Ou podes filtrar apenas as que têm o state 'finished'
        attempts.sort(key=lambda x: x['id'], reverse=True)
        
        last_attempt = attempts[0]
        app.logger.info(f"Tentativa encontrada! ID: {last_attempt['id']} | Estado: {last_attempt['state']}")
        
        return last_attempt['id']

    except Exception as e:
        app.logger.error(f"Erro ao obter tentativas: {e}")
        return None
    
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
        #app.logger.info(f"Resposta bruta do Moodle para cursos: {courses}")
        
        # Se o Moodle retornar um erro no JSON (ex: token inválido)
        if isinstance(courses, dict) and "exception" in courses:
            app.logger.error(f"Erro na API Moodle: {courses['message']}")
            return None

        app.logger.info(f"Cursos obtidos com sucesso para {field}={value}")
        return courses

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Erro na requisição ao Moodle: {e}")
        return None
    
course_data = get_moodle_courses_by_field("shortname", COURSE_SHORTNAME)
if course_data is None:
    app.logger.error("Failed to fetch courses from Moodle. Check the logs for details.")
elif course_data.get('courses'):
    # Extrai o ID do primeiro curso encontrado
    COURSE_ID = course_data['courses'][0]['id']
else:
    COURSE_ID = "2"  # Fallback para um ID padrão, mas idealmente deves lidar com isso melhor