import json
import logging
import time
from flask import Flask, jsonify
import hashlib
import os
from googleapiclient.discovery import build
import requests
import hashlib
import json
import os
import random
from datetime import datetime, timedelta
from flask_apscheduler import APScheduler
from bs4 import BeautifulSoup
from models import *
from seed_db import qa_bank

#RASA_URL = "http://rasa:5005/webhooks/rest/webhook"
RASA_BASE_URL = "http://rasa:5005"

# --- SCRIPT DE POPULAÇÃO ---
def populate_database(course_id=2):
    print("A iniciar a população do MoodleUsers e MoodleUserHistory para SCI...")
    
    # 1. Gerar os Utilizadores do Moodle
    users = []
    base_moodle_id = 2024000
    
    # Criar 16 utilizadores
    for i in range(16):
        moodle_id = base_moodle_id + random.randint(100, 999) + i
        # Garantir unicidade caso o random repita
        while any(u.moodle_id == moodle_id for u in users):
            moodle_id += 1
            
        student_email = f"up2024{10000 + i}@fe.up.pt"
        
        user_record = MoodleUsers(moodle_id=moodle_id, email=student_email)
        users.append(user_record)
        db.session.add(user_record)
        
    try:
        db.session.flush()  # Garante os ids para as chaves estrangeiras
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao criar utilizadores: {e}")
        return

    # 2. Configurar o calendário letivo realista (Setembro de 2024 a Janeiro de 2025)
    start_date = datetime(2024, 9, 16, 9, 0, 0)
    
    # Padrão comportamental: Estudantes divididos por nível de atividade
    # Tipo 0: Heavy users (fazem muitas perguntas), Tipo 1: Moderados, Tipo 2: Ocasionais
    user_profiles = {u.moodle_id: random.choice([0, 1, 2]) for u in users}

    history_records_count = 0
    target_rows = 85  # Garante que ultrapassa o mínimo de 80 rows solicitadas

    # Gerar interações fluindo ao longo das 14 semanas letivas de SCI
    while history_records_count < target_rows:
        for week in range(1, 15):
            if history_records_count >= target_rows:
                break
                
            # Determinar a data da semana corrente
            week_start_date = start_date + timedelta(weeks=week-1)
            
            # Picos de frequência baseados no plano real do PDF:
            # Semana 3-4 (Preparação da Apresentação), Semana 7 (Mini-Exam 1), Semana 12-13 (Mini-Exam 2 e Fecho)
            if week in [3, 4, 7, 12, 13]:
                base_questions_this_week = random.randint(5, 8)
            else:
                base_questions_this_week = random.randint(2, 4)
                
            for _ in range(base_questions_this_week):
                if history_records_count >= target_rows:
                    break
                    
                # Selecionar um aluno aleatório
                active_user = random.choice(users)
                profile = user_profiles[active_user.moodle_id]
                
                # Filtrar probabilidade do perfil interagir (Heavy vs Ocasional)
                if profile == 2 and random.random() > 0.3:
                    continue  # Alunos ocasionais saltam interações frequentemente
                    
                # Escolher aleatoriamente um grupo de Q&A do banco de dados (reproduzindo o RAG)
                pdf_group = random.choice(qa_bank)
                selected_pdf = pdf_group["pdf"]
                q_text, a_text = random.choice(pdf_group["qa"])
                
                # Gerar carimbo de data/hora realista dentro dessa semana letiva
                days_offset = random.randint(0, 4)  # Dias de semana (Segunda a Sexta)
                hours_offset = random.randint(9, 18)  # Horário laboral e letivo
                minutes_offset = random.randint(0, 59)
                
                interaction_timestamp = week_start_date + timedelta(
                    days=days_offset, hours=hours_offset, minutes=minutes_offset
                )
                
                # Simular tempos de resposta do bot (geralmente rápidos, < 5 segundos)
                # Ocasionalmente mais lentos para simular carga ou latência da API
                if random.random() > 0.9:
                    time_taken = f"{random.uniform(5.1, 12.4):.3f}s"
                else:
                    time_taken = f"{random.uniform(0.8, 3.2):.3f}s"
                    
                # Determinar se a pergunta foi complexa o suficiente para transitar para o Tutor Humano
                # Geralmente ocorre se houver termos fora de contexto ou dúvidas de avaliação pessoal
                is_tutor = random.random() < 0.12  # ~12% de taxa de escalonamento para estatísticas do prof.

                history_entry = MoodleUserHistory(
                    course_id=course_id,
                    user_moodle_id=active_user.moodle_id,
                    question=q_text,
                    response=a_text,
                    pdfs=selected_pdf,
                    is_tutor_interaction=is_tutor,
                    time_to_respond=time_taken,
                    timestamp=interaction_timestamp
                )
                
                db.session.add(history_entry)
                history_records_count += 1

    try:
        db.session.commit()
        print(f"Sucesso! Criados {len(users)} utilizadores e {history_records_count} registos de histórico com carimbos temporais reais do curso de SCI.")
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao commitar transação: {e}")


def gerar_hash_perguntas(lista_perguntas):
    # 1. Garantir que a lista está sempre na mesma ordem (pelo slot/id)
    perguntas_ordenadas = sorted(lista_perguntas, key=lambda x: x['moodle_question_id'])
    
    lista_para_hash = []
    for p in perguntas_ordenadas:
        # 2. Normalização extrema do texto
        texto = p['texto_pergunta']
        # Remover espaços inquebráveis (\xa0), quebras de linha e espaços duplos
        texto_normalizado = " ".join(texto.replace('\xa0', ' ').split())
        
        # Criamos uma string única para esta pergunta
        item_string = f"ID:{p['moodle_question_id']}|TXT:{texto_normalizado}"
        lista_para_hash.append(item_string)
    
    # 3. Juntar tudo com um separador único
    string_final = "###".join(lista_para_hash)
    
    # 4. Debug: Descomenta a linha abaixo para ver exatamente o que está a ser hashed
    # print(f"DEBUG HASH INPUT: {string_final}")
    
    return hashlib.md5(string_final.encode('utf-8')).hexdigest()

# Função de exemplo que terás de adaptar à tua realidade
def verificar_total_pdfs_do_curso(course_id):
    print(f"Verificando total de PDFs processados para o curso {course_id}...")
    files = KnowledgeFiles.query.filter_by(course_id=course_id).all()
    total_pdfs = len(files)
    print(f"Total de PDFs processados para o curso {course_id}: {total_pdfs}")
    return total_pdfs

def clean_quiz_data(course_id, quiz_id):
    # Eliminar perguntas antigas do quiz
    quiz_antigo = MoodleQuizPolling.query.filter_by(
        quiz_id=quiz_id,
        course_id=course_id
    ).first()
    if quiz_antigo:
        print(f"Removendo dados antigos do quiz ID {quiz_id} para evitar duplicações.")   
        db.session.delete(quiz_antigo)
        db.session.commit()

    db.session.commit()

   
def obter_quiz_local(course_id, quiz_id):
    quiz_local = MoodleQuizPolling.query.filter_by(
        quiz_id=quiz_id,
        course_id=course_id
        ).first()
    if quiz_local:
        return quiz_local
    else:
        return None

def check_moodle_user_in_db(moodle_id, email):
    # Ver se o utilizador já existe na nossa BD, se não existir, criar
    moodle_user = MoodleUsers.query.filter_by(moodle_id=moodle_id).first()
    if not moodle_user:
        moodle_user = MoodleUsers(moodle_id=moodle_id, email=email)
        db.session.add(moodle_user)
        db.session.commit()
        print(f"Created new Moodle user in DB: {email} (ID: {moodle_id})")
    else:
        print(f"Moodle user already exists in DB: {email} (ID: {moodle_id})")

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


def get_moodle_user_data(user_id, moodle_token, moodle_url):
    # 1. Usa o IP direto e verifica se precisas de porta (ex: :80)
    function = "core_user_get_users"
    
    print(f"--- INÍCIO DA BUSCA MOODLE ---")
    print(f"ID: {user_id} | URL: {moodle_url}")

    params = {
        'criteria[0][key]': 'id',
        'criteria[0][value]': user_id
    }

    try:
        # 2. Adiciona um timeout para o código não ficar "pendurado" para sempre
        response_data = call_moodle(moodle_url, moodle_token, function, params, timeout=5)
        #print(f"Resposta bruta do Moodle: {response_data}")

        if 'users' in response_data and len(response_data['users']) > 0:
            user = response_data['users'][0]
            return {
                "nome": user['firstname'],
                "apelido": user['lastname'],
                "email": user['email'],
            }
        
        print(f"WARNING: Utilizador {user_id} não encontrado no Moodle.")
        return None
            
    except Exception as e:
        # 3. Usa o logger para o erro também, para teres a certeza que vês na consola
        print(f"ERRO: ERRO CRÍTICO ao ligar ao Moodle: {str(e)}")
        return None
    
def get_moodle_contents(course_id, moodle_url, moodle_token):
    function = "core_course_get_contents"
    print(f"--- INÍCIO DA BUSCA DE CONTEÚDOS MOODLE --- | Course ID: {course_id}")
    params = {
        'courseid': course_id
    }
    
    filenames = []  # Lista para armazenar os nomes dos ficheiros encontrados
    try:
        contents = call_moodle(moodle_url, moodle_token, function, params, timeout=5)
        #print(f"Resposta bruta do Moodle para conteúdos: {contents}")
        # print dos nomes dos ficheiros encontrados
        if isinstance(contents, list):
            for section in contents:
                for module in section.get('modules', []):
                    if 'contents' in module:
                        for content in module['contents']:
                            #print(f"Encontrado conteúdo: {content.get('filename', 'sem nome')} (Moodle ID: {module['id']})")
                            filenames.append(content.get('filename', 'sem nome'))
                                                        
        # Se o Moodle retornar um erro no JSON (ex: token inválido)
        if isinstance(contents, dict) and "exception" in contents:
            print(f"ERRO: Erro na API Moodle: {contents['message']}")
            return None, None

        print(f"Conteúdos obtidos com sucesso para o curso {course_id}")
        return contents, filenames

    except requests.exceptions.RequestException as e:
        print(f"ERRO: Erro na requisição ao Moodle: {e}")
        return None, None
    
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

def get_quiz_attempt_review(attempt_id, moodle_url, moodle_token):
    """
    Obtém os detalhes de uma tentativa de quiz, incluindo perguntas e respostas.
    """
    function = "mod_quiz_get_attempt_review"
    print(f"--- INÍCIO DA REVISÃO DE TENTATIVA --- | Attempt ID: {attempt_id}")
    
    params = {
        'attemptid': attempt_id,
        # 'page': -1  # Opcional: -1 retorna todas as páginas de perguntas de uma vez
    }
    
    try:
        # timeout mais longo porque esta chamada pode demorar, especialmente para quizzes grandes
        review_data = call_moodle(moodle_url, moodle_token, function, params, timeout=10)
        
        # Verificação de erro na resposta da API
        if isinstance(review_data, dict) and "exception" in review_data:
            print(f"ERRO: Erro na API Moodle (Review): {review_data['message']}")
            return None

        print(f"Dados da tentativa {attempt_id} obtidos com sucesso.")
        return review_data

    except requests.exceptions.RequestException as e:
        print(f"ERRO: Erro na requisição ao Moodle: {e}")
        return None
    
def get_user_quizzes_by_course(course_id, user_id, moodle_url, moodle_token):
    """
    Obtém a lista de quizzes de um curso e verifica quais o aluno já tentou.
    """
    function = "mod_quiz_get_quizzes_by_courses"
    print(f"--- BUSCANDO QUIZZES DO CURSO PARA O USUÁRIO --- | Course ID: {course_id} | User ID: {user_id}")
    
    try:
        data = call_moodle(moodle_url, moodle_token, function, {'courseids[0]': course_id}, timeout=10)

        if isinstance(data, dict) and "exception" in data:
            print(f"ERRO: Erro na API Moodle: {data['message']}")
            return None

        quizzes = data.get('quizzes', [])
        print(f"Total de quizzes encontrados no curso: {len(quizzes)}")
        
        return quizzes

    except Exception as e:
        print(f"ERRO: Erro ao obter quizzes do curso: {e}")
        return None
    
def get_last_attempt_id(quiz_id, user_id, moodle_url, moodle_token):
    """
    Obtém o ID da última tentativa de um aluno num questionário específico.
    """
    function = "mod_quiz_get_user_quiz_attempts"
    print(f"--- BUSCANDO TENTATIVAS --- | Quiz ID: {quiz_id} | User ID: {user_id}")
    
    params = {
        'quizid': quiz_id,
        'userid': user_id,
        'status': 'finished'  # apenas as finalizadas
    }
    
    try:
        data = call_moodle(moodle_url, moodle_token, function, params, timeout=10)
        
        if isinstance(data, dict) and "exception" in data:
            print(f"ERRO: Erro na API Moodle: {data['message']}")
            return None

        attempts = data.get('attempts', [])
        
        if not attempts:
            print(f"WARNING: Nenhuma tentativa encontrada para o User {user_id} no Quiz {quiz_id}")
            return None

        # Ordenar tentativas pelo ID (a mais recente terá o ID maior)
        # Ou podes filtrar apenas as que têm o state 'finished'
        attempts.sort(key=lambda x: x['id'], reverse=True)
        
        last_attempt = attempts[0]
        print(f"Tentativa encontrada! ID: {last_attempt['id']} | Estado: {last_attempt['state']}")
        
        return last_attempt['id']

    except Exception as e:
        print(f"ERRO: Erro ao obter tentativas: {e}")
        return None
    
def quiz_ja_processado(course_id, quiz_id):
    # Verificar se já analisámos esta tentativa
    analise = MoodleQuizPolling.query.filter_by(
        quiz_id=quiz_id,
        course_id=course_id
    ).first()
    
    if analise:
        return True
    else:
        print(f"Quiz ID {quiz_id} ainda não processado.")
        return False

def marcar_quiz_como_processado(course_id, quiz_id, quiz_name, questions_hash):
    # Criar um novo registo de quiz processado
    novo_registo = MoodleQuizPolling(
        course_id=course_id,
        quiz_id=quiz_id,
        quiz_name=quiz_name,
        questions_hash=questions_hash
    )
    db.session.add(novo_registo)
    db.session.commit()
    print(f"Quiz ID {quiz_id} adicionado ao banco de dados.")
    
def call_moodle(moodle_url, moodle_token, function, params={}, timeout=5):
    """Função genérica para chamar o Web Service do Moodle"""
    params.update({
        'wstoken': moodle_token,
        'wsfunction': function,
        'moodlewsrestformat': 'json'
    })
    try:
        if timeout:
            response = requests.post(f"{moodle_url}/webservice/rest/server.php", data=params, timeout=timeout)
        else:
            response = requests.post(f"{moodle_url}/webservice/rest/server.php", data=params)
        return response.json()
    except Exception as e:
        print(f"ERRO: Erro na chamada à API: {e}")
        return None
    
def obter_perguntas_do_quiz(quiz_id, moodle_url, moodle_token):
    # 1. Iniciar uma tentativa para ler o conteúdo
    # Nota: Se o quiz tiver password, precisarias de a passar aqui
    tentativa = call_moodle(moodle_url, moodle_token, 'mod_quiz_start_attempt', {'quizid': quiz_id})
    
    if 'attempt' not in tentativa:
        print(f"ERRO: Erro ao iniciar tentativa no quiz {quiz_id}: {tentativa}")
        return []

    attempt_id = tentativa['attempt']['id']
    perguntas_extraidas = []

    # --- 4. Ler as perguntas (incluindo múltiplas páginas) ---
    perguntas_extraidas = []
    pagina = 0
    while True:
        dados = call_moodle(moodle_url, moodle_token, 'mod_quiz_get_attempt_data', {'attemptid': attempt_id, 'page': pagina})
        if 'questions' not in dados or not dados['questions']:
            break
            
        for q in dados['questions']:
            texto = extrair_conteudo_pergunta(q['html'])
            perguntas_extraidas.append({
                'moodle_question_id': q['slot'],
                'type': q['type'],
                'texto_pergunta': texto
            })
        
        if 'nextpage' in dados and dados['nextpage'] != -1:
            pagina = dados['nextpage']
        else:
            break

    # --- 5. FECHAR A TENTATIVA (Obrigatório para a próxima execução funcionar) ---
    print(f"Finalizando tentativa {attempt_id}...")
    call_moodle(moodle_url, moodle_token, 'mod_quiz_process_attempt', {
        'attemptid': attempt_id,
        'finishattempt': 1
    })

    return perguntas_extraidas

def get_user_firstname(user_id, moodle_url, moodle_token):
    
    response = call_moodle(moodle_url, moodle_token, 'core_user_get_users', {
        'criteria[0][key]': 'id',
        'criteria[0][value]': user_id
    })
    if response and 'users' in response and response['users']:
        return response['users'][0].get('firstname', 'Unknown')
    return 'Unknown'

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
    print(f"Enviando perguntas para o Rasa para criação de tópicos...")
    for p in pergunta_id_texto:
        if p['type'] == 'truefalse':
            p['texto_pergunta'] = "True or False: " + p['texto_pergunta']
            
    payload = {
        "sender": "doesnt_matter", #user_email
        "message": "/create_topics", # Intent que o Rasa vai usar para identificar a ação
        "metadata": {"perguntas": pergunta_id_texto}
    }
    headers = {"Content-Type": "application/json"}

    lista_perguntas_final = []
    try:
        response = requests.post(RASA_BASE_URL + "/webhooks/rest/webhook", data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        messages = response.json() 
        print(f">> DEBUG COMPLETO RASA: {json.dumps(messages, indent=2)}")

        for message in messages:
            # 1. Verificamos se a mensagem tem o campo 'custom'
            if "custom" in message:
                custom_data = message["custom"]
                # 2. Procuramos pela chave que definimos no Rasa (gemini_analysis)
                # Esta chave contém a lista de perguntas já com tópicos e IDs convertidos
                if "gemini_analysis" in custom_data:
                    lista_perguntas_final = custom_data.get("gemini_analysis", [])
                    break 
        
        # 3. Validar e Logar os resultados
        if lista_perguntas_final:
            # clean "True or False: " do início das perguntas de True/False para guardar na BD
            for p in lista_perguntas_final:
                if p['question'].startswith("True or False: "):
                    p['question'] = p['question'].replace("True or False: ", "")
            #print(f"Perguntas finais após processamento: {lista_perguntas_final}")
        else:
            print("WARNING: Nenhuma pergunta processada encontrada na resposta do Rasa.")

    except Exception as e:
        print(f"ERRO: Erro ao processar resposta do Rasa: {e}")
        
    return lista_perguntas_final


def popular_db(course_id, quiz_id, perguntas):
    for p in perguntas:
        # ir buscar id do topico à tabela de tópicos, usando o nome do tópico que o Gemini nos deu
        topic = Topics.query.filter_by(name=p.get('topic')).first()
        # se nao exitir, criar o tópico
        topic_id = topic.id if topic else None
        if not topic:
            topic = Topics(name=p.get('topic'))
            db.session.add(topic)
            db.session.commit() # Commit para gerar o ID do tópico
            print(f"Novo tópico criado: {p.get('topic')} com ID {topic.id}")
            topic_id = topic.id
            
        nova_questao = MoodleQuizData(
            course_id=course_id,
            quiz_id=quiz_id,
            question=p.get('question'),
            topic_id=topic_id
        )
        db.session.add(nova_questao)
    db.session.commit()