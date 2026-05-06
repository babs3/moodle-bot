print("🚀  A carregar o ficheiro actions.py...")
import sys
sys.modules["sqlite3"] = __import__("pysqlite3")
import chromadb
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk import Action, Tracker
from rasa_sdk import Action
from rasa_sdk.events import SlotSet
from .utils import *

VECTOR_DB_PATH = "/app/vector_store"
print(f"📂  A tentar ligar ao ChromaDB em: {VECTOR_DB_PATH}")
# Em vez de PersistentClient, usamos HttpClient
# Lembra-te: o host é 'chroma' (nome do serviço no docker-compose) 
try:
    chroma_client = chromadb.HttpClient(host='chroma', port=8000)
    print("📡  Cliente ChromaDB instanciado...")
    
    collection = chroma_client.get_collection(name="class_materials")
    print("✅  Collection reloaded successfully.")
except Exception as e:
    print(f"❌  ERRO CRÍTICO NO CHROMA: {str(e)}")

class ActionSetUsername(Action):
    def name(self) -> str:
        return "action_set_username"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: dict):

        # Extract metadata
        metadata = tracker.latest_message.get("metadata", {})
        username = metadata.get("username")

        if username:
            dispatcher.utter_message(text=f"Hello {username}! How can I help you today?")
            return [SlotSet("username", username)]
        else:
            dispatcher.utter_message(text="Hello! I'm here to assist with your learning! How can I help you today?")
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

def action_process(dispatcher, user_message, user_email, input_time, authorized_resources, intent, user_id, tutor_mode):
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
    bm25_docs, bm25_meta, normalized_bm25_scores = hybrid_bm25_search(complex_tokens, simple_tokens, authorized_resources)
    
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

        # === PREPARE QUERY FOR GEMINI === #
        raw_text = "\n".join(results_text)
        prompt = f" Use the following raw educational content to answer the student query '{query}': \n{raw_text} \nDon's exceed 50 words and be concise and precise in your answer. If you don't find relevant information, say you couldn't find relevant content in the course materials."
        
        formatted_response = "Sorry, I couldn't generate a response..."
        try:
            response = g_model.generate_content(prompt)

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
        
        prompt = "Dadas as seguintes perguntas, cria um tópico (em inglês) para cada uma delas. Sempre que possivel, tenta agrupar perguntas relacionadas no mesmo tópico. "
        prompt += "Responde apenas com um JSON no seguinte formato: { 'id': 'id_original', 'question': 'pergunta original', 'topic': 'tópico gerado para a pergunta' }. "
        prompt += "Se não conseguires gerar um tópico para uma pergunta, deixa o campo 'topic' vazio. Aqui estão as perguntas: "
        for pergunta in perguntas:
            prompt += "\n- ID: " + str(pergunta.get("moodle_question_id", "")) + ", question: " + pergunta.get("texto_pergunta", "") + ", topic: ?" # Acessa a pergunta usando .get() para evitar erros se a chave não existir
        
        try:
            response = g_model.generate_content(prompt)
            
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

        user_message = tracker.latest_message.get("text")
        user_email = tracker.sender_id  # ✅ Retrieves the "sender" field
        user_id = tracker.latest_message.get("metadata", {}).get("user_id")
        input_time = tracker.latest_message.get("metadata", {}).get("input_time")
        print(f"🕓  latest_message INPUT TIME: {input_time}")
        authorized_resources = tracker.latest_message.get("metadata", {}).get("authorized_resources", [])
        print(f"📚  Authorized resources from metadata: {authorized_resources}")
        tutor_mode = tracker.latest_message.get("metadata", {}).get("tutor_mode", False)
        print(f"🎓  Tutor mode from metadata: {tutor_mode}")
        
        intent = "definition of "
        
        # Convert ISO 8601 timestamp string back to a datetime object
        timestamp_str = input_time
        timestamp = None
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str)
        print(f"   Decripted timestamp: {timestamp}")        
        
        return action_process(dispatcher, user_message, user_email, input_time, authorized_resources, intent, user_id, tutor_mode)
    
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
        tutor_mode = tracker.latest_message.get("metadata", {}).get("tutor_mode", False)
        
        intent = "explanation of "

        return action_process(dispatcher, user_message, user_email, input_time, authorized_resources, intent, user_id, tutor_mode)

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
        authorized_resources = tracker.latest_message.get("metadata", {}).get("authorized_resources", [])
        tutor_mode = tracker.latest_message.get("metadata", {}).get("tutor_mode", False)
        
        intent = "examples of "
        return action_process(dispatcher, user_message, user_email, input_time, authorized_resources, intent, user_id, tutor_mode)

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
        tutor_mode = tracker.latest_message.get("metadata", {}).get("tutor_mode", False)
        
        intent = "summary of "
        return action_process(dispatcher, user_message, user_email, input_time, authorized_resources, intent, user_id, tutor_mode)  


# === FINAL ACTION: GET PDF NAMES & PAGE LOCATIONS === #
class ActionGetClassMaterialLocation(Action):
    def name(self):
        return "action_get_class_material_location"

    def run(self, dispatcher, tracker, domain):

        bot_response = tracker.get_slot("bot_response")
        input_time = tracker.get_slot("input_time")
        selected_results = tracker.get_slot("materials_location")
        user_id = tracker.get_slot("user_id")
        user_email = tracker.get_slot("user_email")
        user_message = tracker.get_slot("user_query")
        query = treat_raw_query(user_message)
        tutor_mode = tracker.latest_message.get("metadata", {}).get("tutor_mode", False)
        print(f"tutor_mode in ActionGetClassMaterialLocation: {tutor_mode}")
        
        if bot_response == "no_access":
            dispatcher.utter_message(text="You don't have access to any class materials yet. Please check with your instructor to gain access to the course materials and try again.")
            return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", "")]

        if bot_response == "no_response":
            response = f"I couldn't find any relevant content on this topic in the course materials. Please try again."
            save_user_progress(user_email, user_message, response, [], input_time, user_id, tutor_mode)
            dispatcher.utter_message(text=response)
            return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", "")]

        if bot_response == "gemini_error":
            response = f"Sorry, I couldn't process that request due to an error calling Gemini API. Please try again later."
            save_user_progress(user_email, user_message, response, [], input_time, user_id, tutor_mode)
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
            location_results, pdfs_insights = get_materials_location(selected_results, complex_tokens, simple_tokens)

            if location_results:
                response = save_user_progress(user_email, query, bot_response, ", ".join(pdfs_insights), input_time, user_id, tutor_mode)
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
                    response = save_user_progress(user_email, query, bot_response, ", ".join(pdfs_insights), input_time, user_id, tutor_mode)
                    #dispatcher.utter_message(text="</br></br>You can find related information in:</br>" + "</br>".join(location_results))
                    dispatcher.utter_message(
                        text="</br></br><span style='font-size: 11px;'>You can find related information in:</span></br><i><span style='font-size: 10px;'>" 
                        + "</br>".join(location_results) + 
                        "</span></i>"
                )
                else:                
                    print("\n ⚠️  No exact references found, but you might check related PDFs.")
                    response = save_user_progress(user_email, user_message, bot_response, [], input_time, user_id, tutor_mode)
                    dispatcher.utter_message(text="I couldn't find specific page references for your question.")

        #clear the slots
        return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", "")]


class ActionGenerateInitialMenuButtons(Action):
    def name(self):
        return "action_generate_initial_menu_buttons"

    def run(self, dispatcher, tracker, domain):
        print("\n📊  Generating initial menu buttons...")
        
        #user_email = tracker.sender_id
        user_id = tracker.latest_message.get("metadata", {}).get("user_id")
        user_message = tracker.latest_message.get("metadata", {}).get("user_message", None)
        print(f"🎓  User {user_id} sent message: {user_message}")
        
        # get user progress
        progress = requests.get(f"http://flask-server:8080/api/get_user_progress/{user_id}")
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
    