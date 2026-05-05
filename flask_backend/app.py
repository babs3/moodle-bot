import os
#print(f"📂  Conteúdo da pasta /app: {os.listdir('/app')}")
from flask import request
from datetime import datetime, timezone, timedelta
import json
import time
import shutil
import threading
from knowledge_engine import delete_pdf_from_knowledge, process_pdfs
from flask_cors import CORS
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from google.oauth2 import service_account
from utils import *
from models import *

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


def wait_for_rasa():
    app.logger.info("A aguardar que o Rasa fique disponível...")
    while True:
        try:
            response = requests.get("http://rasa:5005")
            if response.status_code == 200:
                app.logger.info("Rasa está online!")
                break
        except requests.exceptions.ConnectionError:
            pass
        
        app.logger.info("Rasa ainda a carregar... a tentar novamente em 5 segundos")
        time.sleep(5)
        
@app.route('/')
def index():        
    return "Flask está a correr na porta 8082!"

@app.route('/chat', methods=['POST'])
def chat():    
    data = request.json
    app.logger.info(f"---------> Received chat request with data: {data}")
    moodle_id = data.get('user_id')
    course_id = data.get('course_id')
    app.logger.info(f"Received message from user_id: {moodle_id}")
    user_message = data.get('message')

    # Busca os dados reais no Moodle
    info_utilizador = get_moodle_user_data(moodle_id)
    user_email = info_utilizador.get("email") if info_utilizador else "EMAIL@EXAMPLE.COM"
    username = info_utilizador.get("nome") if info_utilizador else "NOME_"
    check_moodle_user_in_db(moodle_id, user_email) # Garante que o utilizador existe na BD, se não existir, cria um novo registo
    
    filenames = []
    moodle_contents, moodle_contents_names = get_moodle_contents(course_id)
    if moodle_contents_names == None:
        app.logger.error("Failed to fetch Moodle contents.")
        return jsonify([{"text": "There is no content available for this course or an error occurred while fetching the content. Please try again later."}])
    elif moodle_contents_names == []:
        app.logger.warning("No contents found for this course.")
        return jsonify([{"text": "There is no content available for this course. Please check back later or contact your instructor."}])
    else:
        resources = extract_visible_resources(moodle_contents)
        app.logger.info(f"Recursos autorizados: {resources}")
        # lista com os filenames dos recursos autorizados, ex: ["slides1.pdf", "exercicio2.pdf"]
        filenames = [resource.get("filename") for resource in resources]
        
        authorized_resources = []
        for filename in filenames:
            if filename in resources:
                authorized_resources.append(filename)
        
        if authorized_resources == []:
            app.logger.warning("No authorized resources found for this course.")
            #return jsonify([{"text": "You don't have access to any resources for this course. Please check back later or contact your instructor."}])
    
    # check if user is in tutor mode
    user = MoodleUsers.query.filter_by(moodle_id=moodle_id).first()
    
    if user and user.tutor_mode_active:
        app.logger.info(f"User {moodle_id} is in tutor mode.")
        
        current_time = datetime.now(timezone.utc).isoformat() 
        payload = {
            "sender": user_email,
            "message": "tutor menu buttons trigger",
            "metadata": {"username": username, "input_time":current_time, "user_id": moodle_id, "authorized_resources": authorized_resources, "tutor_mode": True, "user_message": user_message}
        }
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(RASA_URL, data=json.dumps(payload), headers=headers)
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
        
        current_time = datetime.now(timezone.utc).isoformat()
        payload = {
            "sender": user_email,
            "message": user_message, #user_input,
            "metadata": {"username": username,"input_time":current_time, "user_id": moodle_id, "authorized_resources": authorized_resources, "tutor_mode": False}
        }
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(RASA_URL, data=json.dumps(payload), headers=headers)
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

@app.route('/process_knowledge', methods=['POST'])
def process_knowledge():
    files = request.files.getlist('files[]')
    course_id = request.form.get('course_id')
    api_key = request.form.get('api_key')

    if not files or not course_id:
        return jsonify({"error": "Dados insuficientes"}), 400

    # 1. Criar pasta temporária para processamento
    temp_dir = f"temp_processing_{course_id}"
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # 2. Salvar ficheiros do request para a pasta
        for file in files:
            file_path = os.path.join(temp_dir, file.filename)
            file.save(file_path)
            new_file = KnowledgeFile(
                courseid=course_id,
                filename=file.filename
            )
            db.session.add(new_file)
            db.session.commit()

        # 3. Correr a pipeline
        success = process_pdfs(pdf_folder=temp_dir, course_id=course_id, vector_db_path=f"/app/vector_store") #TODO: add COURSE_ID

        # 4. Limpar ficheiros temporários após processar
        shutil.rmtree(temp_dir)

        if success:
            return jsonify({"status": "success", "message": "Conhecimento gerado!"}), 200
        else:
            return jsonify({"status": "error", "message": "Falha ao processar PDFs"}), 500

    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        app.logger.error(f"Erro na pipeline: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    
@app.route('/list_knowledge/<int:course_id>', methods=['GET'])
def list_knowledge(course_id):
    # Procura na base de dados do Flask/PostgreSQL
    files = KnowledgeFile.query.filter_by(courseid=course_id).all()
    
    return jsonify([
        {"filename": f.filename} 
        for f in files
    ])
    
@app.route('/tutor_toggle', methods=['POST'])
def tutor_toggle():
    data = request.json
    user_id = data.get('user_id')
    active = data.get('active')
    course_id = data.get('course_id')

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
        return jsonify([{"text": "Modo Tutor desligado."}])

    # 2. Lógica de Verificação de Quizzes (O Trigger)
    # Vamos buscar todos os quizzes do curso que o aluno tem acesso e verificar se há tentativas novas para analisar. Se houver, fazemos a análise e preparamos um feedback personalizado.
    quizzes = get_user_quizzes_by_course(course_id, user_id) 
    #app.logger.info(f"Quizzes encontrados para user_id {user_id}: {[quiz['name'] for quiz in quizzes]}")
    
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
        app.logger.info(f"Novos erros encontrados para user_id {user_id}: {novos_erros_encontrados}")
        
        # Agora iteramos sobre a lista de objetos reais
        for error in novos_erros_encontrados:
            
            error_question = error.get('question', 'N/A')
            # get question topic from db
            question_data = MoodleQuizData.query.filter_by(question=error_question).first()
            topic_id = question_data.topic_id if question_data else None
            # atualizar o erro com o topic_id encontrado
            error['topic_id'] = topic_id

            # 2. Guardar o progresso
            # verificar se já existe um registo para este erro específico (mesmo quiz, mesma questão, mesma resposta do aluno)
            progresso_existente = TutorProgress.query.filter_by(
                moodle_user_id=user_id,
                tipo=error.get('tipo'),
                topic_id=error.get('topic_id'),
                question=error.get('question'),
                student_answer=error.get('student_answer'),
                correct_answer=error.get('correct_answer')
            ).first()
            
            if progresso_existente:
                app.logger.info(f"Progresso já existe para este erro específico, não criando duplicado. Detalhes: {progresso_existente}")
                continue
            
            progresso = TutorProgress(
                moodle_user_id=user_id,
                tipo=error.get('tipo'),
                topic_id=error.get('topic_id'),
                question=error.get('question'),
                student_answer=error.get('student_answer'),
                correct_answer=error.get('correct_answer'),
                state="pending"
            )
            db.session.add(progresso)

        db.session.commit() # Commit final de tudo o que foi adicionado

    
        temas_id = list(set([e['topic_id'] for e in novos_erros_encontrados]))
        temas = []
        for topic_id in temas_id:
            topic = Topics.query.filter_by(id=topic_id).first()
            if topic:
                temas.append("<strong>" + topic.name + "</strong>")
        
        msg = f"Hello! I have found some issues in your answers, mainly in the topics: {', '.join(temas[:-1]) + ' and ' + temas[-1] if len(temas) > 1 else temas[0]}. Would you like to review these points with me?"
    else:
        msg = "I have activated the tutor mode, but I didn't find any new attempts to analyze. When you take a test, please let me know!"

    return jsonify({"text": f"{msg}"})

@app.route('/api/get_user_progress/<int:user_id>', methods=['GET'])
def get_user_progress(user_id):
    progress = TutorProgress.query.filter_by(moodle_user_id=user_id).all()
    return jsonify([{"state": p.state, "question": p.question, "topic_id": p.topic_id, "student_answer": p.student_answer, "correct_answer": p.correct_answer} for p in progress])

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
        is_tutor_interaction=data["is_tutor_interaction"],
        time_to_respond=data["time_to_respond"]
    )

    db.session.add(progress)
    db.session.commit()
    
    if not progress:
        return jsonify({"error": "Failed to save Moodle progress"}), 500

    return jsonify({"message": "Moodle progress saved"}), 200

@app.route('/delete_knowledge', methods=['POST'])
def remove_knowledge():
    data = request.json
    #print(f"Received request to delete knowledge with data: {data}")
    filename = data.get('filename')
    course_id = data.get('course_id')
    
    if not filename or not course_id:
        return jsonify({"error": "Faltam dados"}), 400
        
    success = delete_pdf_from_knowledge(filename, course_id)
    
    if success:
        # remover file da base de dados
        file_record = KnowledgeFile.query.filter_by(courseid=course_id, filename=filename).first()
        if file_record:
            db.session.delete(file_record)
            db.session.commit()
        
        return jsonify({"message": f"Ficheiro {filename} removido com sucesso!"})
    return jsonify({"error": "Falha ao remover"}), 500

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

    #app.logger.info(f"Cursos encontrados: {cursos}")
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
        #app.logger.info(f"Quizzes encontrados: {dados_quizzes['quizzes']}")

        for quiz in dados_quizzes['quizzes']:
            q_id = quiz['id']
            q_nome = quiz['name']
            q_last_edit = quiz['timemodified'] # O timestamp do Moodle
            # Converter o inteiro do Moodle para um objeto datetime para podermos comparar
            q_last_edit_dt = datetime.fromtimestamp(q_last_edit)
            
            lista_perguntas = obter_perguntas_do_quiz(q_id)
            app.logger.info(f"Perguntas extraídas do moodle: {lista_perguntas}")             
            # Gerar um hash das perguntas para comparação futura
            questions_hash = gerar_hash_perguntas(lista_perguntas)
    
            quiz_local = obter_quiz_local(q_id)
            
            # 3. Comparar com o que já temos no banco de dados
            if not quiz_ja_processado(q_id):
                app.logger.info(f"A processar perguntas do novo quiz: {q_nome}")
                marcar_quiz_como_processado(q_id, q_nome, questions_hash)            
                   
                lista_final_perguntas = criar_topicos_para_perguntas(lista_perguntas) 
                app.logger.info(f"Perguntas processadas pelo Rasa: {lista_final_perguntas}")

                popular_db(q_id, lista_final_perguntas)
                
            # CASO 2: Quiz existe, mas foi editado pelo professor
            elif q_last_edit_dt > quiz_local.timestamp:
                app.logger.info(f"🔄  Alteração detetada no quiz: {q_nome} (Moodle: {q_last_edit_dt} > Local: {quiz_local.timestamp})")
                
                clean_quiz_data(q_id)
                marcar_quiz_como_processado(q_id, q_nome, questions_hash)

                lista_final_perguntas = criar_topicos_para_perguntas(lista_perguntas) 
                app.logger.info(f"Perguntas processadas pelo Rasa (after reprocessing): {lista_final_perguntas}")

                popular_db(q_id, lista_final_perguntas)
                
            # CASO 3: Quiz existe, mas perguntas foram editadas pelo professor
            elif questions_hash != quiz_local.questions_hash:
                app.logger.info(f"🔄  Alteração detetada nas perguntas do quiz: {q_nome}")
                app.logger.info(f"Hash antigo: {quiz_local.questions_hash} | Hash novo: {questions_hash}")
                clean_quiz_data(q_id)
                marcar_quiz_como_processado(q_id, q_nome, questions_hash)

                lista_final_perguntas = criar_topicos_para_perguntas(lista_perguntas) 
                app.logger.info(f"_Perguntas processadas pelo Rasa (after reprocessing): {lista_final_perguntas}")
                
                popular_db(q_id, lista_final_perguntas)

            # CASO 4: Estão iguais
            else:
                app.logger.info(f"✅  Quiz '{q_nome}' já está atualizado.")
                pass

def tarefa_monitor():
    # Esta função será chamada automaticamente pelo scheduler
    # Criamos o contexto manualmente para que a DB funcione
    with app.app_context():
        try:
            new_quiz_polling()
        except Exception as e:
            app.logger.error(f"Erro no monitor: {e}")

if __name__ == "__main__":
    
    with app.app_context():
        print("🛠️  A verificar/criar tabelas na base de dados...")
        db.create_all() 
        print("✅  Verificação concluída.")
        
    # 1. Lançar o Polling em Background para NÃO bloquear o app.run
    import threading
    def background_tasks():
        wait_for_rasa()
        tarefa_monitor()
        print("✅  Polling inicial concluído em background.")

    threading.Thread(target=background_tasks, daemon=True).start()
    
    # 2. Configuração do agendador
    scheduler.add_job(id='moodle_monitor_job', func=tarefa_monitor, trigger='interval', minutes=60)
    scheduler.init_app(app)
    scheduler.start()

    # 2. ARRANCAR O SERVIDOR (Isto tem de ser rápido!)
    # Se mudaste a porta no compose para 8082, continuas a usar 8080 aqui dentro
    app.run(host='0.0.0.0', port=8080, threaded=True, debug=True, use_reloader=False)