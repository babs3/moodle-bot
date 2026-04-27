from time import sleep
from flask import request
from datetime import datetime, timezone, timedelta
import json
import time
from flask_backend.utils import *


@app.route('/')
def index():
    # test here use core_course_get_courses_by_field
    course_data = get_moodle_courses_by_field("shortname", COURSE_SHORTNAME)
    if course_data.get('courses'):
        # Extrai o ID do primeiro curso encontrado
        course_id = course_data['courses'][0]['id']
        course_fullname = course_data['courses'][0]['fullname']
        app.logger.info(f"Curso encontrado: {course_fullname} (ID: {course_id})")
    else:
        app.logger.warning("Nenhum curso encontrado para este utilizador.")
        course_id = None
        course_fullname = None
        
    return f"<h1>Course ID: {course_id}</h1><p><strong>Course Name:</strong> {course_fullname}</p>" # "Flask está a correr na porta 8080!"

@app.route('/chat', methods=['POST'])
def chat():    
    data = request.json
    moodle_id = data.get('user_id')
    app.logger.info(f"Received message from user_id: {moodle_id}")
    user_message = data.get('message')

    # Busca os dados reais no Moodle
    info_utilizador = get_moodle_user_data(moodle_id)
    user_email = info_utilizador.get("email") if info_utilizador else "EMAIL@EXAMPLE.COM"
    username = info_utilizador.get("nome") if info_utilizador else "NOME_"
    check_moodle_user_in_db(moodle_id, user_email) # Garante que o utilizador existe na BD, se não existir, cria um novo registo
    
    moodle_contents = get_moodle_contents(COURSE_ID)
    if moodle_contents is None:
        app.logger.error("Failed to fetch Moodle contents.")
    else:
        resources = extract_visible_resources(moodle_contents)
        app.logger.info(f"Recursos autorizados: {resources}")
        # lista com os filenames dos recursos autorizados, ex: ["slides1.pdf", "exercicio2.pdf"]
        filenames = [resource.get("filename") for resource in resources]
    
    # check if user is in tutor mode
    user = MoodleUsers.query.filter_by(moodle_id=moodle_id).first()
    if user and user.tutor_mode_active:
        app.logger.info(f"User {moodle_id} is in tutor mode.")
        
        url = "http://rasa:5005/webhooks/rest/webhook"
        current_time = datetime.now(timezone.utc).isoformat() #datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "sender": user_email,
            "message": "tutor menu buttons trigger",
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
                if "buttons" in message:
                    buttons = message["buttons"]
                    
            return jsonify([{"text": f"{bot_reply.strip()}"}, {"buttons": buttons}])

        except requests.RequestException as e:
            print(f"⚠️ Error connecting to Rasa: {e}")
            return None
        
    else:
        app.logger.info(f"User {moodle_id} is in normal mode.")
        # Busca contents do Moodle

        #quiz_id = get_quiz_id_by_name(COURSE_ID, "Quiz - SCI")
        #attempt_id = get_last_attempt_id(quiz_id, moodle_id)
        #quiz_review = get_quiz_attempt_review(attempt_id) # Exemplo de chamada, substitui pelo ID real da tentativa do quiz
        #erros = analisar_desempenho_aluno(quiz_review) # Analisa o desempenho do aluno e gera feedback personalizado
        #app.logger.info(f"Desempenho do aluno: {erros}")
        
        # Aqui podes pôr a tua lógica ou chamar o Rasa via REST
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

@app.route('/tutor_toggle', methods=['POST'])
def tutor_toggle():
    data = request.json
    user_id = data.get('user_id')
    active = data.get('active')

    # 1. Atualizar o estado do utilizador na BD
    user = MoodleUsers.query.filter_by(moodle_id=user_id).first()
    app.logger.info(f"Received tutor toggle for user_id: {user_id} with active: {active}")
    app.logger.info(f"Current user in DB before toggle: {user}")
    if not user:
        # Se o user não existir na nossa BD, criamos
        info_utilizador = get_moodle_user_data(user_id)
        user_email = info_utilizador.get("email") if info_utilizador else f"user_{user_id}@example.com"
        check_moodle_user_in_db(user_id, user_email) # Garante que o utilizador existe na BD, se não existir, cria um novo registo
        user = MoodleUsers.query.filter_by(moodle_id=user_id).first()

    user.tutor_mode_active = active
    db.session.commit()

    if not active:
        app.logger.info(f"Modo Tutor desligado para user_id: {user_id}")
        #return jsonify({"message": "Modo Tutor desligado."})
        return jsonify([{"text": "Modo Tutor desligado."}])

    # 2. Lógica de Verificação de Quizzes (O Trigger)
    # Vamos buscar todos os quizzes do curso que o aluno tem acesso e verificar se há tentativas novas para analisar. Se houver, fazemos a análise e preparamos um feedback personalizado.
    quizzes = get_user_quizzes_by_course(COURSE_ID, user_id) 
    app.logger.info(f"Quizzes encontrados para user_id {user_id}: {[quiz['name'] for quiz in quizzes]}")
    
    novos_erros_encontrados = []
    
    for quiz in quizzes:
        quiz_id = quiz['id']
        attempt_id = get_last_attempt_id(quiz_id, user_id)
        
        if attempt_id == None:
            continue
        
        app.logger.info(f"Verificando quiz_id: {quiz_id} para user_id: {user_id} com attempt_id: {attempt_id}")
        
        # Verificar se já analisámos esta tentativa
        analise = MoodleQuizAnalysis.query.filter_by(
            moodle_user_id=user_id, 
            quiz_id=quiz_id
        ).first()

        if not analise or analise.last_attempt_id < attempt_id:
            # Temos uma tentativa nova! Analisar...
            review_data = get_quiz_attempt_review(attempt_id)
            
            erros = analisar_desempenho_aluno(review_data) # A tua função BS4
            
            if erros:
                novos_erros_encontrados.extend(erros)
            
            # Atualizar ou criar o registo de análise
            if not analise:
                analise = MoodleQuizAnalysis(
                    moodle_user_id=user_id, 
                    quiz_id=quiz_id, 
                    last_attempt_id=attempt_id
                )
                db.session.add(analise)
            else:
                analise.last_attempt_id = attempt_id
            
            db.session.commit()

    # 3. Preparar Resposta para o Aluno
    if novos_erros_encontrados:
        
        url = "http://rasa:5005/webhooks/rest/webhook"
        payload = {
            "sender": "placeholder_for_email", #user_email,
            "message": "create topic trigger",
            "metadata": {"errors": novos_erros_encontrados}
        }
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers)
            response.raise_for_status()
            messages = response.json() 
            #app.logger.info(f"DEBUG COMPLETO RASA: {json.dumps(messages, indent=2)}") # Vê a estrutura real aqui  

            # Inicializamos a lista de erros como vazia
            lista_erros_final = []

            for message in messages:
                # Quando usas json_message no Rasa, os dados vêm na chave 'custom'
                if "custom" in message and "errors" in message["custom"]:
                    lista_erros_final = message["custom"]["errors"]
                    break # Encontramos o que queríamos

            #app.logger.info(f"⚠️ Erros extraídos: {lista_erros_final}")

            # Agora iteramos sobre a lista de objetos reais
            for error in lista_erros_final:
                topic_name = error.get('topic', 'Geral')
                
                # 1. Gestão do Tópico na DB
                topic = Topics.query.filter_by(name=topic_name).first()
                if not topic:
                    topic = Topics(name=topic_name)
                    db.session.add(topic)
                    db.session.commit() # Commit para gerar o ID do tópico
                    app.logger.info(f"Novo tópico criado: {topic_name} com ID {topic.id}")

                # 2. Guardar o progresso
                # Nota: Verifica se os nomes das chaves (student_answer vs resposta_aluno)
                # coincidem com o que enviaste no actions.py
                progresso = TutorProgress(
                    moodle_user_id=user_id,
                    slot=error.get('slot'),
                    tipo=error.get('tipo'),
                    topic=topic.id,
                    question=error.get('question'),
                    student_answer=error.get('student_answer'),
                    correct_answer=error.get('correct_answer')
                )
                db.session.add(progresso)

            db.session.commit() # Commit final de tudo o que foi adicionado

        except Exception as e:
            db.session.rollback()
            app.logger.error(f"⚠️ Erro ao processar tutor: {e}")
    
        #app.logger.info(f"Novos erros encontrados para user_id {user_id} nos temas de: {lista_erros_final}")
        temas = list(set([e['topic'] for e in lista_erros_final]))
        msg = f"Hello! I have found some issues in your answers, mainly in the topics: {', '.join(temas)}. Would you like to review these points with me?"
    else:
        msg = "I have activated the tutor mode, but I didn't find any new attempts to analyze. When you take a test, please let me know!"

    return jsonify({"text": f"{msg}"})

@app.route("/api/get_topics", methods=["GET"])
def get_topics():
    topics = Topics.query.all()
    return jsonify([{"id": topic.id, "name": topic.name} for topic in topics])

@app.route("/api/save_topic", methods=["POST"])
def save_topic():
    data = request.json
    topic_name = data.get("topic_name")
    
    if not topic_name:
        return jsonify({"error": "Topic name is required"}), 400

    topic = Topics.query.filter_by(name=topic_name).first()
    if not topic:
        topic = Topics(name=topic_name)
        db.session.add(topic)
        db.session.commit()
        app.logger.info(f"New topic created: {topic_name} with ID {topic.id}")
    else:
        app.logger.info(f"Topic already exists: {topic_name}")

    return jsonify({"message": "Topic saved", "id": topic.id})

@app.route("/api/get_moodle_user/<email>", methods=["GET"])
def get_moodle_user(email):
    moodle_user = MoodleUsers.query.filter(MoodleUsers.email == email).first()
    if not moodle_user:
        return jsonify({"error": "Moodle user not found"}), 404
    return jsonify({"id":str(moodle_user.id), "moodle_id": moodle_user.moodle_id, "email": moodle_user.email}) # "name": moodle_user.name

@app.route("/api/save_moodle_messages", methods=["POST"])
def save_moodle_messages(): # TODO: refactor para os novos campos da BD, como o is_tutor_interaction
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


# --- LÓGICA PRINCIPAL ---
def verificar_novos_quizzes():
    app.logger.info(f"[{time.strftime('%H:%M:%S')}] A iniciar varredura global...")
    
    # 1. Obter todos os cursos do Moodle
    params = {
        'wstoken': TOKEN,
        'wsfunction': "core_course_get_courses",
        'moodlewsrestformat': 'json'
    }
    try:
        cursos = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data=params).json()
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
        
    params.update({
        'wstoken': TOKEN,
        'wsfunction': "mod_quiz_get_quizzes_by_courses",
        'moodlewsrestformat': 'json'
    })
    try:
        dados_quizzes = requests.post(f"{MOODLE_URL}/webservice/rest/server.php", data=params).json()
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
                app.logger.info(f"-> NOVO QUIZ DETETADO: {q_nome} (ID: {q_id})")
                
                # --- AQUI ENTRA A TUA LÓGICA DE EXTRAÇÃO DE PERGUNTAS ---
                # Exemplo: popular_tabela_perguntas(q_id) TODO
                
                # 4. Registar que este quiz já foi tratado
                marcar_quiz_como_processado(q_id)
                app.logger.info(f"   Quiz {q_id} processado com sucesso.")
            else:
                # Opcional: TODO ignorar ou atualizar dados se o 'timemodified' mudou
                pass


def tarefa_monitor():
    # Esta função será chamada automaticamente pelo scheduler
    # Criamos o contexto manualmente para que a DB funcione
    with app.app_context():
        try:
            verificar_novos_quizzes()
        except Exception as e:
            app.logger.error(f"Erro no monitor: {e}")

if __name__ == "__main__":
    # Configuração do agendador
    scheduler.add_job(id='moodle_monitor_job', func=tarefa_monitor, trigger='interval', minutes=0.5)
    scheduler.init_app(app)
    scheduler.start()

    app.run(host='0.0.0.0', port=8080, debug=True, use_reloader=False)