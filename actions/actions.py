import sys
sys.modules["sqlite3"] = __import__("pysqlite3")
import chromadb
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk import Action, Tracker
from rasa_sdk import Action
from rasa_sdk.events import SlotSet
from .utils import *

# Connect to ChromaDB    
VECTOR_DB_PATH = "vector_store"
chroma_client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
collection = chroma_client.get_collection(name="class_materials")
print("\n✅ Collection reloaded successfully.")

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
    
    
 
def action_process(dispatcher, user_message, user_email, input_time, intent, user_id):
    print(f"\n🧒  User ({user_email}) said: {user_message} 📩")
    query = treat_raw_query(user_message)
    
    # Keywords Extraction Process 
    no_punct_query = re.sub(r"[^\w\s\-\&]", "", query).strip()  # Remove punctuation except '-' and '&'
    keywords = extract_query_keywords(no_punct_query)
    complex_tokens, simple_tokens, split_keywords = keywords_to_tokens(keywords, no_punct_query)  
    print(f"\n🔍  Extracted keywords: \n    {complex_tokens} \n    {simple_tokens} \n    Split keywords flag: {split_keywords}")
    
    # Hybrid Search Process    
    vector_docs, vector_metadata, normalized_vector_scores = dense_vector_search(keywords, query, split_keywords, collection, intent)
    bm25_docs, bm25_meta, normalized_bm25_scores = hybrid_bm25_search(complex_tokens, simple_tokens)
        
    if normalized_bm25_scores == []:
        dispatcher.utter_message(text="Sorry, I couldn't find any relevant class materials for that subject.")
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
                print(formatted_response[:100] + "...")
                dispatcher.utter_message(text=formatted_response)
                
                save_user_progress(user_email, user_message, response, None, [], input_time, user_id)
            else:
                print("\n ⚠️  Gemini Response is empty.")
                dispatcher.utter_message(text=formatted_response)
        except Exception as e:
            dispatcher.utter_message(text="Sorry, I couldn't process that request due to an error calling Gemini API")
            selected_results = []  # Clear selected results
            print(f"\n❌  Error calling Gemini API: {e}")
            return  [
                SlotSet("user_query", query),  # Store the query
                SlotSet("materials_location", ""), #gemini_results),  # Store selected materials
                SlotSet("bot_response", "no_response"),  # Store the bot response
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
        print(f"\n🕓  latest_message INPUT TIME: {input_time}")
        # Convert ISO 8601 timestamp string back to a datetime object
        timestamp_str = input_time
        timestamp = None
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str)
        print(f"   Decripted timestamp: {timestamp}")
        
        intent = "definition of "
        
        return action_process(dispatcher, user_message, user_email, input_time, intent, user_id=user_id)
    
# === ACTION 2: GET EXPLANATION === #
class ActionGetExplanation(Action):
    def name(self):
        return "action_get_explanation"

    def run(self, dispatcher, tracker, domain):
        
        print("\n📊  Generating bot 'action_get_explanation' response...")

        user_message = tracker.latest_message.get("text")
        user_email = tracker.sender_id  # ✅ Retrieves the "sender" field
        input_time = tracker.latest_message.get("metadata", {}).get("input_time")
        intent = "explanation of "
        
        return action_process(dispatcher, user_message, user_email, input_time, intent)

# === ACTION 3: GET EXAMPLES === #
class ActionGetExamples(Action):
    def name(self):
        return "action_get_examples"

    def run(self, dispatcher, tracker, domain):
        
        print("\n📊  Generating bot 'action_get_examples' response...")

        user_message = tracker.latest_message.get("text")
        user_email = tracker.sender_id  # ✅ Retrieves the "sender" field
        input_time = tracker.latest_message.get("metadata", {}).get("input_time")
        intent = "examples of "
        
        return action_process(dispatcher, user_message, user_email, input_time, intent)

# === ACTION 4: SUMMARIZE === #
class ActionGetSummary(Action):
    def name(self):
        return "action_get_summary"

    def run(self, dispatcher, tracker, domain):
        
        print("\n📊  Generating bot 'action_get_summary' response...")

        user_message = tracker.latest_message.get("text")
        user_email = tracker.sender_id  # ✅ Retrieves the "sender" field
        input_time = tracker.latest_message.get("metadata", {}).get("input_time")
        intent = "summary of "
        
        return action_process(dispatcher, user_message, user_email, input_time, intent)


# === FINAL ACTION: GET PDF NAMES & PAGE LOCATIONS === #
class ActionGetClassMaterialLocation(Action):
    def name(self):
        return "action_get_class_material_location"

    def run(self, dispatcher, tracker, domain):

        bot_response = tracker.get_slot("bot_response")
        input_time = tracker.get_slot("input_time")
        print(f"\n🕓  materialsLocation INPUT TIME: {input_time}")
        selected_results = tracker.get_slot("materials_location")
        user_id = tracker.get_slot("user_id")
        user_email = tracker.get_slot("user_email")
        user_message = tracker.get_slot("user_query")
        query = treat_raw_query(user_message)
        
        if bot_response == "no_response":
            response = f"I couldn't find any relevant content on this topic in the course materials. Please try again."
            save_user_progress(user_email, user_message, response, None, [], input_time, user_id=user_id)
            dispatcher.utter_message(text=response)
            return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", "")]

        topic = get_query_topic(query, bot_response)
        
        
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
                response = save_user_progress(user_email, query, bot_response, topic, ", ".join(pdfs_insights), input_time)
                print(f"--> SAVED USER PROGRESS: {response}")
                print_results(location_results)              
            
                # check if the user is logged with g.uporto accout
                if is_uporto_email(user_email) == False:
                    print(f"⚠️  User with ID {user_email} is not part of FEUP's community.")
                    return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("user_email", ""), SlotSet("user_query", ""), SlotSet("input_time", "")]
                
                dispatcher.utter_message(text="You can find related information in:\n" + "\n".join(location_results))
            else:
                # no exact references found, so return related PDFs found in previous function
                if selected_results:
                    
                    location_results, pdfs_insights = update_materials_location(selected_results)
                    response = save_user_progress(user_email, query, bot_response, topic, ", ".join(pdfs_insights), input_time)
                    
                    # check if the user is logged with g.uporto accout
                    if is_uporto_email(user_email) == False:
                        print(f"⚠️  User with ID {user_email} is not part of FEUP's community.")
                        return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("user_email", ""), SlotSet("user_query", ""), SlotSet("input_time", "")]
                
                    dispatcher.utter_message(text="You can find related information in:\n" + "\n".join(location_results))
                
                else:                
                    print("\n ⚠️  No exact references found, but you might check related PDFs.")
                    
                    response = save_user_progress(user_email, user_message, bot_response, topic, [], input_time)
                    # check if the user is logged with g.uporto accout
                    if is_uporto_email(user_email) == False:
                        print(f"⚠️  User with ID {user_email} is not part of FEUP's community.")
                        return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", "")]
                
                    dispatcher.utter_message(text="I couldn't find specific page references for your question.")

        #clear the slots
        return [SlotSet("materials_location", []), SlotSet("bot_response", []), SlotSet("sender_id", ""), SlotSet("user_query", ""), SlotSet("input_time", "")]


class ActionGetTotalQuestions(Action):
    def name(self):
        return "action_get_total_questions"

    def run(self, dispatcher, tracker, domain):
        print("\n📊 Getting total questions asked by students...")
        teacher_email = tracker.sender_id
        selected_class_name = tracker.latest_message.get("metadata", {}).get("selected_class_name")
        selected_class_number = tracker.latest_message.get("metadata", {}).get("selected_class_number")
        selected_group = tracker.latest_message.get("metadata", {}).get("selected_group")

        print(f"Selected class: {selected_class_name}-{selected_class_number}")
        print(f"Selected group: {selected_group}")
        
        df = get_progress(teacher_email, selected_class_name, selected_class_number, selected_group)
        if df.empty:
            dispatcher.utter_message(text="There are no questions asked by students yet.")
            return []
        
        result = df.shape[0]
        dispatcher.utter_message(text=f"📊 Students have asked **{result}** questions in total.")
        return []
    
class ActionGetMostPopularTopics(Action):
    def name(self):
        return "action_get_most_popular_topics"

    def run(self, dispatcher, tracker, domain):
        print("\n📊 Getting most popular topics...")
        teacher_email = tracker.sender_id
        selected_class_name = tracker.latest_message.get("metadata", {}).get("selected_class_name")
        selected_class_number = tracker.latest_message.get("metadata", {}).get("selected_class_number")
        selected_group = tracker.latest_message.get("metadata", {}).get("selected_group")

        print(f"Selected class: {selected_class_name}-{selected_class_number}")
        print(f"Selected group: {selected_group}")
        
        df = get_progress(teacher_email, selected_class_name, selected_class_number, selected_group)
        if df.empty:
            dispatcher.utter_message(text="There are no questions asked by students yet.")
            return []        

        df["topic"] = df["topic_id"].apply(lambda x: get_topic(x).get("topic").str.lower() if x else "No Topic")
        topic_counts = df["topic"].value_counts().reset_index()
        topic_counts.columns = ["topic", "Frequency"]
        # sort by frequency
        topic_counts = topic_counts.sort_values(by="Frequency", ascending=False)
        # get the top 5 topics
        top_topics = topic_counts.head(10)
        topics_name = top_topics["topic"].tolist()
        # create a string with the topics to be displayed
        topics_name_string = "\n\n".join([f"📄 {topic} ({top_topics[top_topics['topic'] == topic]['Frequency'].values[0]} references)" for topic in topics_name])

        if not top_topics.empty:
            dispatcher.utter_message(text=f"📊 Most searched Topics are:\n\n{topics_name_string}")
        else:
            dispatcher.utter_message(text="I couldn't find any popular topics.")

        return []
    
class ActionGetMostReferencedPDFs(Action):
    def name(self):
        return "action_get_most_referenced_pdfs"

    def run(self, dispatcher, tracker, domain):
        print("\n📊 Getting most referenced PDFs...")
        teacher_email = tracker.sender_id
        selected_class_name = tracker.latest_message.get("metadata", {}).get("selected_class_name")
        selected_class_number = tracker.latest_message.get("metadata", {}).get("selected_class_number")
        selected_group = tracker.latest_message.get("metadata", {}).get("selected_group")

        print(f"Selected class: {selected_class_name}-{selected_class_number}")
        print(f"Selected group: {selected_group}")

        df = get_progress(teacher_email, selected_class_name, selected_class_number, selected_group)
        if df.empty:
            dispatcher.utter_message(text="There are no questions asked by students yet.")
            return []       

        if not df.empty:
            pdf_list = []
            for pdfs in df["pdfs"].dropna():
                for pdf in pdfs.split(","):
                    pdf_list.append(pdf.split(" (Pages")[0].strip())

            #print(f"\n📖  Found {len(pdf_list)} PDFs:")
            #for pdf in pdf_list:
            #    print(f"📄  PDF: {pdf}")
                
            # === COUNT PDF REFERENCES === #           
            aux_dict = {}
            for pdf in pdf_list:
                if pdf in aux_dict:
                    aux_dict[pdf] += 1
                else:
                    aux_dict[pdf] = 1
            # Sort the dictionary by value (count) in descending order
            sorted_dict = dict(sorted(aux_dict.items(), key=lambda item: item[1], reverse=True))
            # Get the top 5 most referenced PDFs
            #top_pdfs = dict(list(sorted_dict.items())[:5])
            
            #print(f"\n📖  Top 5 most referenced PDFs:")
            #for pdf, count in top_pdfs.items():
            #    print(f"📄  PDF: {pdf} | Count: {count}")
                
            pdf_name_string = "\n\n".join([f"📄 {pdf} ({count} references)" for pdf, count in sorted_dict.items()])
            dispatcher.utter_message(text=f"📊 Most referenced PDFs are:\n\n{pdf_name_string}")
            
        else:
            dispatcher.utter_message(text="I couldn't find any referenced PDFs.")

        return []
    
class ActionTeacherCustomQuestion(Action):
    def name(self):
        return "action_teacher_custom_question"
    
    def run(self, dispatcher, tracker, domain):
        print("\n📊  Generating bot response...")
        teacher_email = tracker.sender_id
        teacher_question = tracker.latest_message.get("metadata", {}).get("teacher_question")
        selected_class_name = tracker.latest_message.get("metadata", {}).get("selected_class_name")
        selected_class_number = tracker.latest_message.get("metadata", {}).get("selected_class_number")
        selected_group = tracker.latest_message.get("metadata", {}).get("selected_group")

        print(f"Selected class: {selected_class_name}-{selected_class_number}")
        print(f"Selected group: {selected_group}")
        print(f"Teacher question: {teacher_question}")

        df = get_progress(teacher_email, selected_class_name, selected_class_number, selected_group)
        if df.empty:
            dispatcher.utter_message(text="There are no questions asked by students yet.")
            return []       

        # remove columns that are not needed
        df = df.drop(columns=["response"])

        prompt = f"The information below summarises the questions asked by students. Given this, formulate an answer taking into account the teacher's question: '{teacher_question}'. \n{df.to_string()}"
        formatted_response = "Sorry, I couldn't generate a response..."
        print(f"\nTeacher Prompt: {prompt}")
        try:
            response = g_model.generate_content(prompt)

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
