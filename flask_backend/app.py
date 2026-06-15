import os
#print(f"📂  Conteúdo da pasta /app: {os.listdir('/app')}")
from flask import request
from datetime import datetime, timezone, timedelta
import json
import time
import shutil
import threading
from flask_cors import CORS
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_caching import Cache
from utils import *
from models import *
from knowledge_engine import *

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
# Configuração adaptada para o Docker
config = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_HOST": os.environ.get("REDIS_HOST", "localhost"),
    "CACHE_REDIS_PORT": 6379,
    "CACHE_DEFAULT_TIMEOUT": 300 # 5 minutos por defeito
}
app.config.from_mapping(config)
cache = Cache(app)
CORS(app) # Isto permite que o Moodle aceda à API
scheduler = APScheduler() # Para agendar tarefas periódicas, como verificar quizzes novos

app.config["SQLALCHEMY_DATABASE_URI"] = f'postgresql://{os.getenv("POSTGRES_USER")}:{os.getenv("POSTGRES_PASSWORD")}@db/{os.getenv("POSTGRES_DB")}'
app.config["JWT_SECRET_KEY"] = "super-secret-key"  # Change in production!
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)  # For database migrations
jwt = JWTManager(app)

# No topo do ficheiro, cria um set para guardar os cursos em processamento
active_syncs = set()


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
    user_id = data.get('user_id')    
    course_id = data.get('course_id')
    user_message = data.get('message', '')
    length_preference = data.get('length_preference', 'detailed') # Pode ser "detailed" ou "concise"
    tone_preference = data.get('tone_preference', 'empathetic') # Pode ser "encouraging" ou "neutral"
    moodle_token = data.get('token')
    moodle_url = data.get('moodle_url')
    isTutorMode = data.get('tutor_mode', False)
    is_button = data.get('is_button', False)
    print(f"Received chat request: message='{user_message}', tutor_mode={isTutorMode}, is_button={is_button}")
    is_teacher = data.get('is_teacher', False)
    if moodle_url == "http://localhost":
        moodle_url = "http://host.docker.internal"
        
    if user_message == '': # Se a mensagem for vazia ou só espaços, não enviamos para o Rasa
        app.logger.warning("Received empty message. Ignoring.")
        return jsonify([{"text": "I didn't receive any message. Please try sending your message again."}])
    
    # 💡 A MAGIA ACONTECE AQUI: Cria uma chave única para a cache baseada no curso e ID do utilizador
    cache_key = f"moodle_user_{course_id}_{user_id}"
    info_utilizador = cache.get(cache_key)

    if not info_utilizador:
        # Se não estiver na cache, vai buscar ao Moodle e guarda na cache
        app.logger.info(f"Cache MISS para o utilizador {user_id}. Chamando API do Moodle.")
        info_utilizador = get_moodle_user_data(user_id, moodle_token, moodle_url)
        if info_utilizador:
            cache.set(cache_key, info_utilizador, timeout=600) # Guarda por 10 minutos
    else:
        app.logger.info(f"Cache HIT para o utilizador {user_id}. Dados carregados da memória.")
    
    user_firstname = info_utilizador.get("name") if info_utilizador else f"user_{user_id}"     
    print(f"📮  --> Received message for {user_firstname} in course_id: {course_id} with Moodle URL: {moodle_url} and token: {moodle_token[:10]}...")
    
    # Busca os dados reais no Moodle
    user_email = info_utilizador.get("email") if info_utilizador else "EMAIL@EXAMPLE.COM"
    username = info_utilizador.get("name") if info_utilizador else "there"
    
    # Define o papel do utilizador para personalizar as respostas do Rasa
    session_init_rasa(user_email, username, "teacher" if is_teacher else "student")
    
    # Limpa a mensagem do utilizador para evitar problemas de formatação ou segurança
    cleaned_message = clean_user_input(user_message)
    #app.logger.info(f"Cleaned message to send to LLM: {cleaned_message}")
    
    if cleaned_message == "":
        # houve algum problema na limpeza da mensagem, ou seja, a mensagem era composta apenas por caracteres indesejados. Neste caso, respondemos ao utilizador pedindo para reformular a mensagem.
        app.logger.warning("Cleaned message is empty after cleaning. Prompting user to reformulate.")
    
        if isTutorMode:
            # 1. Criar uma chave única combinando o ID do utilizador e o ID do curso
            # (Nota: certifica-te se estás a usar a variável 'moodle_id' ou 'user_id' no teu código)
            cache_key_rasa = f"rasa_topics_{user_id}_{course_id}"
            cached_rasa = cache.get(cache_key_rasa)

            if cached_rasa:
                app.logger.info(f"Cache HIT para Rasa (Tópicos) - User: {user_id}, Course: {course_id}")
                # Desempacota o tuplo guardado na cache
                bot_reply, buttons = cached_rasa
            else:
                app.logger.info(f"Cache MISS para Rasa (Tópicos). A chamar o Rasa...")
                
                # Se não estiver na cache, faz a chamada normal ao Rasa
                payload = {
                    "sender": user_email,
                    "message": '/show_topics',
                    "metadata": {
                        "user_id": user_id, 
                        "course_id": course_id,
                        "moodle_url": moodle_url,
                        "moodle_token": moodle_token
                    }
                }
                bot_reply, buttons = call_rasa(payload)
                
                cache.set(cache_key_rasa, (bot_reply, buttons), timeout=300)
            
            if not buttons:
                return jsonify([{"text": "Great job! 🎉 You have reviewed all topics!"}])
            return jsonify([{"text": f"You are in tutor mode.</br>Please select a topic to review.</br>{bot_reply.strip()}"}, {"buttons": buttons}])
        
        else:
            return jsonify([{"text": "I couldn't understand your message. Please try reformulating it."}])
    
    user_message = cleaned_message
    
    cache_key = f"moodle_contents_{course_id}_{user_id}"
    cached_rasa = cache.get(cache_key)
    if not cached_rasa:
        app.logger.info(f"Cache MISS para Moodle contents - User: {user_id}, Course: {course_id}. Fetching from Moodle...")
        moodle_contents, moodle_contents_names, youtube_ids = get_moodle_contents_and_videos(course_id, moodle_url, moodle_token)
        cache.set(cache_key, (moodle_contents, moodle_contents_names, youtube_ids), timeout=1800) # Guarda por 30 minutos
    else:
        app.logger.info(f"Cache HIT para Moodle contents - User: {user_id}, Course: {course_id}. Loaded from cache.")
        moodle_contents, moodle_contents_names, youtube_ids = cached_rasa

    if moodle_contents_names == None:
        app.logger.error("Failed to fetch Moodle contents.")
        return jsonify([{"text": "There is no content available for this course or an error occurred while fetching the content. Please try again later."}])
    elif moodle_contents_names == []:
        app.logger.warning("No contents found for this course.")
        return jsonify([{"text": "There is no content available for this course. Please check back later or contact your instructor."}])
    else:
        print(f"📂  Moodle contents for course {course_id}: {moodle_contents_names}, {youtube_ids}")
        print(f"   moodle_contents: {moodle_contents}")
        resources = extract_visible_resources(moodle_contents)
        # Se resources já são os autorizados, basta extrair os nomes:
        authorized_resources = [res.get("filename") for res in resources if res.get("filename")]
        content_mappings = {res.get("filename"): res.get("display_name", res.get("filename")) for res in resources if res.get("filename")}

        if not authorized_resources:
            app.logger.warning("No authorized resources found for this course.")
            #return jsonify([{"text": "You don't have access to any resources for this course. Please check back later or contact your instructor."}])
        else:
            print(f"🔑  Authorized resources for user {user_id} in course {course_id}: {authorized_resources}")
            print(f"🔑  Content mappings for user {user_id} in course {course_id}: {content_mappings}")

    # check if user is in tutor mode
    user = MoodleUsers.query.filter_by(moodle_id=user_id).first()

    if user and isTutorMode:
        if is_button:
            app.logger.info(f"\nCHAT: User {user_id} is in tutor mode and clicked a button.")
            print(f"button payload received: {user_message}")
            current_time = datetime.now(timezone.utc).isoformat() 
            
            payload = {
                "sender": user_email,
                "message": "/analyze_progress",
                "metadata": {
                    "username": username,
                    "input_time":current_time,
                    "user_id": user_id,
                    "authorized_resources": authorized_resources,
                    "content_mappings": content_mappings,
                    "tutor_mode": True,
                    "topic_id": user_message,
                    "course_id": course_id,
                    "is_teacher": is_teacher,
                    "moodle_url": moodle_url,
                    "moodle_token": moodle_token,
                    "length_preference": length_preference,
                    "tone_preference": tone_preference
                }
            }
            bot_reply, buttons = call_rasa(payload)
            
            cache_key_rasa = f"rasa_topics_{user_id}_{course_id}"
            payload = {
                "sender": user_email,
                "message": '/show_topics',
                "metadata": {
                    "user_id": user_id, 
                    "course_id": course_id,
                    "moodle_url": moodle_url,
                    "moodle_token": moodle_token
                }
            }
            cache_bot_reply, cache_buttons = call_rasa(payload)
            cache.set(cache_key_rasa, (cache_bot_reply, cache_buttons), timeout=300)

            return jsonify([{"text": f"{bot_reply.strip()}"}, {"buttons": buttons}])

        else:            
            # do not send the message to Rasa, just reply that the user is in tutor mode and should select a topic by sending the corresponding number
            app.logger.info(f"User {user_id} is in tutor mode but sent a non-numeric message. Prompting to select a topic.")
            cache_key_rasa = f"rasa_topics_{user_id}_{course_id}"
            cached_rasa = cache.get(cache_key_rasa)

            if cached_rasa:
                app.logger.info(f"Cache HIT para Rasa (Tópicos) - User: {user_id}, Course: {course_id}")
                # Desempacota o tuplo guardado na cache
                bot_reply, buttons = cached_rasa
            else:
                app.logger.info(f"Cache MISS para Rasa (Tópicos). A chamar o Rasa...")
                
                # Se não estiver na cache, faz a chamada normal ao Rasa
                payload = {
                    "sender": user_email,
                    "message": '/show_topics',
                    "metadata": {
                        "user_id": user_id, 
                        "course_id": course_id,
                        "moodle_url": moodle_url,
                        "moodle_token": moodle_token
                    }
                }
                bot_reply, buttons = call_rasa(payload)
                cache.set(cache_key_rasa, (bot_reply, buttons), timeout=300)
            
            if not buttons:
                return jsonify([{"text": " Great job! 🎉 You have reviewed all topics!"}])
                    
            return jsonify([{"text": f"You are in tutor mode.</br>Please select a topic to review.</br>{bot_reply.strip()}"}, {"buttons": buttons}])
            
    else:
        app.logger.info(f"User {user_id} is in normal mode.")
        app.logger.info(f"Cleaned message to send to LLM: {user_message}")
        
        current_time = datetime.now(timezone.utc).isoformat()
        payload = {
            "sender": user_email,
            "message": user_message,
            "metadata": {
                "username": username, 
                "input_time":current_time, 
                "user_id": user_id, 
                "authorized_resources": authorized_resources, 
                "tutor_mode": False, 
                "course_id": course_id, 
                "is_teacher": is_teacher,
                "length_preference": length_preference,
                "tone_preference": tone_preference,
                "content_mappings": content_mappings
            }
        }

        bot_reply, buttons = call_rasa(payload)            
        return jsonify([{"text": f"{bot_reply.strip()}"}])


@app.route('/process_knowledge', methods=['POST'])
def process_knowledge():
    files = request.files.getlist('files[]')
    video_files = request.files.getlist('video_files[]')
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
            
            # ver se já existe um registo deste ficheiro para este curso na base de dados, se não existir, criar um novo registo
            existing_file = KnowledgeFiles.query.filter_by(course_id=course_id, filename=file.filename).first()
            if existing_file:
                app.logger.info(f"Ficheiro {file.filename} já existe na base de dados para o curso {course_id}, não criando duplicado.")
                continue
            else: 
                new_file = KnowledgeFiles(
                    course_id=course_id,
                    filename=file.filename
                )
                db.session.add(new_file)
                db.session.commit()

        # 3. Correr a pipeline
        success = process_pdfs(pdf_folder=temp_dir, youtube_ids=[], course_id=course_id)

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
    
def background_sync(app, course_id, pdf_folder, moodle_token, moodle_url):
    """Função que corre em paralelo para sincronizar PDFs e transcrever vídeos do YouTube."""
    print(f"--- Iniciando sincronização completa para o curso {course_id} ---")
    
    with app.app_context():
        try:
            # 1. Obter a estrutura do curso via Web Service
            ws_url = f"{moodle_url}/webservice/rest/server.php"
            params = {
                'wstoken': moodle_token,
                'wsfunction': 'core_course_get_contents',
                'moodlewsrestformat': 'json',
                'courseid': course_id
            }
            
            response = requests.get(ws_url, params=params)
            sections = response.json()

            if not isinstance(sections, list):
                print(f"Erro ao obter conteúdos do curso {course_id}: {sections}")
                return

            # Criar pasta temporária para PDFs e Áudios
            os.makedirs(pdf_folder, exist_ok=True)

            found_files = 0
            youtube_ids = set() # Usamos set para evitar IDs duplicados na mesma secção

            for section in sections:
                for module in section.get('modules', []):
                    
                    # ==========================================
                    # FLUXO A: DETEÇÃO DE PDFs (O teu código original)
                    # ==========================================
                    if module.get('modname') == 'resource':
                        for content in module.get('contents', []):
                            if content.get('mimetype') == 'application/pdf':
                                file_url = content.get('fileurl')
                                file_name = content.get('filename')
                                
                                separator = '&' if '?' in file_url else '?'
                                download_url = f"{file_url}{separator}token={moodle_token}"
                                file_path = os.path.join(pdf_folder, file_name)
                                
                                r = requests.get(download_url, stream=True)
                                if r.status_code == 200:
                                    content_type = r.headers.get('Content-Type', '')
                                    if 'application/pdf' in content_type:
                                        with open(file_path, 'wb') as f:
                                            for chunk in r.iter_content(chunk_size=8192):
                                                f.write(chunk)
                                        found_files += 1
                                        
                                        file_record = KnowledgeFiles.query.filter_by(course_id=course_id, filename=file_name).first()
                                        if not file_record:
                                            new_file = KnowledgeFiles(course_id=course_id, filename=file_name)
                                            db.session.add(new_file)
                                            db.session.commit()
                                            print(f"PDF guardado na DB: {file_name}")
                    
                    # ==========================================
                    # FLUXO B: DETEÇÃO DE VÍDEOS DO YOUTUBE
                    # ==========================================
                    html_text = ""
                    if 'intro' in module:
                        html_text += module['intro']
                    if 'description' in module:
                        html_text += module['description']
                    
                    # Se for uma página nativa do moodle, o texto rico está dentro de contents
                    if 'contents' in module:
                        for content in module['contents']:
                            if 'content' in content:
                                html_text += content['content']
                    
                    # Se encontrarmos texto HTML, corremos o Regex à procura do YouTube
                    if html_text:
                        print(f"----- html_text: {html_text}")
                        found_ids = re.findall(YOUTUBE_REGEX, html_text)
                        for yt_id in found_ids:
                            video_record = KnowledgeVideos.query.filter_by(course_id=course_id, video_id=yt_id).first()
                            if video_record:
                                print(f"Vídeo {yt_id} já foi transcrito anteriormente. A ignorar.")
                                continue
                                
                            print(f"-> Novo vídeo detetado [{yt_id}]. A iniciar extração de áudio...")
                            youtube_ids.add(yt_id)
                            # Guardar na BD que o vídeo já está feito
                            new_video = KnowledgeVideos(course_id=course_id, video_id=yt_id)
                            db.session.add(new_video)
                            db.session.commit()
                            print(f"✓ Transcrição do vídeo {yt_id} concluída e guardada.")

            print(f"Varrimento concluído. PDFs novos: {found_files} | IDs de Vídeo detetados: {len(youtube_ids)}")

            # Processamento dos PDFs na Knowledge Base
            # Processamento e Transcrição dos Vídeos detetados
            if found_files > 0:
                print(f"A processar {found_files} PDFs na Knowledge Base...")
                process_pdfs(pdf_folder=pdf_folder, youtube_ids=youtube_ids, course_id=course_id)

        except Exception as e:
            print(f"Erro crítico durante a sincronização: {str(e)}")
            
        finally:
            # Libertar o lock do curso
            if 'active_syncs' in globals() and course_id in active_syncs:
                active_syncs.remove(course_id)
            
            # Limpeza da pasta temporária
            if os.path.exists(pdf_folder):
                shutil.rmtree(pdf_folder, ignore_errors=True)
                print(f"Pasta temporária {pdf_folder} limpa com sucesso.")

         
@app.route('/populate_with_moodle_contents/<int:course_id>', methods=['POST'])
def populate_with_moodle_contents(course_id):
    # 1. Trancar imediatamente se já houver um sync ativo (Prevenção de concorrência)
    if course_id in active_syncs:
        print(f"Sync rejeitado: Curso {course_id} já está a ser processado.")
        return jsonify({"message": "Sincronização já em curso para este curso."}), 200
    
    # Registamos logo que este curso está ocupado
    active_syncs.add(course_id) # Ou active_syncs[course_id] = True dependendo do tipo
    
    auth_header = request.headers.get('Authorization')
    moodle_token = auth_header.split(" ")[1] if auth_header else None
    
    # 2. Pegamos o URL do corpo do JSON
    data = request.get_json()
    # Se por algum motivo o JSON falhar, usamos o teu localhost como fallback (útil para dev)
    moodle_url = data.get('moodle_url')
    if moodle_url == "http://localhost":
        moodle_url = "http://host.docker.internal"

    print(f"Sync solicitado: Curso {course_id} | URL: {moodle_url} | Token: {moodle_token[:10]}...")
    
    # IMPORTANTE: Guardar ou atualizar o token deste curso na DB para o polling saber usá-lo depois
    client = ClientConfig.query.filter_by(course_id=course_id).first()
    print(f"Cliente encontrado na DB para course_id {course_id}: {client}")
    if not client:
        client = ClientConfig(
            course_id=course_id, 
            moodle_token=moodle_token,
            moodle_url=moodle_url
        )
        db.session.add(client)
    else:
        client.moodle_token = moodle_token # Atualiza se o cliente mudou o token
        client.moodle_url = moodle_url # Atualiza se o cliente mudou a URL
    db.session.commit()
    
    # 2. Verificamos se já existem conteúdos na DB para este curso
    conteudo_existente = KnowledgeFiles.query.filter_by(course_id=course_id).first()
    
    if conteudo_existente:
        print(f"Sincronização abortada: O curso {course_id} já tem dados.")
        return jsonify({
            "message": "O curso já tem conteúdos na Knowledge Base. Nada a fazer.",
            "status": "already_populated"
        }), 200

    pdf_folder = os.path.join('temp_uploads', str(course_id))
    
    # Passamos a app_instance para a thread
    thread = threading.Thread(
        target=background_sync, 
        args=(app, course_id, pdf_folder, moodle_token, moodle_url) # <--- Adicionado app_instance
    )
    thread.start()

    return jsonify({"message": "Sincronização iniciada."}), 202

@app.route('/list_knowledge/<int:course_id>', methods=['GET'])
def list_knowledge(course_id):
    # Procura na base de dados do Flask/PostgreSQL
    files = KnowledgeFiles.query.filter_by(course_id=course_id).all()
    
    return jsonify([
        {"filename": f.filename} 
        for f in files
    ])
    
@app.route('/tutor_toggle', methods=['POST'])
def tutor_toggle():
    data = request.json
    user_id = data.get('user_id')
    is_active = data.get('active')
    course_id = data.get('course_id')
    moodle_token = data.get('token')
    moodle_url = data.get('moodle_url')
    is_teacher = data.get('is_teacher', False)
    if moodle_url == "http://localhost":
        moodle_url = "http://host.docker.internal"
        
    cache_key = f"moodle_user_{course_id}_{user_id}"
    info_utilizador = cache.get(cache_key)

    if not info_utilizador:
        # Se não estiver na cache, vai buscar ao Moodle e guarda na cache
        app.logger.info(f"Cache MISS para o utilizador {user_id}. Chamando API do Moodle.")
        info_utilizador = get_moodle_user_data(user_id, moodle_token, moodle_url)
        if info_utilizador:
            cache.set(cache_key, info_utilizador, timeout=600) # Guarda por 10 minutos
    else:
        app.logger.info(f"Cache HIT para o utilizador {user_id}. Dados carregados da memória.")

    # Busca os dados reais no Moodle
    user_email = info_utilizador.get("email") if info_utilizador else "EMAIL@EXAMPLE.COM"
    username = info_utilizador.get("name") if info_utilizador else "there"
    print(f"📮  --> Received message for {username} in course_id: {course_id} with Moodle URL: {moodle_url} and token: {moodle_token[:10]}...")
    
    session_init_rasa(user_email, username, "teacher" if is_teacher else "student") # Define o papel do utilizador para personalizar as respostas do Rasa

    if not is_active:
        app.logger.info(f"Modo Tutor desligado para user_id: {user_id}")
        return jsonify([{"text": "Modo Tutor desligado."}])

    # 2. Lógica de Verificação de Quizzes (O Trigger)
    # Vamos buscar todos os quizzes do curso que o aluno tem acesso e verificar se há tentativas novas para analisar. Se houver, fazemos a análise e preparamos um feedback personalizado.
    quizzes = get_user_quizzes_by_course(course_id, user_id, moodle_url, moodle_token) 
    #app.logger.info(f"Quizzes encontrados para user_id {user_id}: {[quiz['name'] for quiz in quizzes]}")
    
    if not quizzes:
        app.logger.warning(f"Nenhum quiz encontrado para o curso {course_id} e user_id {user_id}.")
        return jsonify([{"text": "I have activated the tutor mode, but I couldn't find any quizzes to analyze. When you take a test, please let me know!"}])
    
    novos_erros_encontrados = []
    
    for quiz in quizzes:
        quiz_id = quiz['id']
        attempt_id = get_last_attempt_id(quiz_id, user_id, moodle_url, moodle_token)
        
        if attempt_id == None:
            continue
        
        app.logger.info(f"Verificando quiz_id: {quiz_id} para user_id: {user_id} com attempt_id: {attempt_id}")
        
        # Verificar se já analisámos esta tentativa
        analise = MoodleQuizAnalysis.query.filter_by(
            course_id=course_id,
            user_moodle_id=user_id, 
            quiz_id=quiz_id
        ).first()
        print(f"Análise existente para quiz_id {quiz_id} e user_id {user_id}: {analise}")

        msg = "I have activated the tutor mode, but I didn't find any new attempts to analyze. When you take a test, please let me know!"
        if not analise: # not pending and not reviewed, ou seja, nunca analisámos este quiz para este aluno
            # Temos uma tentativa nova! Analisar...
            review_data = get_quiz_attempt_review(attempt_id, moodle_url, moodle_token)
            erros = analisar_desempenho_aluno(review_data) # A tua função BS4
            if erros:
                novos_erros_encontrados.extend(erros)
            
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
                        course_id=course_id,
                        user_moodle_id=user_id,
                        tipo=error.get('tipo'),
                        quiz_id=question_data.quiz_id if question_data else None,
                        topic_id=error.get('topic_id'),
                        question=error.get('question'),
                        student_answer=error.get('student_answer'),
                        correct_answer=error.get('correct_answer'),
                    ).first()
                    
                    if progresso_existente:
                        progresso_existente.last_attempt_id = attempt_id
                        #app.logger.info(f"Progresso já existe para este erro específico, não criando duplicado. Detalhes: {progresso_existente}")
                        continue
                    
                    progresso = TutorProgress(
                        course_id=course_id,
                        last_attempt_id=attempt_id,
                        user_moodle_id=user_id,
                        tipo=error.get('tipo'),
                        quiz_id=question_data.quiz_id if question_data else None,
                        topic_id=error.get('topic_id'),
                        question=error.get('question'),
                        student_answer=error.get('student_answer'),
                        correct_answer=error.get('correct_answer'),
                        question_feedback=error.get('question_feedback'),
                        state="pending"
                    )
                    db.session.add(progresso)

                analise = MoodleQuizAnalysis(
                    user_moodle_id=user_id, 
                    quiz_id=quiz_id, 
                    last_attempt_id=attempt_id,
                    course_id=course_id,
                    state="pending"
                )
                db.session.add(analise)
                db.session.commit()

            
                temas_id = list(set([e['topic_id'] for e in novos_erros_encontrados]))
                temas = []
                for topic_id in temas_id:
                    topic = Topics.query.filter_by(id=topic_id).first()
                    if topic:
                        temas.append("<strong>" + topic.name + "</strong>")
                
                msg = f"Hello! I have found some issues in your answers, mainly in the topics: {', '.join(temas[:-1]) + ' and ' + temas[-1] if len(temas) > 1 else temas[0]}. Would you like to review these points with me?<br/>"
            else:
                return jsonify([{"text": msg}])
        else:
            if analise.last_attempt_id != attempt_id:
                # Houve uma nova tentativa desde a última análise, atualizar o registo para permitir nova análise
                app.logger.info(f"Nova tentativa detectada para quiz_id {quiz_id} e user_id {user_id}. Atualizando análise para permitir nova revisão.")
                analise.state = "pending"
                analise.last_attempt_id = attempt_id
                db.session.commit()
                
                # eliminar registos de progresso pendentes relacionados a esta tentativa antiga, para evitar confusão com os novos erros que vamos analisar agora
                progresso_existente = TutorProgress.query.filter_by(
                            last_attempt_id=attempt_id,
                            course_id=course_id,
                            user_moodle_id=user_id,
                        ).first()
                if progresso_existente:
                    db.session.delete(progresso_existente)
                    db.session.commit()
                
                # Temos uma tentativa nova! Analisar...
                review_data = get_quiz_attempt_review(attempt_id, moodle_url, moodle_token)
                erros = analisar_desempenho_aluno(review_data) # A tua função BS4
                if erros:
                    novos_erros_encontrados.extend(erros)
                
                # Preparar Resposta para o Aluno
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

                        # Guardar o progresso                                                
                        progresso = TutorProgress(
                            course_id=course_id,
                            last_attempt_id=attempt_id,
                            user_moodle_id=user_id,
                            tipo=error.get('tipo'),
                            quiz_id=question_data.quiz_id if question_data else None,
                            topic_id=error.get('topic_id'),
                            question=error.get('question'),
                            student_answer=error.get('student_answer'),
                            correct_answer=error.get('correct_answer'),
                            question_feedback=error.get('question_feedback'),
                            state="pending"
                        )
                        db.session.add(progresso)

                    db.session.commit()

                
                    temas_id = list(set([e['topic_id'] for e in novos_erros_encontrados]))
                    temas = []
                    for topic_id in temas_id:
                        topic = Topics.query.filter_by(id=topic_id).first()
                        if topic:
                            temas.append("<strong>" + topic.name + "</strong>")
                    
                    msg = f"Hello! I have found some issues in your answers, mainly in the topics: {', '.join(temas[:-1]) + ' and ' + temas[-1] if len(temas) > 1 else temas[0]}. Would you like to review these points with me?<br/>"
                    
                    
            app.logger.info(f"Quiz_id: {quiz_id} para user_id: {user_id} já foi analisado anteriormente com estado '{analise.state}'.")
    
            temas_id = list(set([p.topic_id for p in TutorProgress.query.filter_by(
                                                        course_id=course_id, 
                                                        user_moodle_id=user_id, 
                                                        state="pending")
                                                    .all()]))
            temas = []
            for topic_id in temas_id:
                topic = Topics.query.filter_by(id=topic_id).first()
                if topic:
                    temas.append("<strong>" + topic.name + "</strong>")
            
            if temas:
                msg = f"Hello! I have found some issues in your answers, mainly in the topics: {', '.join(temas[:-1]) + ' and ' + temas[-1] if len(temas) > 1 else temas[0]}.  Would you like to review these points with me?<br/>"
                    
    cache_key_rasa = f"rasa_topics_{user_id}_{course_id}"
    
    payload = {
        "sender": user_email,
        "message": '/show_topics',
        "metadata": {
            "user_id": user_id, 
            "course_id": course_id,
            "moodle_url": moodle_url,
            "moodle_token": moodle_token
        }
    }
    bot_reply, buttons = call_rasa(payload)
    cache.set(cache_key_rasa, (bot_reply, buttons), timeout=300)
    
    return jsonify([{"text": f"{msg}\n\n{bot_reply.strip()}"}, {"buttons": buttons}])
            

@app.route('/api/get_user_progress', methods=['GET'])
def get_user_progress():
    user_id = request.args.get('user_id')
    course_id = request.args.get('course_id')
    moodle_url = request.args.get('moodle_url')
    moodle_token = request.args.get('moodle_token')
    all_questions = request.args.get('all_questions', 'false').lower() == 'true' # Se for true, traz todas as questões, se for false, só as pendentes
    
    # Validação simples de segurança se os parâmetros não vierem
    if not user_id or not course_id:
        return jsonify({"error": "Missing parameters"}), 400
    
    if all_questions:
        progress = TutorProgress.query.filter_by(
            course_id=course_id,
            user_moodle_id=user_id
        ).all()
        
        quiz_id = progress[0].quiz_id if progress else None
        if quiz_id:
            # update da analise
            analise = MoodleQuizAnalysis.query.filter_by(
                course_id=course_id,
                user_moodle_id=user_id, 
                quiz_id=quiz_id,
                state="pending"
            ).first()
            if analise:
                analise.state = "reviewed"
                attempt_id = get_last_attempt_id(quiz_id, user_id, moodle_url, moodle_token)
                analise.last_attempt_id = attempt_id
                
                db.session.commit()
                app.logger.info(f"Análise do quiz_id {quiz_id} atualizada para 'reviewed' para o usuário {user_id} no curso {course_id}.")
        else:
            app.logger.warning(f"Não foi possível encontrar o quiz_id para atualizar a análise do usuário {user_id} no curso {course_id}.")
            
    else:
        progress = TutorProgress.query.filter_by(
            course_id=course_id,
            user_moodle_id=user_id,
            state="pending"
        ).all()
        
    return jsonify([{"quiz_id": p.quiz_id, "question": p.question, "topic_id": p.topic_id, "student_answer": p.student_answer, "correct_answer": p.correct_answer} for p in progress])

@app.route('/api/get_user_progress_by_topic', methods=['GET'])
def get_user_progress_by_topic():
    user_id = request.args.get('user_id')
    course_id = request.args.get('course_id')
    topic_id = request.args.get('topic_id')

    if not user_id or not topic_id or not course_id:
        return jsonify({"error": "Missing parameters"}), 400

    progress = TutorProgress.query.filter_by(
        course_id=course_id,
        user_moodle_id=user_id,
        topic_id=topic_id,
        state="pending"
    ).all()
        
    return jsonify([{"id": p.id, "state": p.state, "question": p.question, "student_answer": p.student_answer, "correct_answer": p.correct_answer} for p in progress])

@app.route('/api/update_progress_state', methods=['POST'])
def update_progress_state():
    ids = request.args.get('ids', []) # lista de ids
    new_state = request.args.get('new_state')
    print(f"Updating progress state for IDs: {ids} to new state: {new_state}")

    if not ids or not new_state:
        return jsonify({"error": "Missing parameters"}), 400

    for id in ids:
        progress = TutorProgress.query.filter_by(
            id=id
        ).first()
        
        if not progress:
            return jsonify({"error": "Progress record not found"}), 404
        
        progress.state = new_state
        
    db.session.commit()
    
    return jsonify({"message": "Progress state updated successfully"})

@app.route('/api/get_user_history/<course_id>', methods=['GET'])
def get_user_history(course_id):
    history = MoodleUserHistory.query.filter_by(
        course_id=course_id,
        is_tutor_interaction=False
    ).all()
    return jsonify([{"user_id": h.user_moodle_id, "question": h.question, "pdfs": h.pdfs, "timestamp": h.timestamp} for h in history])

@app.route("/api/get_topics", methods=["GET"])
def get_topics():
    topics = Topics.query.all()
    return jsonify([{"id": topic.id, "name": topic.name} for topic in topics])

@app.route("/api/get_topics_from_ids", methods=["GET"])
def get_topics_from_ids():
    data = request.json
    topics_ids = data.get("topics_ids", [])
    if not topics_ids:
        return jsonify({"error": "No topic IDs provided"}), 400
    
    topics = Topics.query.filter(Topics.id.in_(topics_ids)).all()
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

@app.route("/api/save_student_moodle_messages", methods=["POST"])
def save_student_moodle_messages():
    data = request.json
    user_id = data.get("user_id")
    app.logger.info(f"Saving Moodle progress for user_id: {user_id} with data: {data}")
    
    progress = MoodleUserHistory(
        course_id=data["course_id"],
        user_moodle_id=int(user_id),
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
        file_record = KnowledgeFiles.query.filter_by(course_id=course_id, filename=filename).first()
        if file_record:
            db.session.delete(file_record)
            db.session.commit()
            return jsonify({"message": f"Ficheiro {filename} removido com sucesso!"})
        
    return jsonify({"error": "Falha ao remover"}), 500

def new_quiz_polling():
    app.logger.info(f"[{time.strftime('%H:%M:%S')}] A iniciar polling a novos quizzes...")
    function = "core_course_get_courses"
    
    # 1. Buscar todos os tokens ativos na tua DB
    clientes = ClientConfig.query.all() 
    if not clientes:
        app.logger.warning("Nenhum cliente encontrado na base de dados para o polling de quizzes.")
        return None

    for cliente in clientes:
        token = cliente.moodle_token
        moodle_url = cliente.moodle_url
        print(f"Polling para course_id {cliente.course_id} usando token {token[:10]}...") # Log para debug, mostra só os primeiros caracteres do token por segurança
        #print(f"URL do Moodle para polling: {moodle_url}")
        
        # 2. Fazer o polling para ESTE cliente específico
        cursos = call_moodle(moodle_url, token, function)
        if not cursos or 'exception' in cursos:
            app.logger.error("Erro ao obter cursos.")
            return None
        
        #app.logger.info(f"Cursos encontrados: {cursos}")
        course_ids = [c['id'] for c in cursos]
        
        # 2. Obter todos os quizzes destes cursos (em blocos para evitar URLs gigantes)
        # O Moodle espera parâmetros no formato: courseids[0]=id1, courseids[1]=id2...
        params = {}
        for i, cid in enumerate(course_ids):
            params[f'courseids[{i}]'] = cid
            
        function = "mod_quiz_get_quizzes_by_courses"
            
        try:
            dados_quizzes = call_moodle(moodle_url, token, function, params)
        except Exception as e:
            app.logger.error(f"Erro na chamada à API: {e}")
            dados_quizzes = None
    
        if dados_quizzes and 'quizzes' in dados_quizzes:
            app.logger.info(f"Quizzes encontrados: {dados_quizzes['quizzes']}")

            for quiz in dados_quizzes['quizzes']:
                course_id = quiz['course']
                q_id = quiz['id']
                q_nome = quiz['name']
                q_last_edit = quiz['timemodified'] # O timestamp do Moodle
                # Converter o inteiro do Moodle para um objeto datetime para podermos comparar
                q_last_edit_dt = datetime.fromtimestamp(q_last_edit)
                
                lista_perguntas = obter_perguntas_do_quiz(q_id, moodle_url, token)
                app.logger.info(f"Perguntas extraídas do moodle: {lista_perguntas}")             
                # Gerar um hash das perguntas para comparação futura
                questions_hash = gerar_hash_perguntas(lista_perguntas)
        
                quiz_local = obter_quiz_local(course_id, q_id)
                
                # 3. Comparar com o que já temos no banco de dados
                if not quiz_ja_processado(course_id, q_id):
                    app.logger.info(f"A processar perguntas do novo quiz: {q_nome}")
                    marcar_quiz_como_processado(course_id, q_id, q_nome, questions_hash)            
                    
                    lista_final_perguntas = criar_topicos_para_perguntas(lista_perguntas) 
                    app.logger.info(f"Perguntas processadas pelo Rasa: {lista_final_perguntas}")

                    popular_db(course_id, q_id, lista_final_perguntas)
                    
                # CASO 2: Quiz existe, mas foi editado pelo professor
                elif q_last_edit_dt > quiz_local.last_updated:
                    app.logger.info(f"🔄  Alteração detetada no quiz: {q_nome} (Moodle: {q_last_edit_dt} > Local: {quiz_local.last_updated})")
                    
                    clean_quiz_data(course_id, q_id)
                    marcar_quiz_como_processado(course_id, q_id, q_nome, questions_hash)

                    lista_final_perguntas = criar_topicos_para_perguntas(lista_perguntas) 
                    app.logger.info(f"Perguntas processadas pelo Rasa (after reprocessing): {lista_final_perguntas}")

                    popular_db(course_id, q_id, lista_final_perguntas)
                    
                # CASO 3: Quiz existe, mas perguntas foram editadas pelo professor
                elif questions_hash != quiz_local.questions_hash:
                    app.logger.info(f"🔄  Alteração detetada nas perguntas do quiz: {q_nome}")
                    app.logger.info(f"Hash antigo: {quiz_local.questions_hash} | Hash novo: {questions_hash}")
                    clean_quiz_data(course_id, q_id)
                    marcar_quiz_como_processado(course_id, q_id, q_nome, questions_hash)

                    lista_final_perguntas = criar_topicos_para_perguntas(lista_perguntas) 
                    app.logger.info(f"_Perguntas processadas pelo Rasa (after reprocessing): {lista_final_perguntas}")
                    
                    popular_db(course_id, q_id, lista_final_perguntas)

                # CASO 4: Estão iguais
                else:
                    app.logger.info(f"✅  Quiz '{q_nome}' já está atualizado.")
                    
            return True

def tarefa_monitor():
    # Esta função será chamada automaticamente pelo scheduler
    # Criamos o contexto manualmente para que a DB funcione
    with app.app_context():
        try:
            while True:
                app.logger.info("A aguardar alguns segundos antes do polling para dar tempo ao trigger do Moodle...")
                time.sleep(20)
                #response = new_quiz_polling()
                #if response != None:
                #    app.logger.info("Polling de quizzes concluído com sucesso.")
                #    break
        except Exception as e:
            app.logger.error(f"Erro no monitor: {e}")

if __name__ == "__main__":
    
    with app.app_context():
        print("🛠️  A verificar/criar tabelas na base de dados...")
        db.create_all() 
        print("✅  Verificação concluída.")
        # comment if you don't want to populate the database with initial data every time you start the app
        populate_database()
        
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