print("🚀  A carregar o ficheiro actions.py...")
import sys
sys.modules["sqlite3"] = __import__("pysqlite3")
import chromadb
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk import Action, Tracker
from rasa_sdk import Action
from rasa_sdk.events import SlotSet
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
        print("\n📊  Generating bot 'action_get_metrics_from_db' response...")
        # 1. Verificar o slot
        role = tracker.get_slot("user_role")

        # 2. Lógica de decisão (Gatekeeper)
        if role == "teacher":
            
            user_email = tracker.sender_id
            user_id = tracker.latest_message.get("metadata", {}).get("user_id")
            course_id = tracker.latest_message.get("metadata", {}).get("course_id")
            input_time = tracker.latest_message.get("metadata", {}).get("input_time")
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
            4. **MAX BREVITY:** Maximum 3-4 paragraphs in total. Keep the total word count under 120 words.
            5. **LANGUAGE:** Always respond in English (UK).
            6. **VISUAL CHARTS:** If the data shows a clear trend over time, a comparison between 2-3 main categories, or metrics that benefit from visual aid, append a single Chart Image at the very end of your response using this exact HTML structure:
            6. **VISUAL CHARTS:** If relevant, append a single Chart Image at the very end using this exact structure:
            <br><br><a href="https://quickchart.io/chart?c={{chart_json}}" target="_blank"><img src="https://quickchart.io/chart?c={{chart_json}}" width="100%"></a>
            Keep the chart design extremely simple, clean, and fit for a narrow sidebar (e.g., a small bar or line chart with minimal labels). If a chart is not relevant for the specific question, do not include the img tag.

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
                    #print(formatted_response)
                    save_user_progress(course_id, user_email, teacher_question, formatted_response, [], input_time, user_id, False)
                    dispatcher.utter_message(text=formatted_response)
                else:
                    print("\n ⚠️  Gemini Response is empty.")
                    dispatcher.utter_message(text="Sorry, I couldn't generate a response.")
                    save_user_progress(course_id, user_email, teacher_question, "Sorry, I couldn't generate a response.", [], input_time, user_id, False)
                    
            except Exception as e:
                dispatcher.utter_message(text="Sorry, I couldn't process that request.")
                save_user_progress(course_id, user_email, teacher_question, "Sorry, I couldn't process that request.", [], input_time, user_id, False)
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
        
        user_email = tracker.sender_id
        user_id = tracker.latest_message.get("metadata", {}).get("user_id")
        input_time = tracker.latest_message.get("metadata", {}).get("input_time")
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
                #print(formatted_response)
                save_user_progress(course_id, user_email, teacher_question, formatted_response, [], input_time, user_id, False)
                dispatcher.utter_message(text=formatted_response)
            else:
                print("\n ⚠️  Gemini Response is empty.")
                save_user_progress(course_id, user_email, teacher_question, "Sorry, I couldn't generate a response.", [], input_time, user_id, False)
                dispatcher.utter_message(text="Sorry, I couldn't generate a response.")
        except Exception as e:
            save_user_progress(course_id, user_email, teacher_question, "Sorry, I couldn't process that request.", [], input_time, user_id, False)
            dispatcher.utter_message(text="Sorry, I couldn't process that request.")
            print(f"\n❌  Error calling Gemini API: {e}")
        
        return []

class ActionSetUsername(Action):
    def name(self) -> str:
        return "action_set_username"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: dict):
        
        #print(f"DEBUG TRACKER SLOTS: {tracker.current_slot_values()}")
        
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

def keywords_to_tokens(keywords, query, context):
    """
    Convert keywords to complex and simple lemmatized tokens.
    Complex tokens are phrases (e.g., "pestel analysis"), while simple tokens are individual words (e.g., "pestel", "analysis").
    """
    keywords = list(dict.fromkeys(keywords)) # Remove duplicates
    if context and context.strip() != "":
        # remove context expression from query independent from lower/upper case and extra spaces
        context_clean = context.strip()
        
        # 2. re.escape garante que caracteres especiais no contexto (como ?, * etc.) não partam o regex
        # re.IGNORECASE faz a magia de ignorar se é maiúscula ou minúscula
        query = re.sub(re.escape(context_clean), "", query, flags=re.IGNORECASE).strip()
        print(f"\n👻  Context '{context_clean}' removed from query. New query: '{query}'")
    
    #print(f"\n🔛  Getting lemmas for keyphrase/keywords: '{keywords}'")
    query_length = len(query.split())
    #print(f"👻  --> Original query: {query}")
    #print(f"👻  --> Query length: {query_length} words")
    
    if keywords == []:
        #print("\n👻  --> No keywords found in the query. Using just .split()")
        query = " ".join(query.split())
        print(f"👻  --> Cleaned query (extra spaces removed): '{query}'")
        simple_tokens = tokenize_and_clean_text(query)
        #print(f"👻  --> New keywords: {simple_tokens}")
        return [], simple_tokens, True         
        
    if query_length <= 5:
        percentage = 0.30
    else:
        percentage = 0.20
    
    if len(keywords) < query_length * percentage:
        simple_keywords = []
        for keyword in keywords:
            if " " in keyword:
                print(f"👻  --> Keyword '{keyword}' is a phrase. Tokenizing and lemmatizing it to extract simple keywords.")
                lemma_words = tokenize_and_clean_text(keyword)
                for word in lemma_words:
                    simple_keywords.append(word)
            else:
                simple_keywords.append(keyword)

        if len(simple_keywords) < query_length * percentage:
            #print(f"👻  --> Keywords are less than {percentage} of the query length ({query_length}). Using just .split()")
            query = " ".join(query.split())
            print(f"👻  --> Cleaned query (extra spaces removed): '{query}'")
            simple_tokens = tokenize_and_clean_text(query)
            #print(f"👻  --> New keywords: {simple_tokens}")
            return [], simple_tokens, True         
        
    #print(f"\n🔛  Current keywords: {keywords}")
    complex_tokens = []  # e.g., ["pestel analysis", "pestel framework"]
    simple_tokens = []  # e.g., ["pestel", "analysis"]
    for i, keyword in enumerate(keywords):        
        if " " in keyword:
            lemma_words = tokenize_and_clean_text(keyword)
            #print(f"    👻  --> Lemmas for phrase '{keyword}': {lemma_words}")
            for word in lemma_words:
                simple_tokens.append(word)  # e.g., ["pestel", "analysis"]
            if len(lemma_words) > 1:
                complex_tokens.append(" ".join(lemma_words)) # e.g., ["pestel analysis"]
        else: 
            simple_tokens.append(keyword) # e.g., ["pestel"]
    
    # remove duplicates from simple_tokens
    simple_tokens = list(set(simple_tokens))
    
    return complex_tokens, simple_tokens, False # Return complex tokens, simple tokens, and split_keywords flag

def action_process(dispatcher, tracker, user_message, user_email, input_time, authorized_resources, intent, user_id, course_id):
    if authorized_resources == []:
        print(f"\n❌  No authorized resources found for user: {user_email}")
        return  [
            SlotSet("user_query", user_message),  # Store the query
            SlotSet("materials_location", []), #gemini_results),  # Store selected materials
            SlotSet("bot_response", "no_access"),  # Store the bot response -> trigger
            SlotSet("user_email", user_email),  # Store the sender ID
            SlotSet("user_id", user_id),  # Store the user ID
            SlotSet("input_time", input_time),
            SlotSet("concept", ""),
            SlotSet("context", "") # Store the context for future use
            ]
        
    print(f"\n📖  --------- Getting Knowledge --------- 📖 ")
    print(f"\n🧒  User ({user_email}) said: {user_message} 📩")
    
    # Extract variables from chat memory
    concept = tracker.get_slot("concept")  
    concept = concept.lower().strip() if concept else ""  
    # remove stopwords from concept for better matching with keywords later
    #concept_tokens = tokenize_and_clean_text(concept)
    #concept = " ".join(concept_tokens) if concept_tokens else ""     
    context = tracker.get_slot("context")   
    context = context.lower().strip() if context else ""     
    print(f"🔍  Concept from slot: '{concept}' || Context from slot: '{context}'")
    
    concepts = list(tracker.get_latest_entity_values("concept"))
    print(f"\n🔍 🔍  Concepts extracted from entities: {concepts}")
    
    complex_tokens = []
    simple_tokens = []
    if concepts: # and concept.strip() != "":
        # check if concept is just one word or multiple words
        for concept in concepts:
            if " " in concept:         
                complex_tokens_split = tokenize_and_clean_text(concept)
                print(f"🔍  Concept '{concept}' split into simple lemma tokens: {complex_tokens_split}")
                for token in complex_tokens_split:
                    simple_tokens.append(token)        
                text = " ".join(complex_tokens_split)
                complex_tokens.append(text)
            else: 
                simple_tokens.append(tokenize_and_clean_text(concept)[0]) # lemmatize and add the single word concept to simple tokens
                print(f"🔍  Concept '{concept}' is a single word. Added to simple tokens: {simple_tokens}")
                
        # stay with acronyms in uppercase from user_message:
        query_tokens = user_message.split()
        for token in query_tokens:
            if token.isupper() and len(token) > 1: # Check if the token is uppercase and has more than 1 character (to avoid adding single letters)
                simple_tokens.append(token)
                print(f"🔍  Added uppercase token '{token}' from user message to simple tokens: {simple_tokens}")
        # remove duplicates from simple_tokens
        simple_tokens = list(set(simple_tokens))
            
    else:
        print(f"\n🔍  No concept identified by Rasa. Proceeding with keywords extraction from the entire query.")
        # Keywords Extraction Process 
        no_punct_query = re.sub(r"[^\w\s\-\&]", "", user_message).strip()  # Remove punctuation except '-' and '&'
        keywords = extract_query_keywords(no_punct_query)
        print(f"🔍  no_punct_query: {no_punct_query}")
        complex_tokens, simple_tokens, _ = keywords_to_tokens(keywords, no_punct_query, context)  
    
    context = " ".join(tokenize_and_clean_text(context)) if context else ""
    print(f"🔍  Tokenized context: {context}")
    
    print(f"\n🔍  Final tokens to be used in search: \n    > Complex tokens: {complex_tokens} \n    > Simple tokens: {simple_tokens}")
    
    print(f"\n🔍  Starting search process in resources: {authorized_resources}")
    # Hybrid Search Process    
    vector_docs, vector_metadata, normalized_vector_scores = dense_vector_search(intent, complex_tokens, simple_tokens, context, user_message, collection, authorized_resources)        
    bm25_docs, bm25_meta, normalized_bm25_scores = hybrid_bm25_search(complex_tokens, simple_tokens, authorized_resources, course_id)
    
    bot_response = None
    if bm25_docs == [] and bm25_meta == []:
        print(f"\n⚠️  BM25 search returned no results for user query: '{user_message}'")
        bot_response = "no_access"
    elif normalized_bm25_scores == []:
        print(f"\n⚠️  Normalized BM25 scores is empty for user query: '{user_message}'")
        bot_response = "no_response"
    if bot_response:
        return  [
            SlotSet("user_query", user_message),  # Store the query
            SlotSet("materials_location", ""), #gemini_results),  # Store selected materials
            SlotSet("bot_response", bot_response),  # Store the bot response -> trigger
            SlotSet("user_email", user_email),  # Store the sender ID
            SlotSet("user_id", user_id),  # Store the user ID
            SlotSet("input_time", input_time),
            SlotSet("concept", ""),
            SlotSet("context", "")
            ]

    
    if complex_tokens:
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
        print("\n🚨  No relevant materials found!")
        return  [
            SlotSet("user_query", user_message),  # Store the query
            SlotSet("materials_location", selected_results), #gemini_results),  # Store selected materials
            SlotSet("bot_response", "I couldn't find relevant content in the course materials."),  # Store the bot response
            SlotSet("user_email", user_email),  # Store the sender ID
            SlotSet("user_id", user_id),  # Store the user ID
            SlotSet("input_time", input_time),
            SlotSet("concept", concept),
            SlotSet("context", context),
            SlotSet("complex_tokens", complex_tokens),
            SlotSet("simple_tokens", simple_tokens)
            ]
    else: 
        # Format results
        results_text = []
        for text_chunk, _, _ in selected_results:
            results_text.append(text_chunk)

        # === PREPARE CONTEXT AND RULES FOR SYSTEM === #
        raw_text = "\n".join(results_text)
        
        if intent != "course info":
            system_instruction = f"""
            ### ROLE
            You are a precise **academic tutor assistant**. Your task is to answer the student's query based strictly on the provided educational course material.

            ### COURSE MATERIAL CONTEXT
            {raw_text}

            ### CRITICAL RULES
            1. **NO MARKDOWN:** Do NOT use asterisks (**) or hashtags (#). 
            2. **HTML ONLY:** Use <b>text</b> for bold and <br> for line breaks.
            3. **CONCISENESS:** Be extremely precise and direct. Do NOT exceed 100 words in your answer.
            4. **STRICTNESS:** Base your answer ONLY on the provided course material above. Do not extrapolate or use outside knowledge.
            5. **FALLBACK:** If you cannot find the relevant information to answer the query within the provided course material, you must reply exactly with this phrase: "I couldn't find relevant content in the course materials."
            6. **LANGUAGE:** Always respond in English (UK).
            
            ### RESPONSE (HTML format)
            """
        else:
            print(f"\n🔍  Intent is 'course info'. Using a different system instruction focused on administrative and logistical information.")
            system_instruction = f"""
            ### ROLE
            You are a precise **academic assistant and course coordinator**. Your task is to answer the student's query regarding course logistics, administration, or syllabus details based strictly on the provided course documentation (such as the course syllabus, grading policy, or official announcements).

            ### COURSE DOCUMENTATION CONTEXT
            {raw_text}

            ### CRITICAL RULES
            1. **NO MARKDOWN:** Do NOT use asterisks (**) or hashtags (#). 
            2. **HTML ONLY:** Use <b>text</b> for bold and <br> for line breaks.
            3. **CONCISENESS & CLARITY:** Be precise and direct. Do NOT exceed 100 words in your answer, but ensure all administrative details requested (dates, percentages, names) are clearly stated.
            4. **STRICTNESS:** Base your answer ONLY on the provided course documentation above. Do not extrapolate, assume, or use outside knowledge about university policies.
            5. **FALLBACK:** If the specific administrative info (e.g., a specific deadline or professor's email) is not explicitly mentioned in the provided text, you must reply exactly with this phrase: "I couldn't find relevant content in the course materials."
            6. **LANGUAGE:** Always respond in English (UK).
            
            ### RESPONSE (HTML format)
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
            user_prompt = f"Student Query: {user_message}"
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
                SlotSet("user_query", user_message),  # Store the query
                SlotSet("materials_location", ""), #gemini_results),  # Store selected materials
                SlotSet("bot_response", "gemini_error"),  # Store the bot response -> trigger
                SlotSet("user_email", user_email),  # Store the sender ID
                SlotSet("user_id", user_id),  # Store the user ID
                SlotSet("input_time", input_time),
                SlotSet("concept", ""),
                SlotSet("context", "")
            ]

    return  [
        SlotSet("user_query", user_message),  # Store the query
        SlotSet("materials_location", selected_results), #gemini_results),  # Store selected materials
        SlotSet("bot_response", formatted_response),  # Store the bot response
        SlotSet("user_email", user_email),  # Store the sender ID
        SlotSet("user_id", user_id),  # Store the user ID
        SlotSet("input_time", input_time),
        SlotSet("concept", concept),
        SlotSet("context", context),
        SlotSet("complex_tokens", complex_tokens),
        SlotSet("simple_tokens", simple_tokens)
        ]

class ActionCreateTopics(Action):
    def name(self):
        return "action_create_topics"

    def run(self, dispatcher, tracker, domain):
        
        print("\n📊  Generating bot 'action_create_topics' response...")

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
                print("\n🎯  Gemini Response Generated Successfully!")
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
        
        #print(f"DEBUG TRACKER SLOTSS: {tracker.current_slot_values()}")
        
        #user_role = tracker.get_slot("user_role")
        #print(f"👤  User role from slot: {user_role}")

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
        #print(f"👩‍🏫  Is teacher ({user_email}) from metadata: {is_teacher}")
        
        intent = "definition of"      
        
        return action_process(dispatcher, tracker, user_message, user_email, input_time, authorized_resources, intent, user_id, course_id)
    
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

        intent = "explanation of"

        return action_process(dispatcher, tracker, user_message, user_email, input_time, authorized_resources, intent, user_id, course_id)

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

        intent = "examples of"
        return action_process(dispatcher, tracker, user_message, user_email, input_time, authorized_resources, intent, user_id, course_id)

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

        intent = "summary of"
        return action_process(dispatcher, tracker, user_message, user_email, input_time, authorized_resources, intent, user_id, course_id)

# === ACTION 4: COMPARE === #
class ActionGetComparison(Action):
    def name(self):
        return "action_get_comparison"

    def run(self, dispatcher, tracker, domain):
        
        print("\n📊  Generating bot 'action_get_comparison' response...")

        user_message = tracker.latest_message.get("text")
        user_email = tracker.sender_id  # ✅ Retrieves the "sender" field
        input_time = tracker.latest_message.get("metadata", {}).get("input_time")
        user_id = tracker.latest_message.get("metadata", {}).get("user_id")
        authorized_resources = tracker.latest_message.get("metadata", {}).get("authorized_resources", [])
        course_id = tracker.latest_message.get("metadata", {}).get("course_id")

        intent = "comparison of"
        return action_process(dispatcher, tracker, user_message, user_email, input_time, authorized_resources, intent, user_id, course_id)


class ActionGetCourseInfo(Action):
    def name(self):
        return "action_get_course_info"

    def run(self, dispatcher, tracker, domain):
        
        print("\n📊  Generating bot 'action_get_course_info' response...")
    
        # Extract variables from chat memory
        user_message = tracker.latest_message.get("text")
        user_email = tracker.sender_id  # ✅ Retrieves the "sender" field
        user_id = tracker.latest_message.get("metadata", {}).get("user_id")
        course_id = tracker.latest_message.get("metadata", {}).get("course_id")
        input_time = tracker.latest_message.get("metadata", {}).get("input_time")
        print(f"🕓  latest_message INPUT TIME: {input_time}")
        authorized_resources = tracker.latest_message.get("metadata", {}).get("authorized_resources", [])
        print(f"📚  Authorized resources from metadata: {authorized_resources}")
        intent = "course info"      
        
        return action_process(dispatcher, tracker, user_message, user_email, input_time, authorized_resources, intent, user_id, course_id)
    
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
        tutor_mode = tracker.latest_message.get("metadata", {}).get("tutor_mode", False)
        #print(f"tutor_mode in ActionGetClassMaterialLocation: {tutor_mode}")
        
        print(f"\n📊  Generating bot 'action_get_class_material_location' response..."
              f"\n> bot_response: {bot_response}")
                
        if bot_response == "no_access":
            dispatcher.utter_message(text="You don't have access to any class materials yet. Please check with your instructor to gain access to the course materials and try again.")
            return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", ""), SlotSet("concept", ""), SlotSet("context", "")]

        if bot_response == "no_response":
            response = f"I couldn't find any relevant content on this topic in the course materials. Please try again."
            save_user_progress(course_id, user_email, user_message, response, [], input_time, user_id, tutor_mode)
            dispatcher.utter_message(text=response)
            return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", ""), SlotSet("concept", ""), SlotSet("context", "")]

        if bot_response == "gemini_error":
            response = f"Sorry, I couldn't process that request due to an error calling Gemini API. Please try again later."
            save_user_progress(course_id, user_email, user_message, response, [], input_time, user_id, tutor_mode)
            dispatcher.utter_message(text=response)
            return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", ""), SlotSet("concept", ""), SlotSet("context", "")]

        if bot_response == "I couldn't find relevant content in the course materials.":
            response = "</br>Please try rephrasing your query."
            save_user_progress(course_id, user_email, user_message, response, [], input_time, user_id, tutor_mode)
            dispatcher.utter_message(text=response)
            return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", ""), SlotSet("concept", ""), SlotSet("context", "")]


        print(f"\n🔖  --------- Getting class materials location --------- 🔖 ")
        
        if len(selected_results) == 0:
            dispatcher.utter_message(text="I couldn't find relevant class materials for your query.")
            print("\n🚨  No relevant materials found!")

        else: # get materials location:
            complex_tokens = tracker.get_slot("complex_tokens") or []
            simple_tokens = tracker.get_slot("simple_tokens") or []
            location_results, pdfs_insights = get_materials_location(selected_results, complex_tokens, simple_tokens, course_id)

            if location_results:
                response = save_user_progress(course_id, user_email, user_message, bot_response, ", ".join(pdfs_insights), input_time, user_id, tutor_mode)
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
                    response = save_user_progress(course_id, user_email, user_message, bot_response, ", ".join(pdfs_insights), input_time, user_id, tutor_mode)
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
        return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", ""), SlotSet("concept", ""), SlotSet("context", ""), SlotSet("complex_tokens", []), SlotSet("simple_tokens", "")]



class ActionShowTopicsForSelection(Action):
    def name(self):
        return "action_show_topics_for_selection"

    def run(self, dispatcher, tracker, domain):
        print("\n📊  Generating topic selection buttons...")
        
        course_id = tracker.latest_message.get("metadata", {}).get("course_id")
        user_id = tracker.latest_message.get("metadata", {}).get("user_id")
        print(f"🎓  User {user_id} from course {course_id}.")
        
        buttons = create_topics_buttons(user_id, course_id)
            
        dispatcher.utter_message(text="", buttons=buttons)
        return []

    
class ActionAnalyzeProgress(Action):
    def name(self):
        return "action_analyze_progress"

    def run(self, dispatcher, tracker, domain):

        print("\n📊  Analyzing user progress for selected topic...")
        
        user_id = tracker.latest_message.get("metadata", {}).get("user_id")
        course_id = tracker.latest_message.get("metadata", {}).get("course_id")
        #user_message = tracker.latest_message.get("metadata", {}).get("user_message", None)
        topic_id = tracker.get_slot("selected_topic")
        print(f"🎓  User {user_id} from course {course_id} selected topic ID: {topic_id}")
        
        if not topic_id:
            dispatcher.utter_message(text="I couldn't identify the topic.")
            return []
        
        topic = requests.get(f"http://flask-server:8080/api/get_topics_from_ids", json={"topics_ids": [topic_id]})
        topic_name = topic.json()[0].get("name", "the selected topic") if topic.status_code == 200 else "the selected topic"
        print(f"📚  User selected topic ID: {topic_id}, name: {topic_name}")
        
        progress = requests.get(f"http://flask-server:8080/api/get_user_progress_by_topic", params={"user_id": user_id, "course_id": course_id, "topic_id": topic_id})
        if progress.status_code == 200:
            progress_data = progress.json()
            print(f"📊  User progress data for topic {topic_name} retrieved: {progress_data}")
        else:
            print(f"❌  Failed to retrieve user progress for topic. Status code: {progress.status_code}")
            progress_data = {}
            return []
        
        ids_list = [entry.get("id") for entry in progress_data if "id" in entry]
        print(f"📊  Extracted progress entry IDs for topic {topic_name}: {ids_list}")
        
        if len(progress_data) > 1:
            print(f"⚠️  Multiple progress entries found for topic {topic_name}. IDs: {ids_list}.")
            # choose one entry
            progress_data = progress_data[0]  # For example, we take the first one. You can implement a more complex logic here if needed.
        else:
            progress_data = progress_data[0]
        print(f"🔍  Selected progress entry for analysis: {progress_data}")
                    
            
        # Conteúdo extraído da tua pesquisa de materiais do curso
        print(f"\n📖  --------- Getting Knowledge --------- 📖 ")
        print(f"\nQUIZ Question: {progress_data['question']} 📩")
        
        authorized_resources = tracker.latest_message.get("metadata", {}).get("authorized_resources", [])
        print(f"📚  Authorized resources from metadata: {authorized_resources}")
        intent = "explanation of"  # Podemos usar a explicação para analisar o progresso do aluno, já que queremos entender onde ele errou e como melhorar
        
        print(f"\n🔍  No concept identified by Rasa. Proceeding with keywords extraction from the entire query.")
        # Keywords Extraction Process 
        no_punct_query = re.sub(r"[^\w\s\-\&]", "", progress_data['question']).strip()  # Remove punctuation except '-' and '&'
        keywords = extract_query_keywords(no_punct_query)
        print(f"🔍  no_punct_query: {no_punct_query}")
        context = None
        complex_tokens, simple_tokens, _ = keywords_to_tokens(keywords, no_punct_query, context)  
        
        context = " ".join(tokenize_and_clean_text(context)) if context else ""
        print(f"🔍  Tokenized context: {context}")
        print(f"\n🔍  Final tokens to be used in search: \n    > Complex tokens: {complex_tokens} \n    > Simple tokens: {simple_tokens}")
        
        print(f"\n🔍  Starting search process in resources: {authorized_resources}")
        # Hybrid Search Process    
        vector_docs, vector_metadata, normalized_vector_scores = dense_vector_search(intent, complex_tokens, simple_tokens, context, topic_id, collection, authorized_resources)        
        bm25_docs, bm25_meta, normalized_bm25_scores = hybrid_bm25_search(complex_tokens, simple_tokens, authorized_resources, course_id)
        
        content_found = True
        if bm25_docs == [] and bm25_meta == []:
            print(f"\n⚠️  BM25 search returned no results for question: '{progress_data['question']}'")
            content_found = False
        elif normalized_bm25_scores == []:
            print(f"\n⚠️  Normalized BM25 scores is empty for question: '{progress_data['question']}'")
            content_found = False
        
        if complex_tokens:
            alpha = 0.75
            print(f"\n🔍  Found keywords: {complex_tokens} and {simple_tokens}. \n     Using hybrid search with alpha = {alpha}")
        else: # Use hybrid search with a higher weight for vector search
            alpha = 0.85
            print(f"\n🔍  Split case: found multiple keywords: {complex_tokens} and {simple_tokens}. Using hybrid search with alpha = {alpha}")
            
        selected_results = hybrid_search(vector_docs, vector_metadata, normalized_vector_scores, bm25_docs, bm25_meta, normalized_bm25_scores, alpha)
        
        if len(selected_results) == 0:
            print("\n🚨  No relevant materials found!")
            content_found = False
        else: 
            # Format results
            results_text = []
            for text_chunk, _, _ in selected_results:
                results_text.append(text_chunk)
            raw_text = "\n".join(results_text)   
        
        if not content_found:
            print("\n🚨  No relevant content found in course materials for the quiz question.")
            dispatcher.utter_message(text="I couldn't find relevant content in the course materials to analyze your answer. Please try again later or check with your instructor.")
            return []

        # === PREPARE THE PROMPTS === #

        system_instruction = """
        # ROLE:
        You are an empathetic, precise, and encouraging AI Tutor. Your job is to analyze a student's wrong answer in a quiz, compare it with the correct course material, and explain why their answer was incorrect and how to reach the right conclusion.

        # RULES:
        1. NO MARKDOWN: Do NOT use asterisks (**), hashtags (#), or markdown lists.
        2. HTML ONLY: Use <b>text</b> for emphasis, <ul><li></li></ul> for lists, and <br> for line breaks.
        3. LANGUAGE: Always respond in English.
        4. TONE: Supportive, constructive, and educational. Do not say "You are wrong". Instead, use "Your answer 'X' differs because...".
        5. BREVITY: Keep it concise. The student is in a sidebar; they need a quick, clear explanation.

        # STRUCTURE FOR THE OUTPUT:
        - <b>Question:</b> Restate the quiz question for clarity.
        - <b>Concept Check:</b> Briefly explain the core concept from the course material.
        - <b>Why it missed the mark:</b> Address the student's specific answer (or if it was 'Sem resposta', encourage them).
        - <b>How to remember:</b> Give a 1-sentence tip or explanation to secure the correct answer.
        """

        # No user_prompt passamos as variáveis dinâmicas desta pergunta específica
        user_prompt = f"""
        Course Material Context:
        {raw_text}

        Quiz Interaction:
        - Question Asked: {progress_data['question']}
        - Student's Answer: {progress_data['student_answer']}
        - Correct Answer: {progress_data['correct_answer']}

        Please provide the HTML feedback analysis.
        """

        # === CALL GEMINI API === #
        generation_config = {
            "temperature": 0.1, # Ótimo para manter a precisão e evitar alucinações sobre a matéria
        }

        try:
            g_model = genai.GenerativeModel(
                model_name=MODEL_NAME,
                system_instruction=system_instruction,
                generation_config=generation_config
            )
            response = g_model.generate_content(user_prompt)
            html_feedback = response.text
            
        except Exception as e:
            print(f"Error calling Gemini: {e}")
            
            
        
        print(f"\n🔖  --------- Getting class materials location --------- 🔖 ")

        location_results, _ = get_materials_location(selected_results, complex_tokens, simple_tokens, course_id)
        location_materials_text = "<span style='font-size: 11px;'>You can find related information in:</span></br><i><span style='font-size: 10px;'>" + "</br>".join(location_results) + "</span></i>"
        
        if not location_results:
            # no exact references found, so return related PDFs found in previous function
            if selected_results:
                location_results, _ = update_materials_location(selected_results)
                location_materials_text = "<span style='font-size: 11px;'>You can find related information in:</span></br><i><span style='font-size: 10px;'>" + "</br>".join(location_results) + "</span></i>"
            else:                
                print("\n ⚠️  No exact references found, but you might check related PDFs.")
                location_materials_text = "<span style='font-size: 11px;'>You can find related information in:</span></br><i><span style='font-size: 10px;'>I couldn't find specific page references for your question.</span></i>"

                    
        update_response = requests.post(f"http://flask-server:8080/api/update_progress_state", params={"ids": ids_list, "new_state": "reviewed"})
        if update_response.status_code == 200:
            print(f"✅  Progress entries for topic {topic_name} updated successfully.")
        else:
            print(f"❌  Failed to update progress entries for topic. Status code: {update_response.status_code}")

        buttons = create_topics_buttons(user_id, course_id)
        if not buttons:
            dispatcher.utter_message(text=f"{html_feedback}<br/><br/>{location_materials_text}<br/><br/>You have reviewed all topics! Great job! 🎉")
        else:
            dispatcher.utter_message(text=f"{html_feedback}<br/><br/>{location_materials_text}<br/><br/>You can choose another topic to explore:<br/>", buttons=buttons)
        return []
