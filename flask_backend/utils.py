import json
import logging
import time
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
from flask_apscheduler import APScheduler
from bs4 import BeautifulSoup
from flask_backend.models import *

RASA_URL = "http://rasa:5005/webhooks/rest/webhook"
MOODLE_URL = "http://host.docker.internal" # Este endereço diz ao Docker: "Sai do contentor e vai buscar o localhost da máquina real".
TOKEN = os.getenv("MOODLE_TOKEN")
COURSE_SHORTNAME = os.getenv("MOODLE_COURSE_SHORTNAME")

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
CORS(app) # Isto permite que o Moodle aceda à API
scheduler = APScheduler() # Para agendar tarefas periódicas, como verificar quizzes novos

app.config["SQLALCHEMY_DATABASE_URI"] = f'postgresql://{os.getenv("POSTGRES_USER")}:{os.getenv("POSTGRES_PASSWORD")}@db/{os.getenv("POSTGRES_DB")}'
app.config["JWT_SECRET_KEY"] = "super-secret-key"  # Change in production!
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)  # For database migrations
jwt = JWTManager(app)

def new_quiz_polling():
    app.logger.info(f"[{time.strftime('%H:%M:%S')}] A iniciar polling a novos quizzes...")
    function = "core_course_get_courses"
    # 1. Obter todos os cursos do Moodle
    try:
        cursos = call_moodle(function, {})
    except Exception as e:
        app.logger.error(f"Erro na chamada à API: {e}")
        cursos = None
    
    if not cursos or 'exception' in cursos:
        app.logger.error("Erro ao obter cursos.")
        return

    app.logger.info(f"Cursos encontrados: {cursos}")
    course_ids = [c['id'] for c in cursos]
    
    # 2. Obter todos os quizzes destes cursos (em blocos para evitar URLs gigantes)
    # O Moodle espera parâmetros no formato: courseids[0]=id1, courseids[1]=id2...
    params = {}
    for i, cid in enumerate(course_ids):
        params[f'courseids[{i}]'] = cid
        
    function = "mod_quiz_get_quizzes_by_courses"
        
    try:
        dados_quizzes = call_moodle(function, params)
    except Exception as e:
        app.logger.error(f"Erro na chamada à API: {e}")
        dados_quizzes = None
    
    if dados_quizzes and 'quizzes' in dados_quizzes:
        app.logger.info(f"Quizzes encontrados: {dados_quizzes['quizzes']}")

        for quiz in dados_quizzes['quizzes']:
            q_id = quiz['id']
            q_nome = quiz['name']
            
            # 3. Comparar com o que já temos no banco de dados
            if not quiz_ja_processado(q_id):
                marcar_quiz_como_processado(q_id, q_nome)
                app.logger.info(f"A processar perguntas do novo quiz: {q_nome}")
                
                lista_perguntas = obter_perguntas_do_quiz(q_id)
                #app.logger.info(f"Perguntas extraídas: {lista_perguntas}")             
                   
                lista_final_perguntas = criar_topicos_para_perguntas(lista_perguntas) 
                app.logger.info(f"Perguntas processadas pelo Rasa: {lista_final_perguntas}")
                
                popular_db(q_id, lista_final_perguntas)
            else:
                # Opcional: TODO ignorar ou atualizar dados se o 'timemodified' mudou
                pass

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
        'criteria[0][key]': 'id',
        'criteria[0][value]': user_id
    }

    try:
        # 2. Adiciona um timeout para o código não ficar "pendurado" para sempre
        response_data = call_moodle(function, params, timeout=5)
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
        'courseid': course_id
    }
    
    try:
        contents = call_moodle(function, params, timeout=5)
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
        'attemptid': attempt_id,
        # 'page': -1  # Opcional: -1 retorna todas as páginas de perguntas de uma vez
    }
    
    try:
        # timeout mais longo porque esta chamada pode demorar, especialmente para quizzes grandes
        review_data = call_moodle(function, params, timeout=10)
        
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
        'courseids[0]': course_id  # A API espera um array de IDs
    }

    try:
        data = call_moodle(function, params, timeout=10)

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
    
    try:
        data = call_moodle(function, {'courseids[0]': course_id}, timeout=10)

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
        'quizid': quiz_id,
        'userid': user_id,
        'status': 'finished'  # apenas as finalizadas
    }
    
    try:
        data = call_moodle(function, params, timeout=10)
        
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
        'field': field,
        'value': value
    }
    
    try:
        courses = call_moodle(function, params, timeout=5)
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
    
def fetch_course_id_from_moodle():
    try:
        # Substitui pela tua lógica real de chamada à API do Moodle
        function = "core_course_get_courses_by_field"
        params = {
            'field': "shortname",
            'value': COURSE_SHORTNAME
        }
        
        course_data = call_moodle(function, params, timeout=5)  
        course_id = course_data['courses'][0]['id']

        return course_id
    
    except Exception as e:
        print(f"Erro na conexão com Moodle: {e}")
    
    return None

def quiz_ja_processado(quiz_id):
    # Verificar se já analisámos esta tentativa
    analise = MoodleQuizPolling.query.filter_by(
        quiz_id=quiz_id
    ).first()
    
    if analise:
        return True
    else:
        return False

def marcar_quiz_como_processado(quiz_id, quiz_name=""):
    # Criar um novo registo de quiz processado
    novo_registo = MoodleQuizPolling(
        quiz_id=quiz_id,
        quiz_name=quiz_name
    )
    db.session.add(novo_registo)
    db.session.commit()
    
def call_moodle(function, params={}, timeout=5):
    """Função genérica para chamar o Web Service do Moodle"""
    params.update({
        'wstoken': TOKEN,
        'wsfunction': function,
        'moodlewsrestformat': 'json'
    })
    try:
        if timeout:
            response = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data=params, timeout=timeout)
        else:
            response = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data=params)
        return response.json()
    except Exception as e:
        app.logger.error(f"Erro na chamada à API: {e}")
        return None
    
def obter_perguntas_do_quiz(quiz_id):
    # 1. Iniciar uma tentativa para ler o conteúdo
    # Nota: Se o quiz tiver password, precisarias de a passar aqui
    tentativa = call_moodle('mod_quiz_start_attempt', {'quizid': quiz_id})
    
    if 'attempt' not in tentativa:
        app.logger.error(f"Erro ao iniciar tentativa no quiz {quiz_id}: {tentativa}")
        return []

    attempt_id = tentativa['attempt']['id']
    perguntas_extraidas = []

    # 2. Obter os dados da tentativa (é aqui que estão as perguntas)
    # O Moodle pagina as perguntas. Por defeito, tentamos a página 0. 
    # TODO: se houver mais páginas, precisas de iterar até obter todas as perguntas.
    dados = call_moodle('mod_quiz_get_attempt_data', {
        'attemptid': attempt_id,
        'page': 0
    })
    
    if 'questions' in dados:
        for q in dados['questions']:
            # Extração de dados básicos
            texto_pergunta = extrair_conteudo_pergunta(q['html'])
            if q['type'] == 'truefalse':
                texto_pergunta = "Verdadeiro ou Falso: " + texto_pergunta
            pergunta = {
                'moodle_question_id': q['slot'], # Slot é a posição no quiz
                #'tipo': q['type'],
                #'html_pergunta': q['html'], # Contém o enunciado e as opções
                'texto_pergunta': texto_pergunta
                #'numero': q['number']
            }
            perguntas_extraidas.append(pergunta)

    # 3. Finalizar a tentativa (para não "sujar" o Moodle)
    call_moodle('mod_quiz_process_attempt', {
        'attemptid': attempt_id,
        'finishattempt': 1 # 1 para finalizar
    })

    return perguntas_extraidas

def extrair_conteudo_pergunta(html_raw):
    # 1. Carregar o HTML no BeautifulSoup
    soup = BeautifulSoup(html_raw, 'html.parser')
    
    # 2. Localizar a div que contém o enunciado (sempre classe 'qtext')
    qtext_div = soup.find('div', class_='qtext')
    
    if qtext_div:
        # get_text() remove todas as tags HTML e devolve apenas o texto limpo
        # strip=True remove espaços e quebras de linha desnecessárias no início/fim
        texto_limpo = qtext_div.get_text(strip=True)
        return texto_limpo
    
    return "Texto não encontrado"

def criar_topicos_para_perguntas(pergunta_id_texto):
    payload = {
        "sender": "doesnt_matter", #user_email
        "message": "create topic trigger",
        "metadata": {"perguntas": pergunta_id_texto}
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(RASA_URL, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        messages = response.json() 
        #app.logger.info(f"DEBUG COMPLETO RASA: {json.dumps(messages, indent=2)}")

        lista_perguntas_final = []

        for message in messages:
            # 1. Verificamos se a mensagem tem o campo 'custom'
            if "custom" in message:
                custom_data = message["custom"]
                
                # 2. Procuramos pela chave que definimos no Rasa (gemini_analysis)
                # Esta chave contém a lista de perguntas já com tópicos e IDs convertidos
                if "gemini_analysis" in custom_data:
                    lista_perguntas_final = custom_data.get("gemini_analysis", [])
                    app.logger.info("Encontrada análise do Gemini com sucesso.")
                    break 

        # 3. Validar e Logar os resultados
        if lista_perguntas_final:
            app.logger.info(f"Processadas {len(lista_perguntas_final)} perguntas.")
        else:
            app.logger.warning("Nenhuma pergunta processada encontrada na resposta do Rasa.")

    except Exception as e:
        app.logger.error(f"Erro ao processar resposta do Rasa: {e}")
        
    return lista_perguntas_final

              
def popular_db(quiz_id, perguntas):
    for p in perguntas:
        # ir buscar id do topico à tabela de tópicos, usando o nome do tópico que o Gemini nos deu
        topic = Topics.query.filter_by(name=p.get('topic')).first()
        # se nao exitir, criar o tópico
        topic_id = topic.id if topic else None
        if not topic:
            topic = Topics(name=p.get('topic'))
            db.session.add(topic)
            db.session.commit() # Commit para gerar o ID do tópico
            app.logger.info(f"Novo tópico criado: {p.get('topic')} com ID {topic.id}")
            topic_id = topic.id
            
        # Aqui fazes o insert na tua tabela 'questoes'
        nova_questao = MoodleQuizData(
            quiz_id=quiz_id,
            question=p.get('question'),
            topic_id=topic_id
        )
        db.session.add(nova_questao)
    db.session.commit()