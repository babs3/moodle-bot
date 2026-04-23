import spacy
#from fuzzywuzzy import fuzz
from thefuzz import fuzz, process
import pickle
from difflib import get_close_matches
import re
import requests
from itertools import product
from nltk.corpus import wordnet
import json
import pandas as pd
from datetime import datetime, timezone
from sentence_transformers import SentenceTransformer, util
import numpy as np
import google.generativeai as genai
import os
from nltk import ngrams

# Set up Google Gemini API Key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

#print("Available Gemini Models:")
#for m in genai.list_models():
#    print(m.name)

def get_first_gemini_pro_model():
    """
    Return the first model name that matches pattern:
      models/gemini-<version>-pro
    Raises RuntimeError if none found.
    """
    pattern = re.compile(r"^models/gemini-(\d+(?:\.\d+)*)-pro$")

    for m in genai.list_models():
        # m is typically an object with attribute `name`
        name = getattr(m, "name", None)
        if not name:
            # fallback if the returned item is the string itself
            name = m

        if isinstance(name, bytes):
            name = name.decode()

        if isinstance(name, str) and pattern.match(name):
            return name

    raise RuntimeError("No 'models/gemini-*-pro' model found")

model_name = get_first_gemini_pro_model()
print(f"✅ Using model: {model_name}")

g_model = genai.GenerativeModel(model_name)
    
# Load Spacy model for NLP tasks
nlp = spacy.load("en_core_web_sm")

# Load sentence transformer model
#model = SentenceTransformer("all-MiniLM-L6-v2")
model = SentenceTransformer("/app/models/all-MiniLM-L6-v2")

# Load BM25 index
with open(f"vector_store/bm25_index.pkl", "rb") as f:
    bm25_simple, bm25_2gram, bm25_3gram, bm25_metadata, bm25_documents = pickle.load(f)
    
def tokenize_and_clean_text(text):
    doc = nlp(text)
    tokens = [
        token.lemma_.lower()  # use lemma (base form), lowercase
        for token in doc
        if not token.is_stop and token.is_alpha  # remove stopwords and punctuation/numbers
    ]
    # Remove duplicates while preserving order
    tokens = list(dict.fromkeys(tokens))
    return tokens

def normalize_score(scores, is_vector):
    """Normalizes scores to a range of 0 to 1."""
    if is_vector:
        best_score = min(scores)
        normalized_scores = [round(best_score / score, 4) for score in scores]
    else:
        best_score = max(scores)
        normalized_scores = [round(score / best_score, 4) for score in scores]
    return normalized_scores

def normalize_bm25_indexes(scores):
    scores = np.array(scores)
    max_score = scores.max()
    return scores / max_score if max_score > 0 else scores

def save_user_progress(user_email, user_message, bot_response, pdfs, input_time_str, user_id):

    print(f"\n📍  Saving user progress for email: {user_email}, ID: {user_id}")
    
    # Extracting the timestamp part
    input_time_cleaned = input_time_str.split("input_time: ")[-1].strip()
    #print(f"\n🕓  Input time cleaned: {input_time_cleaned}")

    # Converting to timezone-aware datetime in UTC
    input_time = datetime.fromisoformat(input_time_cleaned).astimezone(timezone.utc)
    #print(f"   Input time (UTC): {input_time}")

    # Getting current UTC time
    now_utc = datetime.now(timezone.utc)
    #print(f"   Current time (UTC): {now_utc}")

    # Calculating response time
    response_timestamp = (now_utc - input_time).total_seconds()
    print(f" 🕓  Response time: {response_timestamp}")

    # Saving
    data = {
        "user_id": user_id,  # Use Moodle user ID
        "question": user_message,
        "response": bot_response,
        "pdfs": pdfs,
        "response_time": response_timestamp
    }
    
    requests.post("http://flask-server:8080/api/save_moodle_messages", json=data)
    

QUESTION_WORDS = {"what", "who", "where", "when", "why", "how"}

def clean_key_phrase(phrase):
    """Basic cleaner to normalize noun phrases."""
    phrase = phrase.lower().strip()
    
    if phrase.startswith("the "):
        phrase = phrase[4:]
        
    words = phrase.split()
    words = [w for w in words if w not in QUESTION_WORDS]
    phrase = " ".join(words)
    
    return phrase

def extract_query_keywords(query):
    """
    Extracts the most meaningful keyword or phrase from a user query.
    Returns a list of keywords, prioritizing multi-word noun phrases.
    """
    doc = nlp(query.lower())

    multi_word_phrases = []
    used_tokens = set()

    # Extract cleaned multi-word noun phrases
    for chunk in doc.noun_chunks:
        phrase = clean_key_phrase(chunk.text)
        if len(phrase.split()) > 1:
            multi_word_phrases.append(phrase)
            used_tokens.update(phrase.split())

    # If we got a strong multi-word phrase, prefer it
    if multi_word_phrases:
        return multi_word_phrases
        #return list(dict.fromkeys(multi_word_phrases))  # Remove duplicates while preserving order

    # Fallback: extract individual nouns/proper nouns not part of previous phrases
    single_words = []
    for token in doc:
        if token.pos_ in {"NOUN", "PROPN"} and not token.is_stop:
            if token.text:
                single_words.append(token.text.lower())

    return single_words
    #return list(dict.fromkeys(single_words))  # Preserve order, remove duplicates
    

def format_gemini_response(text: str) -> str:
    """
    Format Gemini response for Streamlit:
    - Replace triple backticks (```) with ** for bold formatting.
    - Escape $ symbols to prevent unintended formatting in Streamlit.
    
    Args:
        text (str): The response text from Gemini.
    
    Returns:
        str: The formatted text with ** tags instead of triple backticks and escaped $ symbols.
    """
    # Replace triple backticks with bold (**)
    text = re.sub(r'```(.*?)```', r'*\1*', text, flags=re.DOTALL)
    
    # Escape $ symbols (replace single $ with \$ to prevent LaTeX formatting in Streamlit)
    text = text.replace("$", "\\$")
    
    return text

def is_uporto_email(email):
    # Check if the email domain is "uporto.pt"
    if email.endswith("@g.uporto.pt") or email.endswith("@fe.up.pt"):
        return True
    else:
        #st.error("❌ Invalid email domain. Please use your UPorto email.")
        return False

def lemmatize_word(word):
    """Returns the lemma of a given word (e.g., 'methods' → 'method')."""
    doc = nlp(word)
    return doc[0].lemma_  # Return the base form (lemma)

def fuzzy_match_old(query_tokens, document_tokens, threshold=80):
    """Matches query tokens against document tokens, handling lemmatization & fuzzy similarity."""
    
    #doc_text = " ".join(document_tokens).lower()  # Join doc tokens into full text
    query_tokens = [qt.lower() for qt in query_tokens]  # Lowercase query tokens
    
    for query_token in query_tokens:
        lemma_query = lemmatize_word(query_token)  # Convert to base form
        print(f"\n- 🐟  Query token: '{query_token}' (lemma: '{lemma_query}')")
        
        if " " in query_token:  # If query token is a phrase (e.g., "pestel framework")
            if query_token in document_tokens: # or lemma_query in doc_text:  # Check for phrase
                print(f"  💚  Complex match in query_token '{query_token}'.") #:\n{doc_text}")
                return True
        else:  # Single word matching
            for doc_token in document_tokens:
                lemma_doc = lemmatize_word(doc_token)  # Lemmatize doc token
                # Allow exact match, lemmatized match, or fuzzy match
                if (query_token == doc_token or  
                    lemma_query == lemma_doc or  
                    fuzz.token_set_ratio(query_token, doc_token) >= threshold):
                    print(f"\n  🤍  Simple Match in query_token '{query_token}'=='{doc_token}' or lemma_query '{lemma_query}'=='{lemma_doc}'")
                    return True  

    return False  # No match found

def fuzzy_match_simple_tokens(query_tokens, simple_tokens, threshold=80):
    matched = []
    if not simple_tokens:
        print("⚠️  Warning: No tokens provided for matching.")
        return matched
    
    for token in query_tokens:
        match, score = process.extractOne(token, simple_tokens, scorer=fuzz.ratio)
        print(f"Query Simple Token: '{token}' → Best Match: '{match}' (Score: {score})")
        if score >= threshold:
            print("✅  Match accepted!")
            matched.append((token, match, score))
            
    return matched


def fuzzy_match_complex_tokens(query_tokens, multi_word_tokens, threshold=80):

    matched = []
    if not multi_word_tokens:
        print("⚠️  Warning: No multi-word tokens provided for matching.")
        return matched
    
    for token in query_tokens:
        result = process.extractOne(token, multi_word_tokens, scorer=fuzz.token_set_ratio)
        if result is None:
            #print(f"❌ No matches found for query token: '{token}'")
            continue
        
        match, score = result
        print(f"Query Complex Token: '{token}' → Best Match: '{match}' (Score: {score})")
        
        # Check actual word overlap
        token_words = set(token.lower().split())
        match_words = set(match.lower().split())
        common_words = token_words & match_words

        if score >= threshold and len(common_words) >= 2:
            print(f"✅ Match accepted! Shared words: {common_words}")
            matched.append((token, match, score))
        #else:
            #print("❌ Match rejected. Too little overlap.")

    return matched


def extract_simple_tokens(query): # ['pestel', 'analysis']
    """Extracts only meaningful single-word tokens from a query (excluding stopwords & phrases)."""
    doc = nlp(query.lower())  # Process query with NLP model
    keywords = []
    
    for token in doc:
        if token.pos_ in {"NOUN", "PROPN"} and not token.is_stop:
            keywords.append(token.text)

        # Include adjectives that appear **before** a noun (e.g., "financial management")
        elif token.pos_ == "ADJ" and token.dep_ in {"amod", "compound"}:
            keywords.append(token.text)

    # Remove duplicates while preserving order
    keywords = list(dict.fromkeys(keywords))
    return keywords

# Collect all unique words from BM25 documents to compare for spell correction
VALID_SIMPLE_WORDS = set() # TODO
for doc_text in bm25_documents:
    VALID_SIMPLE_WORDS.update(extract_simple_tokens(doc_text))

def group_pages_by_pdf(document_entries):
    """
    Groups consecutive pages for the same PDF into a range format.
    Example:
        Input: [("file1.pdf", 1), ("file1.pdf", 2), ("file1.pdf", 3), ("file2.pdf", 10), ("file2.pdf", 12)]
        Output: ["file1.pdf (Pages 1-3)", "file2.pdf (Pages 10, 12)"]
    """
    grouped_results = []
    current_pdf = None
    current_pages = []

    for file_name, pages in document_entries:
        pages_list = pages.split("-")
        # Convert to integers and sort
        pages_list = [int(page) for page in pages_list if page.isdigit()]
        if file_name != current_pdf:  
            # If switching to a new PDF, store the previous result
            if current_pdf:
                grouped_results.append(format_page_range(current_pdf, current_pages))
            # Reset tracking for new PDF
            current_pdf = file_name
            tmp_list = []
            for page in pages_list:
                if page not in tmp_list:
                    tmp_list.append(page)
            current_pages = tmp_list
        else:
            for page in pages_list:
                if page not in current_pages:
                    current_pages.append(page)

    # Add the last processed PDF
    if current_pdf:
        grouped_results.append(format_page_range(current_pdf, current_pages))

    return grouped_results

def format_page_range(file_name, pages):
    """
    Converts a list of page numbers into a formatted string.
    Example:
        Input: "file1.pdf", [1, 2, 3, 5, 6, 8]
        Output: "📄 file1.pdf (Pages 1-3, 5-6, 8)"
    """
    # 
    pages.sort()
    ranges = []
    start = pages[0]

    for i in range(1, len(pages)):
        if pages[i] != pages[i - 1] + 1:  # Break in sequence
            if start == pages[i - 1]:
                ranges.append(f"{start}")
            else:
                ranges.append(f"{start}-{pages[i - 1]}")
            start = pages[i]

    # Add the final range
    if start == pages[-1]:
        ranges.append(f"{start}")
    else:
        ranges.append(f"{start}-{pages[-1]}")

    return f"📄 {file_name} (p. {', '.join(ranges)})"

def treat_raw_query(query):
    # === Treat user query === #
    print(f"\n📍  Raw query: {query}")

    query_tokens = [token.text for token in nlp(query)]
    print(f"    📖  Query tokens: {query_tokens}")

    imp_tokens = extract_simple_tokens(query) # Extract meaningful keywords
    imp_tokens_dict = {}
    for token in imp_tokens:
        # Correct potential misspellings in the student query 
        imp_tokens_dict.update({token: correct_spelling(token)})

    updated_query_tokens = []
    for token in query_tokens:
        if imp_tokens_dict.get(token):
            updated_query_tokens.append(imp_tokens_dict.get(token))
        else: 
            updated_query_tokens.append(token)
    print(f"    ✅  Corrected Tokens After Spell Check: {updated_query_tokens}")
 
    corrected_query = " ".join(updated_query_tokens)
    print(f"📍  Treated query: {corrected_query}")
    
    return corrected_query

def treat_pdf_name(pdf_name):
    # remove 'EDITED_' or 'BOOK_' from the beginning of the pdf name
    pdf_name = re.sub(r'^(EDITED_|BOOK_)?', '', pdf_name)
    return pdf_name
    

# === SPELL CORRECTION === #

def correct_spelling(word, set=VALID_SIMPLE_WORDS):
    """Corrects spelling by finding the closest valid match."""
    closest_match = get_close_matches(word, set, n=1, cutoff=0.8)  # 80% similarity threshold
    if closest_match:
        print(f"    - 🐟  best match for '{word}': {closest_match[0]}")
    return closest_match[0] if closest_match else word  # Return the match or original word

# Function to fetch student progress for a teacher’s classes
def get_progress(teacher_email, class_code, class_number, class_group):

    teacher_classes = fetch_teacher_classes(teacher_email)
    if not teacher_classes:
        print(f"\n❌  No classes found for teacher.")
        return
    df_classes = pd.DataFrame(teacher_classes, columns=["id", "code", "number", "group", "course"])

    classes_ids = []
    if class_code and class_number and class_group:
        # get all classes ids by the code, number and group
        print(f"\n 🏷️  Class group: {class_group}")
        classes_ids = df_classes[(df_classes["code"] == class_code) & (df_classes["number"] == class_number) & (df_classes["group"] == class_group)]["id"].tolist()
    elif class_code and class_number:
        # get all classes ids by the code and number
        print(f"\n 🏷️  Class number: {class_number}")
        classes_ids = df_classes[(df_classes["code"] == class_code) & (df_classes["number"] == class_number)]["id"].tolist()
    
    classes_ids = [int(x) for x in classes_ids if pd.notna(x)]
    print(f"\nClasses IDs: {classes_ids}")

    progress = []
    for class_id in classes_ids:
        progress += fetch_class_progress(class_id)

    if progress:
        return pd.DataFrame(progress, columns=["user_id", "class_id", "question", "response", "topic", "pdfs", "timestamp"])
    else:
        print(f"\n❌ No progress data found for class: {class_code}-{class_number}")
        return pd.DataFrame()
        # To show some data so the dashboard is not empty, we fetch all the progress from all the users:
        #progress = fetch_progress()
        #return pd.DataFrame(progress, columns=["user_id", "class_id", "question", "response", "topic", "pdfs", "timestamp"])
    
def dense_vector_search(keywords, query, split_keywords, collection, authorized_resources, intent="definition of "):

    if keywords != []:
        if not split_keywords:
            query = intent + " ".join(keywords)  # Add a prefix to the query

    # === DENSE (Vector) SEARCH === #
    print(f"\n🔛  Getting query embeddings for query: '{query}'\n...")
    
    query_embedding = model.encode(query, convert_to_numpy=True).tolist()
    vector_results = collection.query(query_embeddings=[query_embedding], n_results=20, where={
        "file": {
            "$in": authorized_resources  # O Chroma só procura nestes ficheiros
        }
    })

    vector_docs = vector_results["documents"][0]
    vector_metadata = vector_results["metadatas"][0]
    vector_scores = vector_results["distances"][0]  # Lower is better (L2 distance)
    
    #print(f"\n📖  1. Found {len(vector_docs)} documents with vector search.")
    #for doc, meta, score in zip(vector_docs, vector_metadata, vector_scores):
    #    print(f"📄  PDF: {meta['file'][:25]} | Page: {meta['page']} | Score: {score:.4f}")
    
    # === NORMALIZE SCORES === #
    
    normalized_vector_scores = normalize_score(vector_scores, True)
    
    print(f"\n📖  2. Vector scores Normalized:")
    for doc, meta, score in zip(vector_docs, vector_metadata, normalized_vector_scores):
        print(f"📄  PDF: {meta['file'][:45]} | Page: {meta['page']} | Score: {score:.4f}")
    
    return vector_docs, vector_metadata, normalized_vector_scores


def hybrid_bm25_search(complex_tokens, simple_tokens, authorized_resources, alpha=0.8):
    # === Perform Hybrid BM25 search === #
    print(f"\n🔛 Getting BM25 sparse vectors for both:\n - {complex_tokens}\n - {simple_tokens}")
    
    # check length of complex_tokens and perform != .get_scores
    if complex_tokens == []:
        bm25_scores_complex = bm25_2gram.get_scores(complex_tokens)
        if bm25_scores_complex.max() == 0:
            print("👻  --> Complex Tokens is []")
    else:
        for i, token in enumerate(complex_tokens):
            if len(token.split()) == 3:
                bm25_scores_complex_3 = bm25_3gram.get_scores([token])
                bm25_scores_complex_3 = normalize_bm25_indexes(bm25_scores_complex_3)
                
                if bm25_scores_complex_3.max() == 0:
                    print(f"👻  --> No matching for 3 Complex Tokens '{[token]}'")
                else:
                    print(f"--> Complex Tokens match with len == 3: {[token]}") 
                
                complex_tokens_2 = get_ngrams(token, 2)
                bm25_scores_complex_2 = bm25_2gram.get_scores(complex_tokens_2)
                bm25_scores_complex_2 = normalize_bm25_indexes(bm25_scores_complex_2)  
                
                if bm25_scores_complex_2.max() == 0:
                    print(f"👻  --> Also, no matching for 2 Complex Tokens '{complex_tokens_2}'")
                else:
                    print(f"--> Also, Complex Tokens match with len == 2: {complex_tokens_2}")

                # combine both scores
                if i == 0:
                    bm25_scores_complex = bm25_scores_complex_3 + bm25_scores_complex_2
                else:
                    bm25_scores_complex += bm25_scores_complex_3 + bm25_scores_complex_2  
                
            else: #len(complex_tokens[0]) == 2:  
                bm25_scores_complex_2 = bm25_2gram.get_scores([token])
                bm25_scores_complex_2 = normalize_bm25_indexes(bm25_scores_complex_2)               
                if i == 0:                     
                    bm25_scores_complex = bm25_scores_complex_2
                else:
                    bm25_scores_complex +=  bm25_scores_complex_2
                
                if len(token.split()) == 2:
                    if bm25_scores_complex.max() == 0:
                        print(f"👻  --> No match for Complex Tokens w/len == 2: '{[token]}'")
                    else:
                        print(f"--> Complex Tokens match with len == 2: {[token]}")

    # Perform BM25 Search
    bm25_scores_simple = bm25_simple.get_scores(simple_tokens)
    
    
    # Filter scores to only have words from authorized resources (files)
    filtered_bm25_scores_simple = []
    filtered_bm25_scores_complex = []

    for i, score in enumerate(bm25_scores_simple):
        # Verificar se o ficheiro deste chunk está na lista de visíveis
        file_name = bm25_metadata[i]['file']
        
        if file_name in authorized_resources:
            #print(f"    ✅  File '{file_name}' is authorized. Keeping this BM25 score.")
            filtered_bm25_scores_simple.append({
                "score": score,
                "text": bm25_documents[i],
                "metadata": bm25_metadata[i]
            })
            
    for i, score in enumerate(bm25_scores_complex):
        # Verificar se o ficheiro deste chunk está na lista de visíveis
        file_name = bm25_metadata[i]['file']
        
        if file_name in authorized_resources:
            filtered_bm25_scores_complex.append({
                "score": score,
                "text": bm25_documents[i],
                "metadata": bm25_metadata[i]
            })

    # 5. Ordenar pelos melhores scores e pegar nos top N
    filtered_bm25_scores_simple = sorted(filtered_bm25_scores_simple, key=lambda x: x['score'], reverse=True)
    
    # Normalize BM25 Scores
    bm25_scores_complex = normalize_bm25_indexes(bm25_scores_complex)
    bm25_scores_simple = normalize_bm25_indexes(bm25_scores_simple)
        
    # change alpha if bm_25_scores_complex is zero
    if bm25_scores_complex.max() == 0:
        print("👻  --> Final, no matching for Complex Tokens")
        alpha = 0  # Weight for simple matches
    #print(f"alpha: {alpha}")
        
    # Step 5: Combine Scores (Weighting Complex Matches Higher)
    final_scores = alpha * bm25_scores_complex + (1 - alpha) * bm25_scores_simple  # Give priority to complex matches    
    top_bm25_indices = np.argsort(final_scores)[::-1][:20]  # Top 20 results  
    
    # remove results with zero scores
    top_bm25_indices = [i for i in top_bm25_indices if final_scores[i] > 0]  

    bm25_docs = [bm25_documents[i] for i in top_bm25_indices]
    bm25_meta = [bm25_metadata[i] for i in top_bm25_indices]
    bm25_scores = [final_scores[i] for i in top_bm25_indices]
    
    #print(f"\n📖  1. Found {len(bm25_docs)} documents with bm25 search.")
    #for doc, meta, score in zip(bm25_docs, bm25_meta, bm25_scores):
    #    print(f"📄  PDF: {meta['file'][:25]} | Page: {meta['page']} | Score: {score:.4f}")            
        
        
    # === NORMALIZE SCORES === #
    
    if bm25_scores:            
        normalized_bm25_scores = normalize_score(bm25_scores, False)
        print(f"\n📖  BM25 scores Normalized:")
        for doc, meta, score in zip(bm25_docs, bm25_meta, normalized_bm25_scores):
            print(f"📄  PDF: {meta['file'][:45]} | Page: {meta['page']} | Score: {score:.4f}")
            
        return bm25_docs, bm25_meta, normalized_bm25_scores
    else:
        print("⚠️  Warning: max_bm25_score is zero. There are no contents about that subject.")
        return bm25_docs, bm25_meta, []
        
def get_ngrams(text, n=2):
    tokens = text.split()
    return [' '.join(ngram) for ngram in ngrams(tokens, n)]
        
def hybrid_search(vector_docs, vector_metadata, normalized_vector_scores, bm25_docs, bm25_meta, normalized_bm25_scores, alpha=0.6):
    # === MERGE & RE-RANK RESULTS === #
    hybrid_results = []

    for doc, meta, score in zip(vector_docs, vector_metadata, normalized_vector_scores):
        hybrid_score = alpha * score        
        hybrid_results.append((doc, meta, hybrid_score))

    for doc, meta, score in zip(bm25_docs, bm25_meta, normalized_bm25_scores):
        hybrid_score = (1 - alpha) * score 
        hybrid_results.append((doc, meta, hybrid_score))
        
    # if some hybrid_results have the same meta['file'] and meta['page'], sum the scores
    hybrid_results_dict = {}
    for doc, meta, score in hybrid_results:
        key = (meta['file'], meta['page'])
        if key in hybrid_results_dict:
            hybrid_results_dict[key][2] += score
        else:
            hybrid_results_dict[key] = [doc, meta, score]
    # convert back to list
    hybrid_results = [(doc, meta, score) for (_, _), (doc, meta, score) in hybrid_results_dict.items()]

    # Sort results by hybrid score
    hybrid_results = sorted(hybrid_results, key=lambda x: x[2], reverse=True)
    #print("\n📊  All Merged Results:")
    #for i, (doc, meta, score) in enumerate(hybrid_results):
    #    print(f"{i+1}. 📄  PDF: {meta['file'][:45]} | Page: {meta['page']} | Score: {score:.4f}")

    # === ADAPTIVE THRESHOLDING BASED ON PERCENTILE === #
    scores = [score for _, _, score in hybrid_results]
    max_score = max(scores) if scores else 1
    
    print(f"\n==== THRESHOLDING ====")        
    adaptive_threshold = np.mean(scores) + 0.5 * np.std(scores)
    percentile_70 = np.percentile(scores, 70)
    max_score_threshold = 0.7 * max_score  # Set a threshold of 70% of the maximum score
    #print(f"📊  Adaptive Threshold: {adaptive_threshold:.3f}")
    #print(f"📊  Percentile_70: {percentile_70:.3f}")
    #print(f"📊  Max Score Threshold: {max_score_threshold:.3f}")
    
    threshold = adaptive_threshold #min(adaptive_threshold, percentile_70, max_score_threshold)
    print(f">>  📊  Final Threshold: {threshold:.3f}")   
    
    # Filter results
    selected_results = [(doc, meta, score) for doc, meta, score in hybrid_results if score >= threshold]
    print(f"\n📖  Found {len(selected_results)} relevant documents in a total of {len(hybrid_results)}:")
    for doc, meta, score in selected_results:
        print(f"    📄  PDF: {meta['file']} | Page: {meta['page']}") #| Score: {score:.4f}
    
    return selected_results
    
    
def get_query_topic(query, response):
    print(f"\n\n 🌞  --------- Getting Query Topic --------- 🌞 ")
            
    topic = None
    prompt = f"Given the student query: '{query}', and the response below, what is the most relevant *canonical* topic keyword for the question? \n{response} \nReply only with the topic keyword."
    try:
        response = g_model.generate_content(prompt)

        if hasattr(response, "text") and response.text:
            topic = response.text
            print(f"\n🎯  Gemini Topic Generated Successfully!\nTopic: {topic}")

            # clean the '\n' at the end of the topic
            topic = topic.replace("\n", "").strip()
            
            # Normalize the topic
            topic = get_normalized_topic(topic)
            
        else:
            print("\n  ⚠️ Gemini Response is empty.")
    except Exception as e:
        print(f"\n❌  Error calling Gemini API.: {e}")
    
    return topic

def get_normalized_topic(topic):
    
    if topic != "":
        # get available topics from the database
        available_topics = fetch_topics()
        available_topics_df = pd.DataFrame(available_topics, columns=["id", "topic"])
        available_topics = available_topics_df["topic"].tolist()  
        topic = [normalize_topic(topic, available_topics)][0]
        print(f"    Available topics: {available_topics}") 
        for i, t in enumerate(available_topics):
            print(f"    - Topic {i+1}: {t}")     
        print(f"    Normalized topic: {topic}")
    else:
        print(f"    ⚠️  No topic found.")
        
    return topic

def get_materials_location(selected_results, complex_tokens, simple_tokens):
    location_results = []
    document_entries = []  # Store documents before sorting
    pdfs_insights = []
    bm25_results = []
    
    bm25_docs, bm25_meta, normalized_bm25_scores = hybrid_bm25_search(complex_tokens, simple_tokens, [], 1.0)  # Get BM25 results with alpha=1.0 for complex keyword search only
    for doc, meta, score in zip(bm25_docs, bm25_meta, normalized_bm25_scores):
        bm25_results.append((doc, meta, score))
    
    # Sort results by hybrid score
    bm25_results = sorted(bm25_results, key=lambda x: x[2], reverse=True)
    print("\n📊  bm25_results Results:")
    for i, (doc, meta, score) in enumerate(bm25_results):
        print(f"{i+1}. 📄  PDF: {meta['file'][:45]} | Page: {meta['page']} | Score: {score:.4f}")
    
    # get the bm25_results which file name and pages are also in the selected_results
    selected_results = [(doc, meta, score) for doc, meta, score in selected_results if (meta['file'], meta['page']) in [(meta['file'], meta['page']) for _, meta, _ in bm25_results]]

    print(f"\n📖  Found {len(selected_results)} relevant documents in a total of {len(bm25_results)}:") 
    for doc, meta, score in selected_results:
        print(f"    📄  PDF: {meta['file'][:45]} | Page: {meta['page'][:15]} | Score: {score:.4f}")
        
        file_name = treat_pdf_name(meta["file"])
        page_number = meta["page"]
        pdfs_insights.append(file_name)
        document_entries.append((file_name, page_number))
    
            
    pdfs_insights = list(set(pdfs_insights))
    
    # **Sort by PDF name (A-Z) and then by page number (ascending)**
    document_entries.sort(key=lambda x: (x[0].lower(), x[1]))  
    location_results = group_pages_by_pdf(document_entries) # Format results
    
    return location_results, pdfs_insights  # Return both the formatted results and the list of PDFs

def print_results(results):
    print("\n📌  FINAL SORTED RESULTS:")
    for result in results:
        print(result)
        
def update_materials_location(selected_results):
    location_results = [] 
    document_entries = []  # Store documents before sorting
    pdfs_insights = [] # Store unique PDF names
    
    for document_text, meta, _ in selected_results:
        file_name = treat_pdf_name(meta["file"])
        page_number = meta["page"]
        document_entries.append((file_name, page_number))
        
    # return the first 1 pdf found
    document_entries = document_entries[:1]
    for file_name, page_number in document_entries:
        pdfs_insights.append(file_name)
    pdfs_insights = list(set(pdfs_insights))
    location_results = group_pages_by_pdf(document_entries) # Format results
    
    print_results(location_results)
    
    return location_results, pdfs_insights  # Return both the formatted results and the list of PDFs
    