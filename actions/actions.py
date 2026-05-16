print("🚀  A carregar o ficheiro actions.py...")
import sys
sys.modules["sqlite3"] = __import__("pysqlite3")
import chromadb
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk import Action, Tracker
from rasa_sdk import Action
from rasa_sdk.events import SlotSet, FollowupAction
from .utils import *

print(f"📂  A tentar ligar ao ChromaDB em: /app/vector_store")
# Em vez de PersistentClient, usamos HttpClient
# Lembra-te: o host é 'chroma' (nome do serviço no docker-compose) 
try:
    chroma_client = chromadb.HttpClient(host='chroma', port=8000)
    print("📡  Cliente ChromaDB instanciado...")
    
    collection = chroma_client.get_collection(name="class_materials")
    print("✅  Collection reloaded successfully.")
except Exception as e:
    print(f"❌  ERRO CRÍTICO NO CHROMA: {str(e)}")
    
    
class ActionGetMetricsFromDB(Action):
    def name(self) -> str:
        return "action_get_metrics_from_db"

    def run(self, dispatcher, tracker, domain):
        # 1. Verificar o slot
        role = tracker.get_slot("user_role")

        # 2. Lógica de decisão (Gatekeeper)
        if role == "teacher":
            
            course_id = tracker.latest_message.get("metadata", {}).get("course_id")
            teacher_question = tracker.latest_message.get("text")
            print(f"Teacher question: {teacher_question}")

            df = get_user_history(course_id)
            if df.empty:
                dispatcher.utter_message(text="There are no questions asked by students yet.")
                return []      
            
            # limit df to the last 50 entries to avoid overloading the prompt
            data_snippet = df.tail(50).to_string(index=False)

            system_instruction = f"""
            ### ROLE
            You are a Concise Educational Data Analyst. Your output is displayed in a narrow LMS sidebar.

            ### RULES
            1. **NO MARKDOWN:** Do NOT use asterisks (**) or hashtags (#). 
            2. **HTML ONLY:** Use <b>text</b> for bold, <ul><li></li></ul> for lists, and <br> for line breaks.
            3. **NO INTROS/OTHERS:** Start directly with the analysis. Do not say "Hello" or "Here is the report".
            4. **MAX BREVITY:** Use individual paragraphs. Maximum 3-4 paragraphs in total. Keep the total word count under 100 words.
            5. **LANGUAGE:** Always respond in English (UK).

            ### CONTEXT
            Data: {data_snippet}

            ### INSTRUCTIONS
            - If the question is generic, provide a "Quick Snapshot".
            - Use 'user_id' to distinguish if a problem is global or isolated.
            - Identify the most critical PDF/Topic and provide one brief action.

            ### RESPONSE (HTML format)
            """
            
            generation_config = {
                "temperature": 0.2,
            }
            
            formatted_response = "Sorry, I couldn't generate a response..."
            try:
                g_model = genai.GenerativeModel(
                    model_name=MODEL_NAME,
                    system_instruction=system_instruction,
                    generation_config=generation_config
                )
                response = g_model.generate_content(teacher_question)

                if hasattr(response, "text") and response.text:
                    print("\n🎯  Gemini Response Generated Successfully!")
                    formatted_response = format_gemini_response(response.text)
                    print(formatted_response)
                    dispatcher.utter_message(text=formatted_response)
                else:
                    print("\n ⚠️  Gemini Response is empty.")
                    dispatcher.utter_message(text="Sorry, I couldn't generate a response.")
            except Exception as e:
                dispatcher.utter_message(text="Sorry, I couldn't process that request.")
                print(f"\n❌  Error calling Gemini API: {e}")
        else:
            # Se for aluno ou estiver vazio, dispara a mensagem de erro
            dispatcher.utter_message(template="utter_permission_denied")
        
        return []

class ActionCallLLMWithContext(Action):
    def name(self) -> str:
        return "action_call_llm_with_context"

    def run(self, dispatcher, tracker, domain):
        # Esta ação pode ser usada para chamadas genéricas ao LLM com contexto do histórico de conversa
        # O prompt e a formatação da resposta podem ser adaptados conforme necessário
        print("\n📊  Generating bot 'action_call_llm_with_context' response...")
        
        course_id = tracker.latest_message.get("metadata", {}).get("course_id")
        teacher_question = tracker.latest_message.get("text")
        print(f"Teacher question: {teacher_question}")

        df = get_user_history(course_id)
        if df.empty:
            dispatcher.utter_message(text="There are no questions asked by students yet.")
            return []      
        
        # limit df to the last 50 entries to avoid overloading the prompt
        data_snippet = df.tail(50).to_string(index=False)
        
        # 1. Recuperar os eventos da conversa
        events = tracker.events
        
        # 2. Filtrar e construir o histórico para o LLM
        chat_history = []
        max_turns = 6 # Define quantas mensagens queres que o LLM "lembre"
        
        # Vamos andar de trás para a frente no histórico
        for event in reversed(events):
            if len(chat_history) >= max_turns:
                break
                
            if event.get("event") == "user":
                if event.get("text") != "set username trigger":
                    # Formato Gemini: 'user' + 'parts' com 'text'
                    chat_history.insert(0, {
                        "role": "user", 
                        "parts": [{"text": event.get("text")}]
                    })
            elif event.get("event") == "bot":
                # Formato Gemini: 'model' (e não 'assistant') + 'parts' com 'text'
                chat_history.insert(0, {
                    "role": "model", 
                    "parts": [{"text": event.get("text")}]
                })
            
        # 3. Criar a diretriz do sistema (Persona + Dados dos Alunos + Regras)
        # Injetamos o data_snippet diretamente no papel de sistema para o LLM ter como base de conhecimento.
        system_instruction = f"""
        You are an advanced analytics assistant for professors and academic administrators.
        Your goal is to help professors analyze student behavior, questions, and challenges based on the data provided.

        [STUDENT DATA (Last 50 records in the system)]
        {data_snippet}

        [BEHAVIORAL INSTRUCTIONS]
        1. HISTORY AND FOLLOW-UP: Use the conversation history to answer follow-up or ambiguous questions. If the professor asks "Who?", "Why?" or "What did he say?", analyze the previous messages to identify the student or concept they are referring to.
        2. ACCURACY: Base your responses strictly on the provided student data. If the information is not available and it's not a contextual follow-up question, kindly indicate that you do not have those details.
        3. FORMAT OF THE RESPONSE: You must structure your response using simple HTML tags so that it is rendered correctly in the interface (use tags like <b>, <br>, <ul>, <li>). Do not use Markdown (like ** or ###).
        """

        print(f"\n📜  Complete messages payload for LLM:\n{chat_history}\n")
        
        generation_config = {
            "temperature": 0.2,          # 🛡️ Mantém isto baixo para o bot ser factual e não inventar dados
            #"max_output_tokens": 400,    # 💸 Mantém isto para controlar o tamanho da resposta e custos
            # top_p e top_k omitidos -> O Gemini assume os dele (0.95 e 40)
        }
        
        formatted_response = "Sorry, I couldn't generate a response..."
        try:
            g_model = genai.GenerativeModel(
                model_name=MODEL_NAME,
                system_instruction=system_instruction,
                generation_config=generation_config
            )
            response = g_model.generate_content(chat_history)

            if hasattr(response, "text") and response.text:
                print("\n🎯  Gemini Response Generated Successfully!")
                formatted_response = format_gemini_response(response.text)
                print(formatted_response)
                dispatcher.utter_message(text=formatted_response)
            else:
                print("\n ⚠️  Gemini Response is empty.")
                dispatcher.utter_message(text="Sorry, I couldn't generate a response.")
        except Exception as e:
            dispatcher.utter_message(text="Sorry, I couldn't process that request.")
            print(f"\n❌  Error calling Gemini API: {e}")
        
        return []

class ActionSetUsername(Action):
    def name(self) -> str:
        return "action_set_username"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: dict):
        
        print(f"DEBUG TRACKER SLOTS: {tracker.current_slot_values()}")
        

        sender_id = tracker.sender_id
        # Extract metadata
        metadata = tracker.latest_message.get("metadata", {})
        user_name = metadata.get("user_name")
        user_role = metadata.get("user_role")

        if user_name and user_role:
            print(f"\n👤  ({sender_id}) Setting username slot to: {user_name} and user_role slot to: {user_role}")
            return [SlotSet("username", user_name), SlotSet("user_role", user_role)]
        else:
            return []

def keywords_to_tokens(keywords, query):
    """
    Convert keywords to complex and simple lemmatized tokens.
    Complex tokens are phrases (e.g., "pestel analysis"), while simple tokens are individual words (e.g., "pestel", "analysis").
    """
    
    keywords = list(dict.fromkeys(keywords)) # Remove duplicates
    
    print(f"\n🔛  Getting lemmas for keyphrase/keywords: '{keywords}'")
    query_length = len(query.split())
    print(f"👻  --> Original query: {query}")
    print(f"👻  --> Query length: {query_length} words")
    
    if keywords == []:
        print("\n👻  --> No keywords found in the query. Using just .split()")
        query = " ".join(query.split())
        simple_tokens = tokenize_and_clean_text(query)
        print(f"👻  --> New keywords: {simple_tokens}")
        return [], simple_tokens, True         
        
    if query_length <= 5:
        percentage = 0.30
    else:
        percentage = 0.20
    
    if len(keywords) < query_length * percentage:
        simple_keywords = []
        for keyword in keywords:
            if " " in keyword:
                lemma_words = tokenize_and_clean_text(keyword)
                for word in lemma_words:
                    simple_keywords.append(word)
            else:
                simple_keywords.append(keyword)

        if len(simple_keywords) < query_length * percentage:
            print(f"👻  --> Keywords are less than {percentage} of the query length ({query_length}). Using just .split()")
            query = " ".join(query.split())
            simple_tokens = tokenize_and_clean_text(query)
            print(f"👻  --> New keywords: {simple_tokens}")
            return [], simple_tokens, True         
        
    print(f"\n🔛  Current keywords: {keywords}")
    complex_tokens = []  # e.g., ["pestel analysis", "pestel framework"]
    simple_tokens = []  # e.g., ["pestel", "analysis"]
    for i, keyword in enumerate(keywords):        
        if " " in keyword:
            lemma_words = tokenize_and_clean_text(keyword)
            print(f"\n👻  --> Lemmas for phrase '{keyword}': {lemma_words}")
            for word in lemma_words:
                simple_tokens.append(word)  # e.g., ["pestel", "analysis"]
            if len(lemma_words) > 1:
                complex_tokens.append(" ".join(lemma_words)) # e.g., ["pestel analysis"]
        else: 
            simple_tokens.append(keyword) # e.g., ["pestel"]
    
    # remove duplicates from simple_tokens
    simple_tokens = list(set(simple_tokens))
    
    return complex_tokens, simple_tokens, False # Return complex tokens, simple tokens, and split_keywords flag

def action_process(dispatcher, user_message, user_email, input_time, authorized_resources, intent, user_id, course_id):
    if authorized_resources == []:
        print(f"\n❌  No authorized resources found for user: {user_email}")
        return  [
            SlotSet("user_query", user_message),  # Store the query
            SlotSet("materials_location", []), #gemini_results),  # Store selected materials
            SlotSet("bot_response", "no_access"),  # Store the bot response -> trigger
            SlotSet("user_email", user_email),  # Store the sender ID
            SlotSet("user_id", user_id),  # Store the user ID
            SlotSet("input_time", input_time)
            ]
        
    print(f"\n🧒  User ({user_email}) said: {user_message} 📩")
    query = treat_raw_query(user_message)
    
    # Keywords Extraction Process 
    no_punct_query = re.sub(r"[^\w\s\-\&]", "", query).strip()  # Remove punctuation except '-' and '&'
    keywords = extract_query_keywords(no_punct_query)
    complex_tokens, simple_tokens, split_keywords = keywords_to_tokens(keywords, no_punct_query)  
    print(f"\n🔍  Extracted keywords: \n    {complex_tokens} \n    {simple_tokens} \n    Split keywords flag: {split_keywords}")
    
    print(f"\n🔍  Starting search process in resources: {authorized_resources[0]}")
    # Hybrid Search Process    
    vector_docs, vector_metadata, normalized_vector_scores = dense_vector_search(keywords, query, split_keywords, collection, authorized_resources, intent)        
    bm25_docs, bm25_meta, normalized_bm25_scores = hybrid_bm25_search(complex_tokens, simple_tokens, authorized_resources, course_id)
    
    if bm25_docs == [] and bm25_meta == [] and normalized_bm25_scores == []:
        print(f"\n⚠️  BM25 search returned no results for user query: '{query}'")
        return  [
            SlotSet("user_query", query),  # Store the query
            SlotSet("materials_location", ""), #gemini_results),  # Store selected materials
            SlotSet("bot_response", "no_access"),  # Store the bot response -> trigger
            SlotSet("user_email", user_email),  # Store the sender ID
            SlotSet("user_id", user_id),  # Store the user ID
            SlotSet("input_time", input_time)
            ]
    if normalized_bm25_scores == []:
        print(f"\n⚠️  Normalized BM25 scores is empty for user query: '{query}'")
        return  [
            SlotSet("user_query", query),  # Store the query
            SlotSet("materials_location", ""), #gemini_results),  # Store selected materials
            SlotSet("bot_response", "no_response"),  # Store the bot response
            SlotSet("user_email", user_email),  # Store the sender ID
            SlotSet("user_id", user_id),  # Store the user ID
            SlotSet("input_time", input_time)
            ]
        
    
    if not split_keywords:
        if intent == "definition of ":
            alpha = 0.6 # Use a lower alpha for definitions
            print(f"\n🔍  Found keywords: {complex_tokens} and {simple_tokens}. \n     Using hybrid search with alpha = {alpha} because of the 'DEFINE' intent ")
        else:
            # For other intents, use a slightly higher alpha
            alpha = 0.75
            print(f"\n🔍  Found keywords: {complex_tokens} and {simple_tokens}. \n     Using hybrid search with alpha = {alpha}")
    else: # Use hybrid search with a higher weight for vector search
        alpha = 0.85
        print(f"\n🔍  Split case: found multiple keywords: {complex_tokens} and {simple_tokens}. Using hybrid search with alpha = {alpha}")

        
    selected_results = hybrid_search(vector_docs, vector_metadata, normalized_vector_scores, bm25_docs, bm25_meta, normalized_bm25_scores, alpha)
    
    if len(selected_results) == 0:
        dispatcher.utter_message(text="I couldn't find relevant class materials for your query.")
        print("\n🚨  No relevant materials found!")
    else: 
        # Format results
        results_text = []
        for text_chunk, _, _ in selected_results:
            results_text.append(text_chunk)

        # === PREPARE CONTEXT AND RULES FOR SYSTEM === #
        raw_text = "\n".join(results_text)
        
        system_instruction = f"""
        You are a precise academic tutor assistant. Your task is to answer the student's query based strictly on the provided educational course material.

        [COURSE MATERIAL CONTEXT]
        {raw_text}

        [CRITICAL RULES]
        1. CONCISENESS: Be extremely precise and direct. Do NOT exceed 50 words in your answer.
        2. STRICTNESS: Base your answer ONLY on the provided course material above. Do not extrapolate or use outside knowledge.
        3. FALLBACK: If you cannot find the relevant information to answer the query within the provided course material, you must reply exactly with this phrase: "I couldn't find relevant content in the course materials."
        """

        # === PREPARE PARAMETERS === #
        generation_config = {
            "temperature": 0.1,           # Baixamos para 0.1 para máxima precisão factual
            #"max_output_tokens": 120,     # Um teto seguro (50 palavras dão cerca de 70 tokens)
        }
        
        formatted_response = "Sorry, I couldn't generate a response..."
        
        # === CALL GEMINI API === #
        try:
            g_model = genai.GenerativeModel(
                model_name=MODEL_NAME,
                system_instruction=system_instruction, # Contexto e regras vão aqui
                generation_config=generation_config
            )
            
            # O input do utilizador leva apenas a pergunta direta
            user_prompt = f"Student Query: {query}"
            response = g_model.generate_content(user_prompt)

            if hasattr(response, "text") and response.text:
                print("\n🎯  Gemini Response Generated Successfully!")
                formatted_response = format_gemini_response(response.text)
                dispatcher.utter_message(text=formatted_response)
            else:
                print("\n ⚠️  Gemini Response is empty.")
                dispatcher.utter_message(text=formatted_response)
        except Exception as e:
            selected_results = []  # Clear selected results
            print(f"\n❌  Error calling Gemini API: {e}")
            return  [
                SlotSet("user_query", query),  # Store the query
                SlotSet("materials_location", ""), #gemini_results),  # Store selected materials
                SlotSet("bot_response", "gemini_error"),  # Store the bot response -> trigger
                SlotSet("user_email", user_email),  # Store the sender ID
                SlotSet("user_id", user_id),  # Store the user ID
                SlotSet("input_time", input_time)
            ]

    return  [
        SlotSet("user_query", user_message),  # Store the query
        SlotSet("materials_location", selected_results), #gemini_results),  # Store selected materials
        SlotSet("bot_response", formatted_response),  # Store the bot response
        SlotSet("user_email", user_email),  # Store the sender ID
        SlotSet("user_id", user_id),  # Store the user ID
        SlotSet("input_time", input_time)
        ]

class ActionCreateTopic(Action):
    def name(self):
        return "action_create_topic"

    def run(self, dispatcher, tracker, domain):
        
        print("\n📊  Generating bot 'action_create_topic' response...")

        perguntas = tracker.latest_message.get("metadata", {}).get("perguntas", [])
        print(f"\n🔍  Original perguntas from metadata: {perguntas}")
        
        # 1. DEFINIÇÃO DA SYSTEM INSTRUCTION (Regras, Contexto e Schema em Inglês)
        system_instruction = """
        You are an expert academic data categorization assistant.
        Your task is to analyze a provided list of student questions and generate a concise topic (in English) for each one.

        CRITICAL RULES:
        1. CONSISTENCY: Group related or similar questions under the exact same topic name to maintain categorization consistency.
        2. FALLBACK: If you cannot determine a clear topic for a specific question, leave the "topic" field as an empty string ("").
        3. OUTPUT FORMAT: You must respond strictly with a valid JSON array of objects matching the schema provided below. Do not include any introductory text, explanations, or markdown code block wrappers (like ```json).

        EXPECTED JSON SCHEMA:
        [
        {
            "id": "original_moodle_question_id",
            "question": "original_question_text",
            "topic": "generated_topic_in_english_or_empty_string"
        }
        ]
        """

        # 2. CONSTRUÇÃO DOS DADOS DO UTILIZADOR (Apenas a lista crua)
        user_prompt = "Categorize the following questions:\n"
        for pergunta in perguntas:
            moodle_id = str(pergunta.get("moodle_question_id", ""))
            texto_pergunta = pergunta.get("texto_pergunta", "")
            user_prompt += f"- ID: {moodle_id}, question: {texto_pergunta}\n"
            
        try:
            # 3. INICIALIZAÇÃO DO MODELO
            g_model = genai.GenerativeModel(
                model_name=MODEL_NAME, # A tua variável global com o nome do modelo pro
                system_instruction=system_instruction,
                generation_config={
                    "temperature": 0.2,                          # Temperatura baixa para categorizações mais exatas
                    "response_mime_type": "application/json"     # 🌟 Força o Gemini a cuspir APENAS JSON puro
                }
            )
            response = g_model.generate_content(user_prompt)

            if hasattr(response, "text") and response.text:
                print("\n🎯 Gemini Response Generated Successfully!")
                raw_text = response.text.strip()
                
                # 1. Limpar os backticks de Markdown (```json e ```)
                # O regex remove o que estiver antes e depois do [ ou {
                clean_json_str = re.sub(r'^```json\s*|```$', '', raw_text, flags=re.MULTILINE).strip()
                
                try:
                    # 2. Converter a string limpa num objeto real do Python (lista ou dicionário)
                    gemini_data = json.loads(clean_json_str)
                except json.JSONDecodeError:
                    print("Erro ao converter string do Gemini em JSON")
                    gemini_data = raw_text # Fallback se falhar
            else:
                gemini_data = None

        except Exception as e:
            print(f"\n❌  Error calling Gemini API: {e}")
            gemini_data = None
            
        # 4. ENVIAR APENAS UMA MENSAGEM com tudo agrupado
        # Assim o Flask recebe um único objeto fácil de iterar
        dispatcher.utter_message(json_message={
            "status": "success",
            "gemini_analysis": gemini_data
        })
        
        return []
    
# === ACTION 1: GET DEFINITION === #
class ActionGetDefinition(Action):
    def name(self):
        return "action_get_definition"

    def run(self, dispatcher, tracker, domain):
        
        print("\n📊  Generating bot 'action_get_definition' response...")
        
        print(f"DEBUG TRACKER SLOTSS: {tracker.current_slot_values()}")
        
        # print slot of user_role
        user_role = tracker.get_slot("user_role")
        print(f"👤  User role from slot: {user_role}")

        user_message = tracker.latest_message.get("text")
        user_email = tracker.sender_id  # ✅ Retrieves the "sender" field
        user_id = tracker.latest_message.get("metadata", {}).get("user_id")
        course_id = tracker.latest_message.get("metadata", {}).get("course_id")
        input_time = tracker.latest_message.get("metadata", {}).get("input_time")
        print(f"🕓  latest_message INPUT TIME: {input_time}")
        authorized_resources = tracker.latest_message.get("metadata", {}).get("authorized_resources", [])
        print(f"📚  Authorized resources from metadata: {authorized_resources}")
        #tutor_mode = tracker.latest_message.get("metadata", {}).get("tutor_mode", False)
        #print(f"🎓  Tutor mode from metadata: {tutor_mode}")
        
        is_teacher = tracker.latest_message.get("metadata", {}).get("is_teacher", False)
        print(f"👩‍🏫  Is teacher ({user_email}) from metadata: {is_teacher}")
        
        intent = "definition of "      
        
        return action_process(dispatcher, user_message, user_email, input_time, authorized_resources, intent, user_id, course_id)
    
# === ACTION 2: GET EXPLANATION === #
class ActionGetExplanation(Action):
    def name(self):
        return "action_get_explanation"

    def run(self, dispatcher, tracker, domain):
        
        print("\n📊  Generating bot 'action_get_explanation' response...")

        user_message = tracker.latest_message.get("text")
        user_email = tracker.sender_id  # ✅ Retrieves the "sender" field
        user_id = tracker.latest_message.get("metadata", {}).get("user_id")
        input_time = tracker.latest_message.get("metadata", {}).get("input_time")
        authorized_resources = tracker.latest_message.get("metadata", {}).get("authorized_resources", [])
        course_id = tracker.latest_message.get("metadata", {}).get("course_id")

        intent = "explanation of "

        return action_process(dispatcher, user_message, user_email, input_time, authorized_resources, intent, user_id, course_id)

# === ACTION 3: GET EXAMPLES === #
class ActionGetExamples(Action):
    def name(self):
        return "action_get_examples"

    def run(self, dispatcher, tracker, domain):
        
        print("\n📊  Generating bot 'action_get_examples' response...")

        user_message = tracker.latest_message.get("text")
        user_email = tracker.sender_id  # ✅ Retrieves the "sender" field
        input_time = tracker.latest_message.get("metadata", {}).get("input_time")
        user_id = tracker.latest_message.get("metadata", {}).get("user_id")
        course_id = tracker.latest_message.get("metadata", {}).get("course_id")
        authorized_resources = tracker.latest_message.get("metadata", {}).get("authorized_resources", [])

        intent = "examples of "
        return action_process(dispatcher, user_message, user_email, input_time, authorized_resources, intent, user_id, course_id)

# === ACTION 4: SUMMARIZE === #
class ActionGetSummary(Action):
    def name(self):
        return "action_get_summary"

    def run(self, dispatcher, tracker, domain):
        
        print("\n📊  Generating bot 'action_get_summary' response...")

        user_message = tracker.latest_message.get("text")
        user_email = tracker.sender_id  # ✅ Retrieves the "sender" field
        input_time = tracker.latest_message.get("metadata", {}).get("input_time")
        user_id = tracker.latest_message.get("metadata", {}).get("user_id")
        authorized_resources = tracker.latest_message.get("metadata", {}).get("authorized_resources", [])
        course_id = tracker.latest_message.get("metadata", {}).get("course_id")

        intent = "summary of "
        return action_process(dispatcher, user_message, user_email, input_time, authorized_resources, intent, user_id, course_id)


# === FINAL ACTION: GET PDF NAMES & PAGE LOCATIONS === #
class ActionGetClassMaterialLocation(Action):
    def name(self):
        return "action_get_class_material_location"

    def run(self, dispatcher, tracker, domain):

        bot_response = tracker.get_slot("bot_response")
        input_time = tracker.get_slot("input_time")
        selected_results = tracker.get_slot("materials_location")
        user_id = tracker.get_slot("user_id")
        course_id = tracker.latest_message.get("metadata", {}).get("course_id")
        user_email = tracker.get_slot("user_email")
        user_message = tracker.get_slot("user_query")
        query = treat_raw_query(user_message)
        tutor_mode = tracker.latest_message.get("metadata", {}).get("tutor_mode", False)
        #print(f"tutor_mode in ActionGetClassMaterialLocation: {tutor_mode}")
        
        if bot_response == "no_access":
            dispatcher.utter_message(text="You don't have access to any class materials yet. Please check with your instructor to gain access to the course materials and try again.")
            return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", "")]

        if bot_response == "no_response":
            response = f"I couldn't find any relevant content on this topic in the course materials. Please try again."
            save_user_progress(course_id, user_email, user_message, response, [], input_time, user_id, tutor_mode)
            dispatcher.utter_message(text=response)
            return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", "")]

        if bot_response == "gemini_error":
            response = f"Sorry, I couldn't process that request due to an error calling Gemini API. Please try again later."
            save_user_progress(course_id, user_email, user_message, response, [], input_time, user_id, tutor_mode)
            dispatcher.utter_message(text=response)
            return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", "")]
        
        print(f"\n\n 🔖  --------- Getting class materials location --------- 🔖 ")
        
        if len(selected_results) == 0:
            dispatcher.utter_message(text="I couldn't find relevant class materials for your query.")
            print("\n🚨  No relevant materials found!")

        else: # get materials location:
            no_punct_query = re.sub(r"[^\w\s]", "", query).strip()  # Remove punctuation
            # get relevant keywords from the query
            keywords = extract_query_keywords(no_punct_query)
            complex_tokens, simple_tokens, _ = keywords_to_tokens(keywords, query)       
            location_results, pdfs_insights = get_materials_location(selected_results, complex_tokens, simple_tokens, course_id)

            if location_results:
                response = save_user_progress(course_id, user_email, query, bot_response, ", ".join(pdfs_insights), input_time, user_id, tutor_mode)
                print_results(location_results)              
                dispatcher.utter_message(
                    text="</br></br><span style='font-size: 11px;'>You can find related information in:</span></br><i><span style='font-size: 10px;'>" 
                    + "</br>".join(location_results) + 
                    "</span></i>"
                )
            else:
                # no exact references found, so return related PDFs found in previous function
                if selected_results:
                    location_results, pdfs_insights = update_materials_location(selected_results)
                    response = save_user_progress(course_id, user_email, query, bot_response, ", ".join(pdfs_insights), input_time, user_id, tutor_mode)
                    #dispatcher.utter_message(text="</br></br>You can find related information in:</br>" + "</br>".join(location_results))
                    dispatcher.utter_message(
                        text="</br></br><span style='font-size: 11px;'>You can find related information in:</span></br><i><span style='font-size: 10px;'>" 
                        + "</br>".join(location_results) + 
                        "</span></i>"
                )
                else:                
                    print("\n ⚠️  No exact references found, but you might check related PDFs.")
                    response = save_user_progress(course_id, user_email, user_message, bot_response, [], input_time, user_id, tutor_mode)
                    dispatcher.utter_message(text="I couldn't find specific page references for your question.")

        #clear the slots
        return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", "")]


class ActionGenerateInitialMenuButtons(Action):
    def name(self):
        return "action_generate_initial_menu_buttons"

    def run(self, dispatcher, tracker, domain):
        print("\n📊  Generating initial menu buttons...")
        
        #user_email = tracker.sender_id
        course_id = tracker.latest_message.get("metadata", {}).get("course_id")
        user_id = tracker.latest_message.get("metadata", {}).get("user_id")
        user_message = tracker.latest_message.get("metadata", {}).get("user_message", None)
        print(f"🎓  User {user_id} sent message: {user_message}")
        
        # get user progress
        progress = requests.get(f"http://flask-server:8080/api/get_user_progress", params={"user_id": user_id, "course_id": course_id})
        if progress.status_code == 200:
            progress_data = progress.json()
            print(f"📊  User progress data retrieved: {progress_data}")
        else:
            print(f"❌  Failed to retrieve user progress. Status code: {progress.status_code}")
            progress_data = []
        
        dispatcher.utter_message(
            text="Please select an option:",
            buttons=[
                {"title": "option 1", "payload": "/options_menu"},
                {"title": "option 2", "payload": "/options_menu"},
                {"title": "option 3", "payload": "/options_menu"}
            ]
        )
        return []
    