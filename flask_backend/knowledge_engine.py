import time
from dotenv import load_dotenv
import os
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import chromadb
import pickle
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
import re
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from nltk import ngrams
import spacy
import uuid
from collections import Counter
import re
from yt_dlp import YoutubeDL
from faster_whisper import WhisperModel

# Load Spacy model for NLP tasks
nlp = spacy.load("en_core_web_sm")

embedding_model = SentenceTransformer("/app/models/all-MiniLM-L6-v2")

def get_text_embedding(text):
    return embedding_model.encode(text, convert_to_numpy=True)

def is_page_number(text):
    """Checks if the text is a page number."""
    # check if its a digit or its a digit followed by a dot or a parenthesis
    return bool(re.match(r"^\d+[\.\)]?$", text.strip()))

def extract_text_with_ocr(page):
    # Render page to an image (use a zoom factor for better OCR accuracy)
    zoom = 2  # 2x resolution
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)

    # Convert pixmap to PIL image
    image = Image.open(io.BytesIO(pix.tobytes("png")))

    # Perform OCR using pytesseract
    text = pytesseract.image_to_string(image, config='--psm 3') # 3: Fully automatic page segmentation
    
    #print(f"    🖼️  Extracted OCR text (before cleaning):\n{text}")
    # Clean up the text
    text = clean_ocr_and_image_garbage(text)
    #print(f"    🧹  Extracted OCR text (after cleaning):\n{text}")

    return text

def clean_ocr_and_image_garbage(text):
    # 1. Normalizar espaços iniciais e finais
    text = text.strip()
    
    # 2. Padrões conhecidos de erros de imagem e marcas (Abordagem Genérica)
    image_error_patterns = [
        r"the\s+picture\s+can", 
        r"be\s+displayed", 
        r"picture\s+nant",
        r"made\s+with\s+gamma"
    ]
    
    lines = text.splitlines()
    cleaned_lines = []
    
    for line in lines:
        line_stripped = line.strip()
        
        # Ignorar linhas vazias imediatamente
        if not line_stripped:
            continue
            
        # [Aproveitado da tua]: Ignorar se a linha não tiver conteúdo alfanumérico legítimo
        if re.match(r'^[^a-zA-Z0-9]*$', line_stripped): 
            continue
            
        # [Melhoria]: Remover palavras isoladas de logos/erros (linhas muito curtas de texto solto)
        # Se tiver 3 ou menos caracteres (ex: "The", "BCE", "v", "F 7"), salta a linha
        if len(line_stripped) <= 3:
            continue
            
        # [Novo]: Filtrar mensagens de erro de imagens fragmentadas
        if any(re.search(pattern, line_stripped, re.IGNORECASE) for pattern in image_error_patterns):
            continue
            
        # [Novo]: Rácio de caracteres especiais (apanha "DE| DEPARTAMENTO DE" ou tabelas partidas)
        special_chars = len(re.findall(r'[|()\[\]{}#@_*–➔•]', line_stripped))
        if (special_chars / len(line_stripped)) > 0.15: 
            continue
            
        cleaned_lines.append(line_stripped)
        
    # Juntar as linhas válidas para fazer a formatação global
    text = '\n'.join(cleaned_lines)
    
    # 3. [Aproveitado da tua - FORMATAÇÃO GLOBAL]
    # Remove bullet characters residuais que possam ter ficado a meio de frases
    text = re.sub(r'[\u2022\u00a9¢•™®“”‘’\"*v©®→←▪️]+', '', text)
    
    # Remove strings manuais específicas que aches críticas (como tinhas)
    text = re.sub(r'\b(?:ree|Sex|F 7|Pre-t)\b', '', text, flags=re.IGNORECASE)
    
    # [Aproveitado da tua]: Limpeza estética de espaçamento e pontuação
    text = re.sub(r'\s{2,}', ' ', text)                  # Remove espaços múltiplos
    text = re.sub(r'\.\s*', '. ', text)                  # Garante espaço após ponto
    text = re.sub(r'\s+([?.!,])', r'\1', text)           # Remove espaço antes de pontuação
    text = re.sub(r'\n\s*\n+', '\n\n', text)             # Normaliza quebras de linha duplas
    
    return text.strip()
 
def get_ngrams(text, n=2):
    doc = nlp(text)
    #print(f"\n🔍  Doc text for n-grams: {doc}")
    
    # 1. Primeiro geramos os tokens limpos seguindo a mesma regra dos hifens
    tokens_limpos = []
    tokens_text = [t.text for t in doc]
    
    for i, token in enumerate(doc):
                
        is_hyphenated = (
            token.text == "-" or 
            (i > 0 and tokens_text[i-1] == "-") or 
            (i < len(doc) - 1 and tokens_text[i+1] == "-")
        )            
        
        # se nao tiver hifenados, segue a regra normal de limpeza
        if not is_hyphenated:
            # se o token nao for stop ou for um hifen, mantem o token
            if not token.is_stop or token.text != "-":
                # Define a formatação (Acrónimo vs Lemma)
                if token.lemma_.lower() == "datum":
                    valor_token = 'data'  # Corrige "datum" para "data"
                elif token.lemma_.lower() == "learning":
                    valor_token = 'learn'
                else:
                    valor_token = token.lemma_.lower()
                tokens_limpos.append(valor_token)
                continue
        # se tiver hifenados, mantem o token original (sem lematizar) e junta com os tokens vizinhos se forem hifenados
        else:
            if token.text == "-":
                if i > 0 and i < len(doc) - 1:
                    #print(f"⚠️  Token '-' is hyphenated between '{tokens_text[i-1]}' and '{tokens_text[i+1]}'. Keeping them as a single token.")
                    new_token = tokens_text[i-1] + "-" + tokens_text[i+1]
                    tokens_limpos.append(new_token.lower())
                    continue  # Skip the next token since it's already merged        
        
    # 2. Criamos os n-grams a partir dos tokens limpos
    ngrams = []
    for i in range(len(tokens_limpos) - n + 1):
        janela_tokens = tokens_limpos[i:i+n]
        # Juntamos com espaço, mas corrigimos o " - " para "-" para o n-gram ficar bonito
        ngram_texto = " ".join(janela_tokens).replace(" - ", "-")
        ngrams.append(ngram_texto)
        
    return ngrams

LINES_TO_REMOVE = [
    # SCI slides style
    "M.EIC043",
    "M. EICO43",
    "CYBERPHYSICAL SYSTEMS AND INTERNET OF THINGS",
    "2023/2024",
    "2024/2025",
    "The picture can’t",
    "be displayed.",
    "The",
    "picture",
    "can’t be",
    "SISTEMAS CIBERFÍSICOS E INTERNET DAS COISAS",
    "Wm tele Se CYBERPHYSICAL SYSTEMS AND INTERNET OF THINGS 2024/2025",
    "DE| DEPARTAMENTO DE",
    "ENGENHARIA INFORMATICA,",
    "M. EICO43 (OTTO US) AEWA PM NLL al Oa Nes) 2023/2024",
    "The",
    "picture",
    "nant ha",
    "BCE",
    "The picture cai",
    "ENGENHARIA INFORMATICA",
    "DEPARTAMENTO DE",
    "FEUP FACUoADE DF EncenaR",
    "FEUP DEI",
    "FEUP FACUoRDE DF EncenAR ENGENHARIA INFORMATICA.",
    "A alee) CYBERPHYSIC. INTERNET OF THINGS",
    "FEU FACULDADE De ENCENHARIA ENGENHARIA INFORMATICA.",
    "FEUP FACUoRDE DF EncenAR ENGENHARIA INFORMATICA.",
    "FEUP Face cena ENGENHARIA INFORMATICA.",
    "FEUP Facwuoto€ De Enc ENGENHARIA INFORMATICA.",
    "FEUP Facuuoxoeo en",
    "M. EICO43 meee aang",
    "Bporro DE| 2erartaueno 0",
    "FEUP FACUoADE DF EncenaR ENGENHARIA INFORMATICA.",
    "Bporro DE| 2erasraneno oe",
    "FEUP Facwuoto€ De Enc ENGENHARIA INFORMATICA.",
    "porro",
    "Fro acai acne DEI",
    "G Made with Gamma",
    
    # GEE slides style
    "Enterprise Management and", 
    "Entrepreneurship",
    "MIEIC 2023-2024",
    "José Coelho Rodrigues, Manuel Aires de Matos",
    "José Coelho Rodrigues",
    "MIEIC 2022-2023",
    "Operations slides by João Claro and José Coelho Rodrigues",
    "Lia Patrício (2023)",
    "M.EIC 2022-2023",
    "Lia Patrício | Marta Campos Ferreira |",
    
    # LGP slides style
    "UPTEC—SCIENCE AND TECHNOLOGY PARK OF UNIVERSITY OF PORTO",
    "[aPorRTO",
    "ON VtRaDA DE ENGENHARIA",
    "FEUP VERSIDADE DO PORTO",
    "Porto",
    "FACULDADE DE ENGENHARIA",
    "UNIVERSIDADE DO PORTO",
    "FEUP UNIVERSIDADE DO PORTO"
]
    
def clean_using_blacklist(doc_text, blacklist):
    # Criamos uma variável de trabalho que vai acumulando as limpezas
    current_text = doc_text
    removed_lines = []
    
    for line in blacklist:
        # 1. Limpar espaços nas pontas e fazer o escape de caracteres especiais
        flexible_pattern = re.escape(line.strip())
        
        # 2. SEPARAR PONTUAÇÃO: Forçar que após um ponto (\.) ou barra (\/) possa existir um espaço opcional (\s*)
        flexible_pattern = re.sub(r'(\\\.|\\\/)', r'\1\\s*', flexible_pattern)
        
        # 3. ESPAÇOS FLEXÍVEIS: Onde já existiam espaços na blacklist, aceitar qualquer quantidade deles
        flexible_pattern = re.sub(r'\\ ', r'\\s*', flexible_pattern)
        
        # 4. HÍFENS FLEXÍVEIS: Permitir hífens opcionais entre letras
        flexible_pattern = flexible_pattern.replace('-', r'\-?')
        flexible_pattern = re.sub(r'([A-Z])([A-Z])', r'\1\-?\2', flexible_pattern, flags=re.IGNORECASE)
        
        # 5. O MILAGRE DO OCR (Zero vs Ó): Substitui qualquer 0 ou O por um grupo [0O]
        flexible_pattern = re.sub(r'(0|O)', r'[0O]', flexible_pattern, flags=re.IGNORECASE)

        # 6. Executar a substituição NO TEXTO QUE JÁ VEM A SER LIMPO (current_text)
        text_after_sub = re.sub(flexible_pattern + r'\s*', '', current_text, flags=re.IGNORECASE)
        
        # Verificação de log baseada na mudança desta iteração específica
        if current_text != text_after_sub:
            removed_lines.append(line)            
            # Atualizamos a nossa variável de trabalho com o texto limpo
            current_text = text_after_sub
    
    #if removed_lines:
    #    print(f"\n🧹  Removed from blacklist: '{removed_lines}'")
        #print(f"        Before: {doc_text}")
        #print(f"        After: {current_text}")
            
    # SÓ DEVOLVE O TEXTO DEPOIS DE CORRER A BLACKLIST TODA (Fora do loop for)
    return current_text

def extract_text_by_context(pdf_path, is_book=False, edited=False, min_word_threshold=20, sim_threshold=0.65):
    """Extracts text from each page of a PDF, merging short pages and sequential numbered sections."""
    doc = fitz.open(pdf_path)
    page_chunks = []
    total_pages = len(doc)
    title = None
    
    blacklist = create_blacklist(pdf_path)
    print("\nBlacklist de linhas repetidas (headers/footers):")
    for line in blacklist:
        print(f"- {line}")
    
    print(f"\n\n📄  Processing {pdf_path} with {total_pages} pages...\n")

    i = 0
    while i < total_pages:
        collected_texts = []
        page_numbers = []
        write_title = False
        unformatted_title = False
        title_num = ""
        
        while i < total_pages:
            cleaned_image_text = ""
            print(f"📄  - Page {i + 1} of {total_pages}")
            
            current_text = doc[i].get_text("text").strip()
            current_text = clean_using_blacklist(current_text, blacklist)  # Clean the text by lines
            
            # Only use OCR if the page has no normal text 
            if len(current_text.split()) == 0 and i != 0:
                image_text = extract_text_with_ocr(doc[i])
                if image_text.split() != []:
                    current_text = '__OCR__' + clean_using_blacklist(image_text, blacklist)
                    print(f"    🖼️  current_text is OCR text from page {i + 1}")
                else:
                    print(f"    ⚠️  Skipping empty page {i + 1}")
                    i += 1
                    continue
            #else:
            #    print(f"-> current_text is normal text from page {i + 1}:\n{current_text}")            
            
            emb_i = get_text_embedding(current_text)
            word_count = len(current_text.split())
            
            # use again current_text to get the titles
            if unformatted_title: # title as the last line
                unformatted_title = False                
                title = current_text.split("\n")[-2]
                # body is all from the begining until the line before the last of the page
                body = ""
                for line in current_text.split("\n"):
                    if line == title:
                        break
                    body += line + "\n"
                print(f"\n     * Unformatted title: {title}: \n{body}")
            else:
                title = current_text.split("\n")[0]
                #print(f"     *? Title: {title}")
                body = ""
   
                # if title is just a number, skip it
                if is_page_number(title): # if true, title is the second line
                    print(f"     ⚠️  Skipping title: {title}")
                    try:
                        title = current_text.split("\n")[1]
                    except IndexError:
                        print(f"     ⚠️  Skipping empty page {i + 1} (just a page number)")
                        i += 1
                        continue
                    try:
                        body = current_text.split("\n", 2)[2]
                    except IndexError:
                        body = ""
                    #print(f"\n     * Title after digit: {title}: \n{body}")
                    
                else: # title as the first line
                    if cleaned_image_text != "":
                        body = cleaned_image_text
                    else:
                        try:
                            body = ""
                            for line in current_text.split("\n", 1)[1].split("\n"):
                                if is_page_number(line):
                                    # skip if line is a number or the same as the title
                                    continue
                                body += line + "\n"
                        except IndexError: # page is just a title
                            body = "" 
            
            # if title starts with a number, extract the number
            if re.match(r"^\d+\.\s", title):
                # extract the number and remove it from the title
                title_num = re.search(r"^\d+\.\s", title).group(0)
                #print(f"     * Title '{title}' with number: {title_num}")
                # remove the dot from the title_num
                title_num = title_num.replace(".", "")
            
            if not is_book and not edited:
                # append current text to collected_texts but with a new line after first line
                current_text = '__PARABREAK__' + title + '__PARABREAK__' + body
            
            #print(f"\n    {str(i + 1)}. Current Text:\n{current_text}\n")
            collected_texts.append(current_text)
            page_numbers.append(str(i + 1))
                
            i += 1 # Move to the next page

            if not is_book and not edited:
                # check title of next page
                if i < total_pages:
                    next_text = doc[i].get_text("text").strip()
                    next_text = clean_using_blacklist(next_text, blacklist)
                    next_title = next_text.split("\n")[0]
                            
                    # merge with next page if is like the introdutory slide of the next numbered sections
                    if re.match(r"^\d+\.\s", next_title):
                        # extract the number
                        next_title_num = re.search(r"^\d+\.\s", next_title).group(0)
                        if next_title_num == '1. ':
                            print(f"     🦖  Page {i} is an introduction for a sequence of slides w/numbered titles.")
                            continue # merge with next page
                        
                    # sometimes the pdf text is parsed wrongly, so the title my be as the last line of the page
                    # check if the last line of the next page is the same as the title of the current page:
                    try:
                        next_bad_title = next_text.split("\n")[-2] # cause -1 is the page number -> IN GEE
                    except IndexError:
                        #print(f"     ⚠️  Skipping empty page {i + 1} (just a page number)")
                        #i += 1
                        #continue
                        next_bad_title = ""
                    
                    if title == next_title:
                        print(f"     🦖  Pages {i} and {i + 1} have the same title: {title}")
                        # remove the last appended current_text
                        collected_texts.pop()
                        collected_texts.append('__PARABREAK__' + body)
                        write_title = True
                        continue # Merge with next page
                    
                    elif title == next_bad_title:
                        print(f"     🦖🦖  Pages {i} and {i + 1} have the same title: {title}")
                        # remove the last appended current_text
                        collected_texts.pop()
                        collected_texts.append('__PARABREAK__' + body)
                        write_title = True
                        unformatted_title = True
                        continue
                    
                    elif title_num != "":
                        # check if the next title starts with a number
                        if re.match(r"^\d+\.\s", next_title):
                            # extract the number and remove it from the title
                            next_title_num = re.search(r"^\d+\.\s", next_title).group(0)
                            next_title = re.sub(r"^\d+\.\s", "", next_title)
                            #print(f"     * Next title '{next_title}' with number: {next_title_num}")
                            
                            next_title_num = next_title_num.replace(".", "")
                            if int(title_num) + 1 == int(next_title_num):
                                print(f"     #️⃣  Pages {i} and {i + 1} have sequential numbered titles : {title_num} and {next_title_num}")
                                continue # Merge with next page
                    
                    else:
                        if write_title:
                            print(f"     ...🦖  Page {i + 1} has different title: {next_title}")
                            collected_texts.pop()
                            collected_texts.append('__PARABREAK__' + body)
                            break  # Stop if titles are different
 
            if i < total_pages:
                if edited:
                    continue # Merge with next page
                next_text = doc[i].get_text("text").strip()
                next_text = clean_using_blacklist(next_text, blacklist)
                
                emb_j = get_text_embedding(next_text)
                sim = cosine_similarity([emb_i], [emb_j])[0][0]
                #print(f"     * Pages {i} and {i+1} have similarity score: {sim:.2f}")
                if sim >= sim_threshold:
                    print(f"     🟰  Pages {i} and {i+1} have similar content!")   
                    continue  # Merge with next page
                else: # next is not similar
                    if word_count >= min_word_threshold or i == total_pages:
                        break  # Stop if it's a valid content page or end of doc
                    if i == 1:
                        print(f"     ⚠️  First page has too few words: {word_count} | {min_word_threshold}. Continuing with next page...")
                        # If it's the first page, we always merge it with the next page, no search with OCR
                        continue
                    print(f"     ⚠️  Page {i} has too few words: {word_count} | {min_word_threshold} -> verify if it has images...")
                    # try OCR
                    current_image_text = extract_text_with_ocr(doc[i-1])
                    if current_image_text.split() != []:
                        current_image_text = clean_using_blacklist(current_image_text, blacklist)
                        print(f"       🖼️  Page {i} has images!")
                        # Stop if it has sufficient OCR text
                        image_word_count = len(current_image_text.split())
                        if image_word_count >= min_word_threshold:
                            collected_texts.pop()
                            collected_texts.append('__PARABREAK__' + '__OCR__' + current_image_text)
                            break
                        else:
                            print(f"     ⚠️  Page {i} has no suficient content, merging with next...")
                            continue
                    else:
                        print(f"     ⚠️  Page {i} has no suficient content, merging with next...")
                        continue  # Merge with next page
                                   
                  
        is_ocr = False
        if write_title:
            #print(f"🏷️  Pages have common title '{title}':") 
            cleaned_text, is_ocr = clean_text("\n\n".join(collected_texts))
            final_text = title + "\n\n" + cleaned_text
        else:
            if edited:
                #print("=> Edited PDF detected!")
                final_text = clean_edited_text("\n\n".join(collected_texts))
            else:
                final_text, is_ocr = clean_text("\n\n".join(collected_texts))
                
        
        page_label = "-".join(page_numbers) if len(page_numbers) > 1 else page_numbers[0]
        page_chunks.append({"text": final_text, "page": page_label, "is_ocr": is_ocr})
        
        if write_title:
            print(f"\n-----> 🏷️  Text from page(s) {page_label} w/title '{title}':\n{final_text}\n\n")
        else:
            print(f"\n-----> 🏷️  Text from page(s) {page_label}:\n{final_text}\n\n")

    return page_chunks

def process_video_transcription(raw_text, chunk_size=100, chunk_overlap=20):
    """
    Lê a transcrição de um vídeo, limpa-a e divide-a em chunks de texto 
    com sobreposição (overlap) para não perder contexto semântico.
    
    :param txt_path: Caminho para o ficheiro .txt gerado pelo Whisper.
    :param chunk_size: Número aproximado de palavras por chunk.
    :param chunk_overlap: Número de palavras a repetir entre chunks vizinhos.
    :return: Lista de dicionários estruturados prontos para a Vector Store.
    """
    print(f"\n🎬  Processing video transcription...")

    cleaned_text = re.sub(r'\[\d{2}:\d{2}\]', '', raw_text) # Remove [00:00] se existir
    
    # Limpeza básica de espaços e quebras de linha múltiplas
    cleaned_text = " ".join(cleaned_text.split())

    # Tokenização simplificada por palavras (funciona perfeitamente para inglês)
    words = cleaned_text.split()
    total_words = len(words)
    
    video_chunks = []
    chunk_index = 1
    
    # Algoritmo de Janela Deslizante (Sliding Window)
    start_idx = 0
    while start_idx < total_words:
        # Define o fim do bloco atual
        end_idx = min(start_idx + chunk_size, total_words)
        
        # Extrai as palavras e junta-as de volta num bloco de texto
        chunk_words = words[start_idx:end_idx]
        chunk_text = " ".join(chunk_words)
        
        # Validar tamanho mínimo (evitar chunks residuais vazios no fim do ficheiro)
        if len(chunk_words) < 15 and video_chunks:
            # Se for muito pequeno, junta-o ao chunk anterior em vez de criar um novo
            video_chunks[-1]["text"] += " " + chunk_text
            break
            
        # Estrutura o output exatamente igual ao que o teu processamento de PDF já espera
        video_chunks.append({
            "text": chunk_text,
            "page": f"video_chunk_{chunk_index}", # Identificador no lugar da página
            "is_ocr": False,
            #"word_count": len(chunk_words)
        })
        
        print(f"  🔹  Created chunk {chunk_index}: {len(chunk_words)} words.")
        print(f"     Sample text: '{chunk_text}'\n")
        
        # Avança o ponteiro considerando a sobreposição (overlap)
        start_idx += (chunk_size - chunk_overlap)
        chunk_index += 1

    print(f"🎬  Video processing concluded. Total chunks created: {len(video_chunks)}\n")
    return video_chunks

def clean_doc_text(text):
    text = text.replace("\n", " ")
    # remove excessive whitespace
    text = re.sub(r"\s{2,}", " ", text)
    text = text.replace(" - ", " ")
    return text.strip()

def tokenize_and_clean_text(text):
    doc = nlp(text)
    
    tokens = []
    tokens_text = [t.text for t in doc]
    
    for i, token in enumerate(doc):
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
    
    return cleaned_tokens

def initialize_chroma():
    # Agora ligamo-nos ao container 'chroma' via HTTP
    # O host é o nome do serviço no docker-compose
    client = chromadb.HttpClient(host='chroma', port=8000)
    return client

def create_blacklist(pdf, threshold_pct=0.15):
    """
    Identifica automaticamente linhas repetidas que parecem headers/footers.
    pages: Lista de listas de strings (cada sublista é o texto de uma página)
    """
    doc = fitz.open(pdf)
    pages = []
    for page in doc:
        text = page.get_text("text")
        ocr_text = extract_text_with_ocr(page)
        if ocr_text.split() != []:
            #print(f"    🖼️  OCR text for blacklist creation:\n{ocr_text}")
            ocr_text = text + "\n" + ocr_text
        lines = ocr_text.splitlines()
        pages.append(lines)
        
    total_pages = len(pages)
    all_lines = []
    
    for page in pages:
        # Usamos set() por página para contar apenas uma ocorrência por página
        unique_lines_in_page = set([line.strip() for line in page if line.strip()])
        all_lines.extend(unique_lines_in_page)
        
    line_counts = Counter(all_lines)
    
    # Se a linha aparece em mais de X% das páginas, vai para a blacklist
    blacklist = {line for line, count in line_counts.items() if (count / total_pages) > threshold_pct}
    # remove símbolos comuns da blacklist, pois podem aparecer em conteúdos legítimos
    # 1. Filtro que já tinhas para os símbolos especiais
    symbols = ["➔", "►", "¢", "●", "•", "–", "‣", "▪", "◦", "·", "‧", "", "", "Ø", "ü"]
    for sym in symbols:
        blacklist = {line for line in blacklist if sym not in line}

    # 2. FILTRO DE NUMERAÇÕES (O que precisas acrescentar)
    # Este padrão deteta linhas que contêm APENAS números, ou números seguidos de pontos/hífens/parênteses (ex: "1.", "2 -", "(3)")
    numeric_pattern = r"^\(?\d+[\.\-\)\s]*$"

    blacklist = {
        line for line in blacklist 
        if not re.match(numeric_pattern, line.strip())
    }
    # ordenar para que as linhas com mais palavras apareçam primeiro, para uma limpeza mais eficaz
    blacklist = sorted(blacklist, key=lambda x: len(x.split()), reverse=True)
    
    return blacklist
            
def process_pdfs(pdf_folder, youtube_ids, course_id):
    """Processa PDFs de um curso específico e atualiza a base de conhecimento."""
    
    # 1. Definir o caminho da subpasta do curso
    vector_db_path = "/app/vector_store"
    
    chroma_client = initialize_chroma()
    # Mantemos uma única coleção, mas filtraremos por course_id no metadata
    collection = chroma_client.get_or_create_collection(name="class_materials")
    
    documents = []
    metadata = []
    simple_tokens = []
    ngram_docs_2 = []
    ngram_docs_3 = []
    
    # 3. Processar ficheiros na pasta temporária criada pela API
    for file in os.listdir(pdf_folder):
        if file.endswith(".pdf"):
            pdf_path = os.path.join(pdf_folder, file)

            if file.startswith("BOOK_"):
                page_chunks = extract_text_by_context(pdf_path, is_book=True, edited=False, min_word_threshold=50, sim_threshold=0.90)
            elif file.startswith("EDITED_"):
                page_chunks = extract_text_by_context(pdf_path, is_book=False, edited=True)
            else:
                page_chunks = extract_text_by_context(pdf_path)
                
            for chunk in page_chunks:
                # ... dentro do teu loop original ...
                doc_text = chunk["text"]

                parent_metadata = {
                    "file": file, 
                    "page": chunk["page"], 
                    "course_id": str(course_id),
                    "is_ocr": chunk["is_ocr"],
                    "doc_type": "parent"
                }

                words = doc_text.split()
                child_size = 100
                overlap = 20

                # === SALVAGUARDA PARA PAIS PEQUENOS ===
                # Se o Pai for menor ou quase do tamanho do target do Filho, ele próprio vira Filho
                if len(words) <= child_size:
                    documents.append(doc_text)
                    
                    child_meta = parent_metadata.copy()
                    child_meta["doc_type"] = "child"
                    child_meta["parent_text"] = doc_text # O texto do pai é igual ao do filho
                    metadata.append(child_meta)
                    
                    # Processamento para o BM25 (sobre o texto completo)
                    cleaned_text = tokenize_and_clean_text(clean_doc_text(doc_text))
                    simple_tokens.append(cleaned_text)
                    ngram_docs_2.append(get_ngrams(" ".join(cleaned_text), 2))
                    ngram_docs_3.append(get_ngrams(" ".join(cleaned_text), 3))

                else:
                    # Se for grande, corre o teu loop normal de fragmentação (Parent-Child)
                    for i in range(0, len(words), child_size - overlap):
                        child_text = " ".join(words[i:i + child_size])
                        if not child_text.strip():
                            continue
                            
                        documents.append(child_text)
                        
                        child_meta = parent_metadata.copy()
                        child_meta["doc_type"] = "child"
                        child_meta["parent_text"] = doc_text
                        metadata.append(child_meta)
                        
                        cleaned_text = tokenize_and_clean_text(clean_doc_text(child_text))
                        simple_tokens.append(cleaned_text)
                        ngram_docs_2.append(get_ngrams(" ".join(cleaned_text), 2))
                        ngram_docs_3.append(get_ngrams(" ".join(cleaned_text), 3))
                        #print(f"---> simple_tokens: {cleaned_text}\n")
                        print(f"3-gram tokens: {get_ngrams(' '.join(cleaned_text), 3)}\n")
                
    if not youtube_ids:
        print("-> Nenhum vídeo do YouTube para processar.")
    else: 
        print(f"-> Processando {len(youtube_ids)} vídeos do YouTube...")
        for video_id, video_name in youtube_ids:
            print(f"-> Novo vídeo detetado [{video_id}]. A iniciar extração de áudio...")
            
            audio_output_mp3 = os.path.join(pdf_folder, f"{video_id}.mp3")
            
            # Configuração do yt-dlp para extrair apenas áudio leve
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(pdf_folder, f"{video_id}.%(ext)s"),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '96',
                }],
                'quiet': True
            }
            
            try:
                # Download do áudio do YT
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
                    
                if os.path.exists(audio_output_mp3):
                    print(f"-> A transcrever áudio do vídeo {video_id} com Whisper local (CPU)...")
                    model = WhisperModel("base", device="cpu", compute_type="int8", download_root=pdf_folder)
                    segments, info = model.transcribe(audio_output_mp3, language="en", beam_size=5)
                    
                    # Juntar os segmentos em texto corrido
                    full_text = "\n".join([segment.text for segment in segments])
                    video_chunks = process_video_transcription(full_text)
                                        
                    inc = 1
                    child_size = 100
                    overlap = 20

                    for chunk in video_chunks:
                        doc_text = chunk["text"]
                        
                        # 1. Definir o metadado base que identifica o Pai
                        # Nota: Mantemos o campo "page" mapeado para o teu incremento (inc) para não quebrar a lógica de UI
                        parent_metadata = {
                            "file": video_id, 
                            "page": str(inc), 
                            "course_id": str(course_id),
                            "is_ocr": False,
                            "doc_type": "parent"  # Identificador crucial!
                        }
                        
                        words = doc_text.split()
                        
                        # === SALVAGUARDA PARA CHUNKS DE VÍDEO CURTOS ===
                        # Se o texto do vídeo for pequeno, ele próprio vira o Filho (cópia exata)
                        if len(words) <= child_size:
                            documents.append(doc_text)
                            
                            child_meta = parent_metadata.copy()
                            child_meta["doc_type"] = "child"
                            child_meta["parent_text"] = doc_text  # O texto do pai é igual ao do filho
                            metadata.append(child_meta)
                            
                            # Processamento para o BM25 sobre o bloco de vídeo
                            cleaned_text = tokenize_and_clean_text(clean_doc_text(doc_text))
                            simple_tokens.append(cleaned_text)
                            ngram_docs_2.append(get_ngrams(" ".join(cleaned_text), 2))
                            ngram_docs_3.append(get_ngrams(" ".join(cleaned_text), 3))
                            
                        else:
                            # === DIVISÃO PARENT-CHILD SE FOR GRANDE ===
                            for i in range(0, len(words), child_size - overlap):
                                child_text = " ".join(words[i:i + child_size])
                                if not child_text.strip():
                                    continue
                                    
                                documents.append(child_text)
                                
                                # O metadado do filho herda o contexto do vídeo e armazena o texto do Pai
                                child_meta = parent_metadata.copy()
                                child_meta["doc_type"] = "child"
                                child_meta["parent_text"] = doc_text
                                metadata.append(child_meta)
                                
                                # Processamento BM25 focado na granularidade do Filho
                                cleaned_text = tokenize_and_clean_text(clean_doc_text(child_text))
                                simple_tokens.append(cleaned_text)
                                ngram_docs_2.append(get_ngrams(" ".join(cleaned_text), 2))
                                ngram_docs_3.append(get_ngrams(" ".join(cleaned_text), 3))
                                
                        # O incremento original continua a avançar por bloco "Pai" processado
                        inc += 1
                
            except Exception as e:
                print(f"Erro ao processar o vídeo {video_id}: {e}")
                continue
        
    if not documents:
        return False

    # 4. Gerar Embeddings Densos
    embeddings = embedding_model.encode(documents, convert_to_numpy=True)
        
    # 5. Guardar no ChromaDB
    ids = [str(uuid.uuid4()) for _ in range(len(documents))]
    
    collection.add(
        ids=ids,
        embeddings=embeddings.tolist(),
        metadatas=metadata,
        documents=documents
    )
    
    # 6. Guardar Index BM25
    bm25_simple = BM25Okapi(simple_tokens)
    bm25_2gram = BM25Okapi(ngram_docs_2)
    bm25_3gram = BM25Okapi(ngram_docs_3)
    
    with open(os.path.join(vector_db_path, f"bm25_index_{course_id}.pkl"), "wb") as f:
        pickle.dump((bm25_simple, bm25_2gram, bm25_3gram, metadata, documents), f)
    
    return True

# To reduce embeddings noise
def clean_text(text):
    # remove the first '__PARABREAK__' if it exists
    if text.startswith('__PARABREAK__'):
        text = text[13:]  # remove the first 15 characters
    
    is_ocr = False
    # se contem '__OCR__' em qualquer sitio do texto, remove it and add a note that the text is from OCR
    if '__OCR__' in text:
        text = text.replace('__OCR__', '')  # remove the marker
        is_ocr = True
        
    # removes extra newlines/spaces
    #text = ' '.join(text.split())
    text = text.replace('__PARABREAK__', '\n')
    
    # replace ('?', ':') with the same character + '\n'
    #text = re.sub(r'([?:])', r'\1\n', text)
    
    # Step 1: Add a newline before each number (only if not already at line start)
    #text = re.sub(r'(?<!\n)(\b\d+\.\s)', r'\n\1', text)
    
    # Step 1: Replace 'ü' with a newline and bullet ●
    # Only add newline if 'ü' is not at the beginning of a line
    #text = re.sub(r'(?<!\n)ü\s*', r'\n● ', text)  # mid-line ü → newline + bullet
    #text = re.sub(r'(?<=\n)ü\s*', r'● ', text)     # line-start ü → just bullet
    
    
    # Step 2: Join lines that are wrapped (mid-paragraph or mid-bullet)
    # We'll do this by:
    #   - Keeping paragraph breaks
    #   - Joining lines that are not separated by a double newline
    paragraphs = text.split('\n\n')
    joined_paragraphs = []
    for para in paragraphs:
        # Join lines inside a paragraph with a space
        joined = ' '.join(line.strip() for line in para.splitlines())
        joined_paragraphs.append(joined)

    # Rejoin paragraphs with double line breaks
    final_text = '\n\n'.join(joined_paragraphs)
    
    # Step 3: Clean up bullet points
    # Replace bullet points with a newline and a dash
    final_text = re.sub(r"\s*[➔►¢●•–‣▪◦·‧Øü]\s*", r"\n- ", final_text)
    final_text = re.sub(r"\s*[○]\s*", r"\n    - ", final_text)
    # relace numbered lists with a newline and a dash
    final_text = re.sub(r"\s*(\d+\.\s)", r"\n\1", final_text)  # forces numbered items to a new line
    
    # Remove hyphens between letters (e.g., "num- ber" -> "number")
    text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)
    # Normalize multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Final cleanup of whitespace and over-newlines
    final_text = re.sub(r'\n{3,}', '\n\n', final_text).strip()
    
    return final_text, is_ocr

def clean_edited_text(text):
    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Step 1: Preserve paragraph breaks by replacing double newlines with a placeholder
    text = re.sub(r'\n\s*\n', '__PARABREAK__', text)

    # Step 2: Remove single newlines (line breaks within paragraphs)
    text = re.sub(r'\n+', ' ', text)

    # Step 3: Restore paragraph breaks
    text = text.replace('__PARABREAK__', '\n\n')
    
    # substitute '●' or '•' with '\n●' or '\n•'
    text = re.sub(r'([●•])', r'\n-', text)

    # Step 4: Optionally strip trailing spaces
    return text.strip()

def delete_pdf_from_knowledge(filename, course_id):
    vector_db_path = os.path.join("/app/vector_store/", f"course_{course_id}")
    """Remove um PDF específico do ChromaDB e reconstrói o índice BM25."""
    
    # Ligar ao ChromaDB (Client-Server)
    chroma_client = initialize_chroma()
    collection = chroma_client.get_or_create_collection(name="class_materials")
    
    # 1. Primeiro, perguntamos ao Chroma quais são os IDs que batem com os metadados
    # Nota: Garante que o tipo de dado (str vs int) é o mesmo usado no process_pdfs
    results = collection.get(
        where={
            "$and": [
                {"file": filename},
                {"course_id": str(course_id)} 
            ]
        }
    )
    
    # 2. Se encontrarmos IDs, apagamos por ID (que é o método mais rápido e infalível)
    if results['ids']:
        collection.delete(ids=results['ids'])
        print(f"🗑️  Removidos {len(results['ids'])} chunks do ficheiro: {filename}")
    else:
        print(f"⚠️  Nenhum registo encontrado para {filename} no curso {course_id}")
        return False

    # 3. Atualizar o BM25 (O BM25 não permite 'delete', temos de reconstruir)
    pkl_path = os.path.join(vector_db_path, "bm25_index.pkl")
    
    if os.path.exists(pkl_path):
        with open(pkl_path, "rb") as f:
            _, _, _, metadata, documents = pickle.load(f)
        
        # Filtrar os metadados e documentos para manter apenas o que NÃO é o ficheiro a apagar
        indices_para_manter = [
            i for i, meta in enumerate(metadata) 
            if not (meta['file'] == filename and meta['course_id'] == str(course_id))
        ]
        
        if not indices_para_manter:
            # Se não sobrar nada, apagamos o ficheiro pkl
            os.remove(pkl_path)
            return True

        new_metadata = [metadata[i] for i in indices_para_manter]
        new_documents = [documents[i] for i in indices_para_manter]
        
        # Precisas de re-tokenizar para o BM25 (ou guardar os tokens no pkl anteriormente para ser mais rápido)
        new_simple_tokens = [tokenize_and_clean_text(clean_doc_text(doc)) for doc in new_documents]
        new_ngram_docs_2 = [get_ngrams(" ".join(tokens), 2) for tokens in new_simple_tokens]
        new_ngram_docs_3 = [get_ngrams(" ".join(tokens), 3) for tokens in new_simple_tokens]

        # Re-inicializar os objetos BM25
        new_bm25_simple = BM25Okapi(new_simple_tokens)
        new_bm25_2gram = BM25Okapi(new_ngram_docs_2)
        new_bm25_3gram = BM25Okapi(new_ngram_docs_3)

        # Guardar o novo snapshot
        with open(pkl_path, "wb") as f:
            pickle.dump((new_bm25_simple, new_bm25_2gram, new_bm25_3gram, new_metadata, new_documents), f)
    
    return True
