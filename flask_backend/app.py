from time import sleep
from flask import request
from datetime import datetime, timezone, timedelta
import json
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
    
    # Busca contents do Moodle
    moodle_contents = get_moodle_contents(COURSE_ID)
    
    if moodle_contents is None:
        app.logger.error("Failed to fetch Moodle contents.")
    else:
        resources = extract_visible_resources(moodle_contents)
        app.logger.info(f"Recursos autorizados: {resources}")
        # lista com os filenames dos recursos autorizados, ex: ["slides1.pdf", "exercicio2.pdf"]
        filenames = [resource.get("filename") for resource in resources]

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
        temas = list(set([e['pergunta'][:30] + "..." for e in novos_erros_encontrados]))
        msg = f"Hello! I have found some issues in your answers: {', '.join(temas)}. Would you like to review these points with me?"
    else:
        msg = "I have activated the tutor mode, but I didn't find any new attempts to analyze. When you take a test, please let me know!"

    return jsonify({"text": f"{msg}"})

    
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
    
