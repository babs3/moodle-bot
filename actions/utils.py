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
import urllib.parse
from collections import defaultdict
from nltk import ngrams

# Set up Google Gemini API Key
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

#print("Available Gemini Models:")
#for m in genai.list_models():
#    print(m.name)

# Criamos uma variável de cache para não bater na API sem necessidade
_CACHED_MODEL_NAME = None

def get_latest_gemini_pro_model():
    global _CACHED_MODEL_NAME
    
    # Se já descobrimos o modelo antes, usamos o valor em cache
    if _CACHED_MODEL_NAME:
        return _CACHED_MODEL_NAME

    pattern = re.compile(r"^models/gemini-(\d+(?:\.\d+)*)-flash$")
    available_models = []

    try:
        for m in genai.list_models():
            name = getattr(m, "name", m)
            if isinstance(name, bytes):
                name = name.decode()
            
            match = pattern.match(name)
            if match:
                # Guardamos o nome e a versão (convertida em tuplo de inteiros para ordenar corretamente)
                # Ex: "2.5" -> (2, 5)
                version_str = match.group(1)
                version_tuple = tuple(map(int, version_str.split('.')))
                available_models.append((version_tuple, name))
    except Exception as e:
        print(f"⚠️ Erro ao listar modelos: {e}. Usando fallback seguro.")
        return "models/gemini-2.5-flash" # Fallback caso a API dê 429 logo no início

    if not available_models:
        raise RuntimeError("No 'models/gemini-*-flash' model found")

    # Ordena pelo tuplo da versão (da maior para a menor) e pega o nome do mais recente
    available_models.sort(key=lambda x: x[0], reverse=True)
    
    _CACHED_MODEL_NAME = available_models[0][1]
    return _CACHED_MODEL_NAME

# Uso no teu código:
MODEL_NAME = get_latest_gemini_pro_model() #"models/gemini-2.5-flash"
print(f"✅  Using latest model found: {MODEL_NAME}")

# Load Spacy model for NLP tasks
nlp = spacy.load("en_core_web_sm")

# Load sentence transformer model
model_path = "/app/models/all-MiniLM-L6-v2"
embedding_model = SentenceTransformer(model_path)

# Set irrelevant intent words to filter out from complex and simple tokens
irrelevant_intent_words = ["example", "definition", "significance", "explanation", "meaning", "info", "information", "details", "description", "overview", "summary", "clarification", "insight", "comparison"]


def load_bm25_index(course_id):
    pkl_path = os.path.join("vector_store", f"bm25_index_{course_id}.pkl")
    if os.path.exists(pkl_path):
        with open(pkl_path, "rb") as f:
            return pickle.load(f)
    else:
        return [], [], [], [], []
    
# 3. Processar o marcador <chart> no teu Python:
def encode_chart_match(match):
    json_str = match.group(1).strip()
    # Faz o URL encoding perfeito de TODA a string JSON
    encoded_json = urllib.parse.quote(json_str)
    
    # Retorna o HTML perfeitamente montado e seguro
    return f'<br><br><a href="https://quickchart.io/chart?c={encoded_json}" target="_blank"><img src="https://quickchart.io/chart?c={encoded_json}" width="100%"></a>'

def tokenize_and_clean_text(text):
    # REMOVIDO: text.replace('-', ' ') -> Mantemos os hifens!
    doc = nlp(text)
    
    tokens = []
    tokens_text = [t.text for t in doc]
    
    for i, token in enumerate(doc):
        #print(f"\nToken: '{token.text}', POS: {token.pos_}, Lemma: '{token.lemma_}', Is_Stop: {token.is_stop}")
        # Verifica se o token atual está colado a um hifen
        is_hyphenated = (
            token.text == "-" or 
            (i > 0 and tokens_text[i-1] == "-") or 
            (i < len(doc) - 1 and tokens_text[i+1] == "-")
        )
        
        # Filtro: aceita se for alfabético OU se for o próprio hifen
        if token.is_alpha or token.text == "-":
            # Se for stopword, só ignoramos se NÃO fizer parte de um termo com hifen
            if token.is_stop and not is_hyphenated:
                continue
                
            # Define a formatação (Acrónimo vs Lemma)
            if token.text.isupper():
                valor_token = token.text  # Mantém acrónimos em maiúsculas
            elif token.lemma_.lower() == "datum":
                valor_token = 'data'  # Corrige "datum" para "data"
            elif token.lemma_.lower() == "learning":
                valor_token = 'learn'
            else:
                valor_token = token.lemma_.lower()
            tokens.append(valor_token)
    
    text = " ".join(tokens)
    cleaned_text = text.replace(" - ", "-")
    cleaned_tokens = cleaned_text.split()
            
    # Remove duplicados mantendo a ordem
    tokens = list(dict.fromkeys(cleaned_tokens))
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

def save_user_progress(course_id, user_email, user_message, bot_response, pdfs, input_time_str, user_id, is_tutor_interaction):

    print(f"\n📍  Saving user progress for email: {user_email}, ID: {user_id}")
    
    # Calculating response time
    input_time_cleaned = input_time_str.split("input_time: ")[-1].strip()
    input_time = datetime.fromisoformat(input_time_cleaned).astimezone(timezone.utc)
    now_utc = datetime.now(timezone.utc)
    response_timestamp = (now_utc - input_time).total_seconds()
    print(f" 🕓  Response time: {response_timestamp}")

    # Saving
    data = {
        "course_id": course_id,
        "user_id": user_id,  # Use Moodle user ID
        "question": user_message,
        "response": bot_response,
        "pdfs": pdfs,
        "is_tutor_interaction": is_tutor_interaction,
        "time_to_respond": response_timestamp
    }
    
    requests.post("http://flask-server:8080/api/save_student_moodle_messages", json=data)
    

QUESTION_WORDS = {"what", "who", "where", "when", "why", "how", "compare", "differentiate", "list", "give", "show", "are there", "could you", "explain", "define", "meaning of", "examples of", "definition of", "what is", "what are", "can you", "do you know", "tell me about", "describe", "summarize", "elaborate on", "details about", "information on", "clarify", "expand on", "insights on", "break down", "illustrate with examples", "provide examples of", "what do you know about", "how does", "why is", "what's the difference between", "what's the meaning of", "what's an example of", "can you explain", "can you define", "can you give me examples of", "could you explain", "could you define", "could you give me examples of"}

def clean_key_phrase(phrase):
    """Basic cleaner to normalize noun phrases."""
    phrase = phrase.lower().strip()
    
    if phrase.startswith("the "):
        phrase = phrase[4:]
        
    words = phrase.split()
    words = [w for w in words if w not in QUESTION_WORDS]
    phrase = " ".join(words)
    
    return phrase

def upgrade_to_3grams(treated_query, complex_tokens, simple_tokens):
    new_complex = []
    used_tokens = set()

    # 1. Tentar fundir bigrams sobrepostos
    # Ex: 'learning analysis' + 'analysis algorithm' -> 'learning analysis algorithm'
    for i, token_a in enumerate(complex_tokens):
        words_a = token_a.split()
        
        # Só tentamos fundir se for um bigram (2 palavras)
        if len(words_a) == 2:
            for j, token_b in enumerate(complex_tokens):
                if i == j:
                    continue
                words_b = token_b.split()
                
                if len(words_b) == 2:
                    # Se a última palavra de A for igual à primeira de B
                    if words_a[-1] == words_b[0]:
                        merged_ngram = f"{words_a[0]} {words_a[1]} {words_b[1]}"
                        if merged_ngram not in new_complex:
                            new_complex.append(merged_ngram)
                        used_tokens.add(token_a)
                        used_tokens.add(token_b)

    # 2. Adicionar os complex_tokens que NÃO foram fundidos em trigrams
    for token in complex_tokens:
        if token not in used_tokens and token not in new_complex:
            new_complex.append(token)

    # 3. Fallback: Se não fundiu nada por sobreposição, corre a lógica original de 3-grams seguidos
    if not any(len(t.split()) == 3 for t in new_complex):
        query_words = treated_query.split()
        query_3grams = []
        for i in range(len(query_words) - 2):
            ngram = f"{query_words[i]} {query_words[i+1]} {query_words[i+2]}"
            query_3grams.append(ngram)
        
        for ngram in query_3grams:
            ngram_words = ngram.split()
            if all(word in simple_tokens for word in ngram_words):
                if ngram not in new_complex:
                    new_complex.append(ngram)

    # Se gerámos novos trigrams, filtramos bigrams redundantes que ficaram lá dentro
    # Ex: Se temos 'learning analysis algorithm', já não precisamos de 'learning analysis'
    final_complex = []
    for token in new_complex:
        # Verifica se este token já está contido noutro token maior da lista
        if any(token != other and token in other for other in new_complex):
            continue
        final_complex.append(token)

    return final_complex if final_complex else complex_tokens, simple_tokens

def extract_context_after(query, context):
    #print(f"\n🔍  Extracting noun after concept '{context}' in query: '{query}'")
    before_context = ""
    if " " in context:
        before_context = context.split()[0] + " "  # Pega a primeira palavra do contexto para retornar no texto
        context = context.split()[-1]  # Pega a última palavra do contexto para procurar no texto
        print(f"🔹  Adjusted context for search: '{context}', before_context: '{before_context}'")
        
    doc = nlp(query)

    # Extract cleaned multi-word noun phrases
    new_context = []
    check_noun = False
    for token in doc:
        #print(f"Token: '{token.text}', POS: {token.pos_}, Lemma: '{token.lemma_}', Is_Stop: {token.is_stop}")
        if check_noun:
            if token.pos_ in {"NOUN", "PROPN"} and not token.is_stop:
                if token.lemma_.lower() == "datum":
                    new_context.append('data')
                elif token.lemma_.lower() == "learning":
                    new_context.append('learn')
                else:
                    new_context.append(token.lemma_.lower())
                
        if token.text.lower() == context.lower():
            #print(f"Found context '{context}' in query. Looking for nouns after this token...")
            check_noun = True
    return before_context + context + ' ' + " ".join(new_context) if new_context else before_context + context

def extract_noun_after(query, concept):
    #print(f"\n🔍  Extracting noun after concept '{concept}' in query: '{query}'")
    before_concept = ""
    if " " in concept:
        before_concept = concept.split()[0] + " "  # Pega a primeira palavra do conceito para procurar no texto
        concept = concept.split()[-1]  # Pega a última palavra do conceito para procurar no texto
        print(f"🔹  Adjusted concept for search: '{concept}', before_concept: '{before_concept}'")
        
    doc = nlp(query)

    # Extract cleaned multi-word noun phrases
    check_noun = False
    for token in doc:
        #print(f"Token: '{token.text}', POS: {token.pos_}, Lemma: '{token.lemma_}', Is_Stop: {token.is_stop}")
        if check_noun:
            if token.pos_ in {"NOUN", "PROPN"} and not token.is_stop:
                if token.lemma_.lower() == "datum":
                    return before_concept + concept + ' data'
                elif token.lemma_.lower() == "learning":
                    return before_concept + concept + ' learn'
                else:
                    return before_concept + concept + ' ' + token.lemma_.lower()
                
        if token.text.lower() == concept.lower():
            #print(f"Found concept '{concept}' in query. Looking for nouns after this token...")
            check_noun = True
    return ""

def extract_noun_before(query, concept):
    #print(f"\n🔍  Extracting noun before concept '{concept}' in query: '{query}'")
    after_concept = ""
    if " " in concept:
        after_concept = " " + concept.split()[-1]  # Pega a última palavra do conceito para procurar no texto
        concept = concept.split()[0]  # Pega a primeira palavra do conceito para procurar no texto
        print(f"🔹  Adjusted concept for search: '{concept}', after_concept: '{after_concept}'")
    
    doc = nlp(query)

    last_noun = None

    for token in doc:
        # Se encontrarmos o conceito, verificamos se já tínhamos guardado um substantivo antes
        if token.text.lower() == concept.lower():
            if last_noun is not None:
                return last_noun + ' ' + concept + after_concept
            return ""  # Encontrou o conceito, mas não havia substantivo antes

        # Vai guardando/atualizando o último substantivo válido encontrado
        if token.pos_ in {"NOUN", "PROPN"} and not token.is_stop:
            if token.lemma_.lower() == "datum":
                last_noun = "data"
            elif token.lemma_.lower() == "learning":
                last_noun = "learn"
            else:
                last_noun = token.lemma_.lower()
        else:
            # Opcional: Se houver palavras irrelevantes (que não stop-words) entre o nome 
            # e o conceito, podes querer "fazer reset" ao last_noun.
            # Se queres que o nome esteja COLADO ao conceito, descomenta a linha abaixo:
            # last_noun = None
            pass

    return ""

def extract_query_keywords(query):
    """
    Extracts the most meaningful keyword or phrase from a user query.
    Returns a list of keywords, prioritizing multi-word noun phrases.
    """
    doc = nlp(query)

    acronyms = [token.text for token in doc if token.is_upper and len(token.text) > 1]
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
        return acronyms + multi_word_phrases
        #return list(dict.fromkeys(multi_word_phrases))  # Remove duplicates while preserving order

    # Fallback: extract individual nouns/proper nouns not part of previous phrases
    single_words = []
    for token in doc:
        if token.pos_ in {"NOUN", "PROPN"} and not token.is_stop:
            if token.text:
                if token.text.isupper():  # Keep acronyms as they are
                    single_words.append(token.text)
                else:
                    single_words.append(token.text.lower())
        elif not token.is_stop:
            if token.text and token.text.isupper():  # Keep standalone acronyms
                single_words.append(token.text)

    return single_words


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

def group_pages_by_pdf(document_entries, content_mappings):
    """
    Groups consecutive pages for the same PDF into a range format.
    Example:
        Input: [("file1.pdf", 1), ("file1.pdf", 2), ("file1.pdf", 3), ("file2.pdf", 10), ("file2.pdf", 12)]
        Output: ["file1.pdf (Pages 1-3)", "file2.pdf (Pages 10, 12)"]
    """
    grouped_results = []
    current_file = None
    current_pages = []
    print(f"🔍  Content Mappings: {content_mappings}")

    for file_name, pages in document_entries:
        # substitute file_nem with display name using content_mappings
        print(f"\n🔹  Original file name: '{file_name}'")
        file_name = content_mappings.get(file_name, file_name)
        print(f"🔹  Mapped file name: '{file_name}'")
        pages_list = pages.split("-")
        # Convert to integers and sort
        pages_list = [int(page) for page in pages_list if page.isdigit()]
        if file_name != current_file:  
            # If switching to a new PDF, store the previous result
            if current_file:
                grouped_results.append(format_page_range(current_file, current_pages))
            # Reset tracking for new PDF
            current_file = file_name
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
    if current_file:
        grouped_results.append(format_page_range(current_file, current_pages))
        
    return grouped_results

def format_page_range(file_name, pages):
    """
    Converts a list of page numbers into a formatted string.
    Example:
        Input: "file1.pdf", [1, 2, 3, 5, 6, 8]
        Output: "📄 file1.pdf (Pages 1-3, 5-6, 8)"
    """
    
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
        
    # se o file começar com "Video Lecture" não mostrar páginas
    if file_name.startswith("Video Lecture"):
        return f"🎥  {file_name}"
    else:
        return f"📄  {file_name} (p. {', '.join(ranges)})"


def treat_pdf_name(pdf_name):
    # remove 'EDITED_' or 'BOOK_' from the beginning of the pdf name
    pdf_name = re.sub(r'^(EDITED_|BOOK_)?', '', pdf_name)
    return pdf_name
    

# Function to fetch student progress for a teacher’s classes
def get_user_history(course_id):
    response = requests.get(f"http://flask-server:8080/api/get_user_history/{course_id}")
    if response.status_code == 200:
        progress_data = response.json()
        #print(f"📊  User progress data retrieved: {progress_data}")
        return pd.DataFrame(progress_data)
    else:
        print("⚠️  Failed to retrieve user progress data.")
        return pd.DataFrame()    
    
def get_llm_classroom_analysis(course_id):
    response = requests.get(f"http://flask-server:8080/api/get_llm_classroom_analysis/{course_id}")
    if response.status_code == 200:
        analysis_data = response.json()
        print(f"📊  LLM classroom analysis retrieved: {analysis_data}")
        return analysis_data
    else:
        print("⚠️  Failed to retrieve LLM classroom analysis.")
        return {}
    
def get_quiz_history(course_id):
    response = requests.get(f"http://flask-server:8080/api/get_quiz_history/{course_id}")
    if response.status_code == 200:
        quiz_data = response.json()
        print(f"📊  Quiz history data retrieved: {quiz_data}")
        return pd.DataFrame(quiz_data)
    else:
        print("⚠️  Failed to retrieve quiz history data.")
        return {}


def formatar_historico_para_llm(quiz_history):
    quiz_history_list = json.loads(quiz_history)
    # Agrupa os dados por quiz
    dados_por_quiz = defaultdict(lambda: {"notas": [], "timestamps": [], "reprovas": 0, "total": 0})
    
    for h in quiz_history_list:
        q_id = h.quiz_id
        dados_por_quiz[q_id]["notas"].append(h.percentage)
        dados_por_quiz[q_id]["timestamps"].append(h.timestamp)
        dados_por_quiz[q_id]["total"] += 1
        if h.percentage < 50.0:  # Critério de nota negativa
            dados_por_quiz[q_id]["reprovas"] += 1

    # Ordena os quizes cronologicamente com base na média das datas em que foram feitos
    quizes_ordenados = sorted(
        dados_por_quiz.items(), 
        key=lambda x: min(x[1]["timestamps"]) if x[1]["timestamps"] else 0
    )

    # Cria a estrutura final que o LLM vai ler
    historico_temporal = []
    for q_id, info in quizes_ordenados:
        media_quiz = sum(info["notas"]) / len(info["notas"]) if info["notas"] else 0
        historico_temporal.append({
            "quiz_id": q_id,
            "class_average_percentage": round(media_quiz, 1),
            "total_students_completed": info["total"],
            "students_failed_count": info["reprovas"]
        })
        
    return historico_temporal

def filtrar_e_expandir_tokens(complex_tokens):
    lista_final = []
    
    for token in complex_tokens:
        palavras = token.split()
        num_palavras = len(palavras)
        
        # Se tiver 4 ou mais palavras, decompõe em sub-expressões de 3 e 2 palavras
        if num_palavras >= 4:
            # 1. Adiciona todas as combinações de 3 palavras (tri-grams)
            for i in range(num_palavras - 2):
                lista_final.append(" ".join(palavras[i:i+3]))
                
            # 2. Adiciona todas as combinações de 2 palavras (bi-grams)
            for i in range(num_palavras - 1):
                lista_final.append(" ".join(palavras[i:i+2]))
        elif num_palavras == 3:
            # Se tiver exatamente 3 palavras, adiciona a expressão original e os bi-grams
            lista_final.append(token)  # Mantém o token original
            for i in range(num_palavras - 1):
                lista_final.append(" ".join(palavras[i:i+2]))
        else:
            # Se já tiver 2  palavras (ou menos), mantém o token original
            lista_final.append(token)
    
    print(f"\n🔍  ComplexTokens after filtering and expansion: {lista_final}")
    
    lista_final_cleaned = []        

    for expression in lista_final:
        doc = nlp(expression)
        nova_expressao = ""
        
        # Criamos uma lista com o texto original dos tokens para espreitar os vizinhos
        tokens_text = [token.text for token in doc]
        
        for i, token in enumerate(doc):
            # --- NOVA LÓGICA PARA HIFENS ---
            # Verifica se o token atual é um hifen, ou se está colado a um hifen (antes ou depois)
            is_hyphenated = (
                token.text == "-" or 
                (i > 0 and tokens_text[i-1] == "-") or 
                (i < len(doc) - 1 and tokens_text[i+1] == "-")
            )
            
            if token.text.isupper():  # Mantém acrônimos como estão
                nova_expressao += token.text + " "
                
            elif token.is_stop and not is_hyphenated:  # SÓ ignora stopword se NÃO tiver hifen
                print(f"🔹  Ignoring stopword: '{token.text}' in token: '{expression}'")
                continue
                
            else:
                nova_expressao += token.text.lower() + " "
                
        # --- LIMPEZA DE ESPAÇOS NOS HIFENS ---
        # O spaCy adiciona espaços ao reconstruir (ex: "end - to - end")
        # Este replace volta a colar o "end-to-end" corretamente
        expressao_formatada = nova_expressao.strip().replace(" - ", "-")
        
        if expressao_formatada:  
            if len(expressao_formatada.split()) > 1 or "-" in expressao_formatada:  # Mantém se for multi-palavra OU tiver hifen
                if expressao_formatada not in lista_final_cleaned:  
                    lista_final_cleaned.append(expressao_formatada)
            
    print(f"\n🔍  ComplexTokens after case normalization: {lista_final_cleaned}")
    
    return lista_final_cleaned

def dense_vector_search(intent, complex_tokens, simple_tokens, context, query, collection, authorized_resources):
    complex_2grams = [token for token in complex_tokens if len(token.split()) == 2]
    complex_3grams = [token for token in complex_tokens if len(token.split()) == 3]
    
    if complex_tokens != []:
        if complex_3grams != []:
            query = intent + " " + " ".join(complex_3grams)
        elif complex_2grams != []:
            query = intent + " " + " ".join(complex_tokens) 
        
            # se existir acronimos nos simple tokens, adiciona-os ao início da query, seguido dos complex tokens
            #acronimos = [token for token in simple_tokens if token.isupper()]
            # se complex_token acabar com 'and', adicionar o acronimo depois
            #if complex_tokens and complex_tokens[-1].endswith('and'):
            #    query = intent + " " + " ".join(complex_tokens) + " " #+ " ".join(acronimos)
            #else: 
            #    query = intent + " " + " ".join(complex_tokens) #  + " ".join(acronimos) + " "
            #query = re.sub(r'\s+', ' ', query).strip()  # Remove extra spaces
    else:          
        query = intent + " " + " ".join(simple_tokens)
        
    if context and context.strip() != "":
        query += " in " + context  # Add context to the query if it exists

    # 1. Buscar todos os metadados da coleção
    # (Pedimos apenas os metadados para não sobrecarregar a memória com textos gigantes)
    all_data = collection.get(include=["metadatas"])

    # 2. Extrair e listar os nomes únicos dos ficheiros guardados
    if all_data and "metadatas" in all_data:
        # Mapeia o campo "file" de cada chunk na coleção
        files_in_chroma = set(
            meta.get("file") for meta in all_data["metadatas"] if meta and "file" in meta
        )
        print("\n--- 📁  FICHEIROS ATUALMENTE NO CHROMADB ---")
        for f in files_in_chroma:
            print(f"- {f}")
        print(f"Total de ficheiros únicos: {len(files_in_chroma)}\n")
    else:
        print("A coleção está completamente vazia ou não tem metadados.")
    
    
    # === DENSE (Vector) SEARCH === #
    print(f"\n🔛  Getting query embeddings for query: '{query}'\n...")

    query_embedding = embedding_model.encode(query, convert_to_numpy=True).tolist()

    # Modificação do Filtro WHERE para garantir que só procura nos filhos e nos ficheiros certos
    search_filter = {
        "$and": [
            {"file": {"$in": authorized_resources}},
            {"doc_type": "child"} # Ignora os pais na busca densa para não poluir os scores
        ]
    }

    vector_results = collection.query(
        query_embeddings=[query_embedding], 
        n_results=20, 
        where=search_filter
    )  

    vector_docs = vector_results["documents"][0]
    vector_metadata = vector_results["metadatas"][0]
    vector_scores = vector_results["distances"][0] 

    # === RETORNAR O PAI E REMOVER DUPLICADOS === #
    unique_docs = []
    seen_combinations = set()

    for child_doc, meta, score in zip(vector_docs, vector_metadata, vector_scores):
        file_page_combo = (meta['file'], meta['page'])
        
        if file_page_combo not in seen_combinations:
            # TRUQUE AQUI: Substituímos o texto do filho pelo texto do Pai!
            parent_text = meta["parent_text"]
            
            # Limpar o metadado para não enviar o texto do pai duplicado para a frente
            clean_meta = meta.copy()
            del clean_meta["parent_text"] 
            
            unique_docs.append((parent_text, clean_meta, score))
            seen_combinations.add(file_page_combo)

    vector_docs, vector_metadata, vector_scores = zip(*unique_docs) if unique_docs else ([], [], [])

    # === NORMALIZE SCORES === #
    normalized_vector_scores = normalize_score(vector_scores, True)
    
    print(f"\n📖  1. Found {len(vector_docs)} unique parent documents via child vector search.")
    for doc, meta, score in zip(vector_docs, vector_metadata, normalized_vector_scores):
        print(f"📄  PDF: {meta['file'][:25]} | Page: {meta['page']} | Score: {score:.4f}")

    return vector_docs, vector_metadata, normalized_vector_scores


def hybrid_bm25_search(complex_tokens, simple_tokens, authorized_resources, course_id, alpha=0.8):
    # === Perform Hybrid BM25 search === #
    
    if complex_tokens != []:
        complex_tokens = filtrar_e_expandir_tokens(complex_tokens)
    print(f"\n🔛  Getting BM25 sparse vectors for both:\n - {complex_tokens}\n - {simple_tokens}\n")
    
    # grant access to the BM25 index updated with new documents (if any)
    try:
        bm25_simple, bm25_2gram, bm25_3gram, bm25_metadata, bm25_documents = load_bm25_index(course_id)
        if bm25_simple == []:
            print("👻  --> BM25 index is empty. No documents available for search.")
            return [], [], []
    except FileNotFoundError:
        print("👻  --> User does not have access to any documents in the authorized resources.")
        return [], [], []


    # check length of complex_tokens and perform != .get_scores
    if complex_tokens == []:
        bm25_scores_complex = bm25_2gram.get_scores(complex_tokens)
        if bm25_scores_complex.max() == 0:
            print("👻  --> Complex Tokens is []")
    else:
        for i, token in enumerate(complex_tokens):
            if len(token.split()) == 3:
                bm25_scores_complex_3 = bm25_3gram.get_scores([token])
                
                if bm25_scores_complex_3.max() != 0:
                    print(f"--> Complex Tokens match with len == 3: {[token]}") 
                    # print from what pages the 2-grams are matching
                    for idx, score in enumerate(bm25_scores_complex_3):
                        if score > 0:
                            meta = bm25_metadata[idx]
                            print(f"    - 3-gram '{token}' matches with pages:")
                            for idx, score in enumerate(bm25_scores_complex_3):
                                if score > 0:
                                    meta = bm25_metadata[idx]
                                    print(f"        📄  {meta['file'][:30]} | Page: {meta['page']} | Score: {score:.4f}")
                                                
                
                # combine both scores
                if i == 0:
                    bm25_scores_complex = bm25_scores_complex_3
                else:
                    bm25_scores_complex += bm25_scores_complex_3 
                
            else: #len(complex_tokens[0]) == 2:  
                bm25_scores_complex_2 = bm25_2gram.get_scores([token])
                
                if len(token.split()) == 2:
                    if bm25_scores_complex_2.max() != 0:
                        print(f"--> Complex Tokens match with len == 2: {[token]}")
                        # print from what pages the 2-grams are matching
                        for idx, score in enumerate(bm25_scores_complex_2):
                            if score > 0:
                                meta = bm25_metadata[idx]
                                print(f"    - 2-gram '{token}' matches with pages:")
                                for idx, score in enumerate(bm25_scores_complex_2):
                                    if score > 0:
                                        meta = bm25_metadata[idx]
                                        print(f"        📄  {meta['file'][:30]} | Page: {meta['page']} | Score: {score:.4f}")
                if i == 0:                     
                    bm25_scores_complex = bm25_scores_complex_2
                else:
                    bm25_scores_complex +=  bm25_scores_complex_2
                
    fallback_tokens = []
    valid_tokens = []
    # Perform BM25 Search por token
    for token in simple_tokens:
        bm25_scores_simple_token = bm25_simple.get_scores([token])
        
        if bm25_scores_simple_token.max() != 0:
            # Conta quantos chunks têm score > 0 para este token
            match_count = sum(1 for score in bm25_scores_simple_token if score > 0)
            
            if match_count > 10:
                print(f"⚠️ Token '{token}' é muito abrangente ({match_count} matches). Guardado como garantia.")
                # Guardamos nas garantias (fallback)
                fallback_tokens.append(token)
            else:
                print(f"--> Simple Token '{token}' matches with pages ({match_count} matches):")
                # Guardamos nos tokens válidos
                valid_tokens.append(token)
                
                # O teu print original (apenas para os válidos)
                #for idx, score in enumerate(bm25_scores_simple_token):
                #    if score > 0:
                #        meta = bm25_metadata[idx]
                #        print(f"        📄  {meta['file'][:30]} | Page: {meta['page']} | Score: {score:.4f}")
    
    if valid_tokens:
        print(f"\n🔍  Valid Simple Tokens for BM25 search: {valid_tokens}")
        bm25_scores_simple = bm25_simple.get_scores(valid_tokens)
    elif fallback_tokens:
        print("⚠️  No valid simple tokens found. Using fallback tokens for BM25 search.")
        bm25_scores_simple = bm25_simple.get_scores(fallback_tokens)
    else:
        print("⚠️  No valid or fallback simple tokens found. BM25 search will return no results.")
        bm25_scores_simple = np.zeros(len(bm25_metadata))  # No matches
    
    # =========================================================================
    # MODIFICAÇÃO PARENT-CHILD ADAPTADA AO TEU AGREGADOR HÍBRIDO (SIMPLE + COMPLEX)
    # =========================================================================
    # Em vez de agregar pela chave `doc_text` (que era o texto do Filho), 
    # vamos agregar pelo identificador único do Pai `(file, page)`.
    combined_parents = {}

    # 1. Processar os scores simples (vindos dos sub-chunks Filhos)
    for i, score in enumerate(bm25_scores_simple):
        meta = bm25_metadata[i]
        if meta['file'] in authorized_resources:
            file_page_combo = (meta['file'], meta['page'])
            parent_text = meta["parent_text"] # Recuperamos o Pai real aqui!
            
            if file_page_combo not in combined_parents:
                combined_parents[file_page_combo] = {
                    "text": parent_text,
                    "metadata": meta,
                    "score_simple": score,
                    "score_complex": 0.0
                }
            else:
                # Max Pooling: Se outra parte da mesma página pontuar melhor, mantém o maior score
                if score > combined_parents[file_page_combo]["score_simple"]:
                    combined_parents[file_page_combo]["score_simple"] = score

    # 2. Processar os scores complexos (vindos dos sub-chunks Filhos)
    for i, score in enumerate(bm25_scores_complex):
        meta = bm25_metadata[i]
        if meta['file'] in authorized_resources:
            file_page_combo = (meta['file'], meta['page'])
            parent_text = meta["parent_text"]
            
            if file_page_combo in combined_parents:
                if score > combined_parents[file_page_combo]["score_complex"]:
                    combined_parents[file_page_combo]["score_complex"] = score
            else:
                combined_parents[file_page_combo] = {
                    "text": parent_text,
                    "metadata": meta,
                    "score_simple": 0.0,
                    "score_complex": score
                }

    # Inicializar variáveis de retorno para o caso de falha precoce
    bm25_docs = []
    bm25_meta = []
    bm25_scores = []

    # Se não sobrou nenhum documento autorizado, parar cedo
    if not combined_parents:
        print("⚠️ No authorized documents found after filtering.")
    else:
        # Converter para lista plana para fazer os cálculos vetoriais em NumPy
        parents_list = list(combined_parents.values())
        
        raw_scores_simple = np.array([x["score_simple"] for x in parents_list])
        raw_scores_complex = np.array([x["score_complex"] for x in parents_list])
        
        # 3. Normalizar
        norm_scores_simple = np.array(normalize_score(raw_scores_simple, False))
        norm_scores_complex = np.array(normalize_score(raw_scores_complex, False))

        if norm_scores_complex.max() == 0:
            print("👻  --> Final, no matching for Complex Tokens")
            alpha = 0
            
        # 4. Combinar scores usando a tua ponderação alfa original
        final_scores = alpha * norm_scores_complex + (1 - alpha) * norm_scores_simple
        
        # 5. Ordenar de forma decrescente
        sorted_indices = np.argsort(final_scores)[::-1]
        
        for idx in sorted_indices:
            # Critério de corte: score zero ou quando atingir o limite de 20 pais únicos
            if final_scores[idx] <= 0 or len(bm25_docs) >= 20:
                break
                
            meta_copy = parents_list[idx]["metadata"].copy()
            
            # Limpeza crucial: remove o payload gigante de metadados para não sobrecarregar as camadas seguintes
            if "parent_text" in meta_copy:
                del meta_copy["parent_text"]
                
            bm25_docs.append(parents_list[idx]["text"]) # Guardamos o texto do PAI completo!
            bm25_meta.append(meta_copy)
            bm25_scores.append(final_scores[idx])
        
    # Retorno e prints organizados
    if bm25_scores:            
        print(f"\n📖  BM25 scores Normalized (Parent-Child Aligned):")
        for doc, meta, score in zip(bm25_docs, bm25_meta, bm25_scores):
            print(f"📄  PDF: {meta['file'][:45]} | Page: {meta['page']} | Score: {score:.4f}")
            
        return bm25_docs, bm25_meta, bm25_scores
    else:
        print("⚠️  Warning: max_bm25_score is zero. There are no contents about that subject.")
        return bm25_docs, bm25_meta, []
    
        
def get_ngrams(text, n=2):
    tokens = text.split()
    return [' '.join(ngram) for ngram in ngrams(tokens, n)]
        

def calculate_engine_threshold(scores, strictness_factor=1.0):
    """
    Calcula o threshold adaptativo.
    strictness_factor < 1.0 -> Threshold mais baixo (mais permissivo, mais resultados)
    strictness_factor > 1.0 -> Threshold mais alto (mais rigoroso, menos resultados)
    """
    if not scores:
        return 0
        
    max_score = max(scores)
    adaptive_threshold = np.mean(scores) + 0.5 * np.std(scores)
    percentile_70 = np.percentile(scores, 70)
    max_score_threshold = 0.8 * max_score
    
    # Calculamos o threshold base original
    base_threshold = min(adaptive_threshold, percentile_70, max_score_threshold)
    
    # Aplicamos o fator para subir ou descer a fasquia
    final_threshold = base_threshold * strictness_factor
    
    # Garantia para o threshold não ultrapassar o score máximo possível por erro matemático
    return min(final_threshold, max_score)

def hybrid_search(vector_docs, vector_metadata, normalized_vector_scores, bm25_docs, bm25_meta, normalized_bm25_scores, alpha=0.6):
    
    # === AJUSTE DINÂMICO DOS THRESHOLDS BASEADO NO ALPHA ===
    # Exemplo com alpha = 0.85:
    # vector_strictness = 1.5 - 0.85 = 0.65 (Threshold do vetor DESCE -> mais resultados)
    # bm25_strictness   = 0.5 + 0.85 = 1.35 (Threshold do BM25 SOBE -> menos resultados)
    vector_strictness = 1.5 - alpha  
    bm25_strictness = 0.5 + alpha    

    # Calcular os thresholds com os respetivos pesos de exigência
    vector_threshold = calculate_engine_threshold(normalized_vector_scores, strictness_factor=vector_strictness)
    bm25_threshold = calculate_engine_threshold(normalized_bm25_scores, strictness_factor=bm25_strictness)
    print(f"\n📊  Calculated Thresholds:\n - Vector Threshold: {vector_threshold:.4f} (Strictness: {vector_strictness:.2f})\n - BM25 Threshold: {bm25_threshold:.4f} (Strictness: {bm25_strictness:.2f})")
    
    # Criar conjuntos (sets) para controlo de quem veio de onde e quem passou nos thresholds
    vector_passed = set()
    bm25_passed = set()
    all_vector_keys = set()
    all_bm25_keys = set()
    
    # Analisar resultados do Vetor
    for meta, score in zip(vector_metadata, normalized_vector_scores):
        key = (meta['file'], meta['page'])
        all_vector_keys.add(key)
        if score >= vector_threshold:
            vector_passed.add(key)
            
    # Analisar resultados do BM25
    for meta, score in zip(bm25_meta, normalized_bm25_scores):
        key = (meta['file'], meta['page'])
        all_bm25_keys.add(key)
        if score >= bm25_threshold:
            bm25_passed.add(key)
            
    # 2. Aplicar a tua regra de seleção lógica (União das 3 condições)
    # Condição 1: Interseção pura (Aparece em ambos os motores, independentemente do score)
    intersection_keys = all_vector_keys.intersection(all_bm25_keys)
    
    # Combinar todas as chaves autorizadas
    authorized_keys = intersection_keys.union(vector_passed).union(bm25_passed)
    
    # === MERGE & RE-RANK RESULTS ===
    hybrid_results = []

    # Adicionar scores do vetor (pesados por alpha)
    for doc, meta, score in zip(vector_docs, vector_metadata, normalized_vector_scores):
        hybrid_score = alpha * score        
        hybrid_results.append((doc, meta, hybrid_score))

    # Adicionar scores do BM25 (pesados por 1 - alpha)
    for doc, meta, score in zip(bm25_docs, bm25_meta, normalized_bm25_scores):
        hybrid_score = (1 - alpha) * score 
        hybrid_results.append((doc, meta, hybrid_score))
        
    # Agrupar e somar os scores híbridos
    hybrid_results_dict = {}
    for doc, meta, score in hybrid_results:
        key = (meta['file'], meta['page'])
        if key in hybrid_results_dict:
            hybrid_results_dict[key][2] += score
        else:
            hybrid_results_dict[key] = [doc, meta, score]
            
    # Converter de volta para lista
    hybrid_results = [(doc, meta, score) for (_, _), (doc, meta, score) in hybrid_results_dict.items()]

    # Ordenar os resultados finais pelo score híbrido combinado
    hybrid_results = sorted(hybrid_results, key=lambda x: x[2], reverse=True)
    
    # === FILTRAGEM FINAL ===
    # Só entram os documentos cujas chaves foram pré-aprovadas pelas tuas 3 regras
    selected_results = []
    print(f"\n==== 📊  HYBRID SELECTION LOG ==== ")
    print(f">> Vector Threshold: {vector_threshold:.3f} | BM25 Threshold: {bm25_threshold:.3f}")
    
    for doc, meta, score in hybrid_results:
        key = (meta['file'], meta['page'])
        
        if key in authorized_keys:
            selected_results.append((doc, meta, score))
            
            # Print explicativo do porquê deste documento ter sido salvo
            reasons = []
            if key in intersection_keys: reasons.append("Encontrado em Ambos")
            if key in vector_passed: reasons.append("Passou Threshold Vetor")
            if key in bm25_passed: reasons.append("Passou Threshold BM25")
            
            print(f"✅  Selecionado: PDF: {meta['file'][:25]} | Pág: {meta['page']} | Score Híbrido: {score:.4f} | Motivo: {', '.join(reasons)}")
        else:
            print(f"❌  Eliminado:   PDF: {meta['file'][:25]} | Pág: {meta['page']} | Score Híbrido: {score:.4f}")
            
    #print(f"\n📖  Found {len(selected_results)} relevant documents in a total of {len(hybrid_results)}:")
    #for doc, meta, score in selected_results:
    #    print(f"    📄  PDF: {meta['file']} | Page: {meta['page']}") #| Score: {score:.4f}
    
    # access text to replace '__OCR__' withspecific NOTE
    for i, (doc, meta, score) in enumerate(selected_results):
        if '__OCR__' in doc:
            selected_results[i] = (doc.replace('__OCR__', "[NOTE: This text was extracted via OCR from an image/scan and may contain minor spelling errors]"), meta, score)
    
    # print for see the OCR notes in the selected results
    print(f"\n📖  Selected Results after thresholding (with OCR notes if applicable):")
    updated_results = []
    
    for doc, meta, score in selected_results:
        #print(f"    📄  PDF: {meta['file'][:45]} | Page: {meta['page']} | OCR: {meta['is_ocr']} | DOC text: {doc[:50]}...")
        if meta.get('is_ocr') == True:
            #print(f"    ⚠️  Document is OCR. Adding note about potential errors in the text.")
            note = "[NOTE: This text was extracted via OCR from an image/scan and may contain minor spelling errors]\n"
            doc = note + doc
            
        updated_results.append((doc, meta, score))
        
    for doc, meta, score in updated_results:
        print(f"    📄  PDF: {meta['file'][:45]} | Page: {meta['page']} | OCR: {meta.get('is_ocr', False)} | DOC text: \n{doc[:200]}...")
    

    return updated_results
    
    
def generate_topic(question, correct_answer, course_fullname="Ciber-physical Systems and Internet of Things"):
    print(f"\n\n 🌞  --------- Generating Question Topic --------- 🌞 ")
            
    topic = None
    prompt = f"Given the following question and correspondent expected answer of one of the evaluations in the course of {course_fullname}, what is the most relevant *canonical* topic keyword for the question? \nQuestion: {question}\nExpected Answer: {correct_answer}\nTopic: ? \n\nReply only with the topic keyword."
    try:
        g_model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            #system_instruction=system_instruction TODO: ver se é preciso
        )
        response = g_model.generate_content(prompt)

        if hasattr(response, "text") and response.text:
            topic = response.text
            print(f"\n🎯  Gemini Topic Generated Successfully!\nTopic: {topic}")

            # clean the '\n' at the end of the topic
            topic = topic.replace("\n", "").strip()
            
            # Normalize the topic
            topic = normalize_topic(topic)
        else:
            print("\n  ⚠️ Gemini Response is empty.")
    
    except Exception as e:
        print(f"\n❌  Error calling Gemini API.: {e}")
    
    return topic

def normalize_topic(new_topic, threshold=0.85):
    # get available topics from the database
    response = requests.get("http://flask-server:8080/api/get_topics")
    if response.status_code == 200:
        # Só aqui é que convertes para JSON
        available_topics = response.json() 
        #print(f"DEBUG COMPLETO RASA: {json.dumps(available_topics, indent=2)}") # Vê a estrutura real aqui  
        
    else:
        print(f"Erro no servidor: {response.status_code}")
        available_topics = [] # Fallback
    
    #print(f"\n🔍  Available topics: {available_topics}")        
    if not available_topics:
        # save the first topic if there are no topics in the database
        requests.post("http://flask-server:8080/api/save_topic", json={"topic_name": new_topic})
        return new_topic
    
    available_topics_names = [t['name'] for t in available_topics]
    
    new_vec = embedding_model.encode(new_topic, convert_to_tensor=True)
    known_vecs = embedding_model.encode(available_topics_names, convert_to_tensor=True)
    
    for i, t in enumerate(available_topics_names):
        print(f"    - Topic {i+1}: {t}")     

        sims = util.cos_sim(new_vec, known_vecs)[0]
        max_score, best_idx = sims.max(), sims.argmax()

        if max_score >= threshold:
            print(f"\n ⚖️  Normalized topic '{new_topic}' to '{available_topics_names[best_idx]}' with score {max_score:.2f}")
            return available_topics_names[best_idx]  # Use existing normalized topic
    
    print(f"\n ➕  No close match found for topic '{new_topic}'. Saving as new topic.")
    requests.post("http://flask-server:8080/api/save_topic", json={"topic_name": new_topic})
    return new_topic  # Return the new topic if no close match was found


def get_materials_location(selected_results, complex_tokens, simple_tokens, course_id, content_mappings):
    location_results = []
    document_entries = []  # Store documents before sorting
    pdfs_insights = []
    bm25_results = []
    
    bm25_docs, bm25_meta, normalized_bm25_scores = hybrid_bm25_search(complex_tokens, simple_tokens, [], course_id, 1.0)  # Get BM25 results with alpha=1.0 for complex keyword search only
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
    location_results = group_pages_by_pdf(document_entries, content_mappings) # Format results
    
    return location_results, pdfs_insights  # Return both the formatted results and the list of PDFs

def print_results(results):
    print("\n📌  FINAL SORTED RESULTS:")
    for result in results:
        print(result)
        
def update_materials_location(selected_results, content_mappings):
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
    location_results = group_pages_by_pdf(document_entries, content_mappings) # Format results
    
    print_results(location_results)
    
    return location_results, pdfs_insights  # Return both the formatted results and the list of PDFs
    
def create_topics_buttons(user_id, course_id, moodle_url, moodle_token):
    # get user progress
    progress = requests.get(f"http://flask-server:8080/api/get_user_progress", params={"user_id": user_id, "course_id": course_id, "all_questions": False, "moodle_url": moodle_url, "moodle_token": moodle_token})
    if progress.status_code == 200:
        progress_data = progress.json()
        print(f"📊  User progress data retrieved: {progress_data}")
    else:
        print(f"❌  Failed to retrieve user progress. Status code: {progress.status_code}")
        progress_data = []
        
    if progress_data == []:
        print(f"⚠️  all questions were already reviewd")
        progress_data = requests.get(f"http://flask-server:8080/api/get_user_progress", params={"user_id": user_id, "course_id": course_id, "all_questions": True, "moodle_url": moodle_url, "moodle_token": moodle_token})
        return []
    
    # A tua lista de tópicos (pode vir de uma BD, API ou slot)
    topics_ids = []
    for entry in progress_data:
        topic_id = entry.get("topic_id")
        if topic_id and topic_id not in topics_ids:
            topics_ids.append(topic_id)
            
    # get topics from topics_ids
    topics = requests.get(f"http://flask-server:8080/api/get_topics_from_ids", json={"topics_ids": topics_ids})
    if topics.status_code == 200:
        topics_list = topics.json()
    else:
        print(f"❌  Failed to retrieve topics. Status code: {topics.status_code}")
        topics_list = []
    print(f"📚  Topics retrieved for user {user_id}: {topics_list}")

    buttons = []
    for topic in topics_list:
        buttons.append({
            "title": topic.get("name"),
            "payload": topic.get("id")
            #"payload": "/set_topic_id{" + f"'topic_id': '{topic.get('id')}'" + "}"
        })
        
    return buttons