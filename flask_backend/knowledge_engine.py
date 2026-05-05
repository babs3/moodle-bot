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
    
    # Clean up the text
    text = clean_ocr_text(text)

    return text

def clean_ocr_text(text):
    # Normalize line endings and remove leading/trailing whitespace
    text = text.strip()
    
    # Remove excess empty lines (more than 1 in a row)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    
    # Remove bullet characters or random artifacts often inserted by OCR
    text = re.sub(r'[\u2022\u00a9¢•™®“”‘’\"*v©®→→←→▪️]+', '', text)

    # Remove OCR garbage lines (non-word content lines)
    text = "\n".join([line for line in text.splitlines() 
                      if re.search(r'\w', line)])  # keep lines with words

    # Remove random floating characters or garbage words
    text = re.sub(r'\b(?:ree|Sex|F 7|Pre-t)\b', '', text, flags=re.IGNORECASE)

    # Remove unwanted punctuation and fix spaces
    text = re.sub(r'\s{2,}', ' ', text)                 # multiple spaces
    text = re.sub(r'\.\s*', '. ', text)                 # dot spacing
    text = re.sub(r'\s+([?.!,])', r'\1', text)          # space before punctuation
    
    # Remove low-quality lines
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if len(line) < 3 and not re.search(r'\w', line): continue
        if re.match(r'^[^a-zA-Z0-9]*$', line): continue
        cleaned_lines.append(line)

    text = '\n'.join(cleaned_lines)

    # Final trimming
    text = text.strip()
    
    return text
 
def get_ngrams(text, n=2):
    doc = nlp(text)
    tokens = [
        token.lemma_.lower()
        for token in doc
        if token.is_alpha and not token.is_stop
    ]
    return [" ".join(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]

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
    
def clean_by_line(text):
    text_lines = text.split('\n')
    
    cleaned_lines = []
    for line in text_lines:
        line = line.strip()
        if not line:
            continue
        if line in LINES_TO_REMOVE:
            #print(f"⚠️  Skipping line: {line}")
            continue
        cleaned_lines.append(line)
    
    cleaned_text = '\n'.join(cleaned_lines)
    
    return cleaned_text.strip()
        
def extract_text_by_context(pdf_path, is_book=False, edited=False, min_word_threshold=20, sim_threshold=0.65):
    """Extracts text from each page of a PDF, merging short pages and sequential numbered sections."""
    doc = fitz.open(pdf_path)
    page_chunks = []
    total_pages = len(doc)
    title = None
    
    print(f"\n\n📄 Processing {pdf_path} with {total_pages} pages...\n")

    i = 0
    while i < total_pages:
        collected_texts = []
        page_numbers = []
        write_title = False
        unformatted_title = False
        title_num = ""
        
        while i < total_pages:
            cleaned_image_text = ""
            print(f"📄 - Page {i + 1} of {total_pages}")
            
            current_text = doc[i].get_text("text").strip()
            current_text = re.sub(r'/\*\*|\*/|LGP\[\]', "", current_text) # for LGP slides style
            
            current_text = clean_by_line(current_text)  # Clean the text by lines
            
            # Only use OCR if the page has no normal text 
            if len(current_text.split()) == 0 and i != 0:
                image_text = extract_text_with_ocr(doc[i])
                if image_text.split() != []:
                    current_text = clean_by_line(image_text)
                    #print(f"    🖼️  current_text is OCR text from page {i + 1}:\n{current_text}")
                else:
                    print(f"     ⚠️  Skipping empty page {i + 1}")
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
                    next_text = clean_by_line(next_text)  # Clean the text by lines
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
                next_text = clean_by_line(next_text)
                
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
                        current_image_text = clean_by_line(current_image_text)
                        print(f"       🖼️  Page {i} has images!\n{current_image_text}")
                        # Stop if it has sufficient OCR text
                        image_word_count = len(current_image_text.split())
                        if image_word_count >= min_word_threshold:
                            collected_texts.pop()
                            collected_texts.append('__PARABREAK__' + current_image_text)
                            break
                        else:
                            print(f"     ⚠️  Page {i} has no suficient content, merging with next...")
                            continue
                    else:
                        print(f"     ⚠️  Page {i} has no suficient content, merging with next...")
                        continue  # Merge with next page
                                   
                    
        
        if write_title:
            #print(f"🏷️  Pages have common title '{title}':") 
            final_text = title + "\n\n" + clean_text("\n\n".join(collected_texts))
        else:
            if edited:
                #print("=> Edited PDF detected!")
                final_text = clean_edited_text("\n\n".join(collected_texts))
            else:
                final_text = clean_text("\n\n".join(collected_texts))
                
        
        page_label = "-".join(page_numbers) if len(page_numbers) > 1 else page_numbers[0]
        page_chunks.append({"text": final_text, "page": page_label})
        
        if write_title:
            print(f"\n-----> 🏷️  Text from page(s) {page_label} w/title '{title}':\n{final_text}\n\n")
        else:
            print(f"\n-----> 🏷️  Text from page(s) {page_label}:\n{final_text}\n\n")

    return page_chunks


def clean_doc_text(text):
    text = text.replace("\n", " ")  # Normalize line breaks
    text = re.sub(r"\s{2,}", " ", text)  # Remove excessive whitespace
    text = re.sub(r"(?<=\w)- (?=\w)", "", text)  # Remove hyphenated line breaks
    text = re.sub(r"\s*-\s*", " - ", text)  # Normalize dash spacing (useful for multiword splits)
    #text = re.sub(r"[^\w\s\-]", "", text)  # Optionally remove punctuation except hyphens
    return text.strip()

def tokenize_and_clean_text(text):
    doc = nlp(text)
    tokens = [
        token.lemma_.lower()  # use lemma (base form), lowercase
        for token in doc
        if not token.is_stop and token.is_alpha  # remove stopwords and punctuation/numbers
    ]
    return tokens

def initialize_chroma():
    # Agora ligamo-nos ao container 'chroma' via HTTP
    # O host é o nome do serviço no docker-compose
    client = chromadb.HttpClient(host='chroma', port=8000)
    return client
            
def process_pdfs(pdf_folder, course_id, vector_db_path="/app/vector_store/"):
    """Processa PDFs de um curso específico e atualiza a base de conhecimento."""
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
                doc_text = chunk["text"]
                documents.append(doc_text)
                
                metadata.append({
                    "file": file, 
                    "page": chunk["page"], 
                    "course_id": str(course_id) 
                })
                
                cleaned_text = tokenize_and_clean_text(clean_doc_text(doc_text))
                simple_tokens.append(cleaned_text)
                ngram_docs_2.append(delete_duplicated_ngrams(get_ngrams(" ".join(cleaned_text), 2)))
                ngram_docs_3.append(delete_duplicated_ngrams(get_ngrams(" ".join(cleaned_text), 3)))
                

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
    
    with open(os.path.join(vector_db_path, "bm25_index.pkl"), "wb") as f:
        pickle.dump((bm25_simple, bm25_2gram, bm25_3gram, metadata, documents), f)
    
    return True

def delete_duplicated_ngrams(ngram_list):
    """Removes duplicate n-grams from a list."""
    seen = set()
    unique_ngrams = []
    for ngram in ngram_list:
        if ngram not in seen:
            seen.add(ngram)
            unique_ngrams.append(ngram)
    return unique_ngrams

# To reduce embeddings noise
def clean_text(text):
    # remove the first '__PARABREAK__' if it exists
    if text.startswith('__PARABREAK__'):
        text = text[13:]  # remove the first 15 characters
        
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
    final_text = re.sub(r"\s*[►¢●•–‣▪◦·‧Øü]\s*", r"\n- ", final_text)
    final_text = re.sub(r"\s*[○]\s*", r"\n    - ", final_text)
    # relace numbered lists with a newline and a dash
    final_text = re.sub(r"\s*(\d+\.\s)", r"\n\1", final_text)  # forces numbered items to a new line
    
    # Remove hyphens between letters (e.g., "num- ber" -> "number")
    text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)
    # Normalize multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Final cleanup of whitespace and over-newlines
    final_text = re.sub(r'\n{3,}', '\n\n', final_text).strip()
    
    return final_text

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

def delete_pdf_from_knowledge(filename, course_id, vector_db_path="/app/vector_store/"):
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
        print(f"🗑️ Removidos {len(results['ids'])} chunks do ficheiro: {filename}")
    else:
        print(f"⚠️ Nenhum registo encontrado para {filename} no curso {course_id}")
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
        new_ngram_docs_2 = [delete_duplicated_ngrams(get_ngrams(" ".join(tokens), 2)) for tokens in new_simple_tokens]
        new_ngram_docs_3 = [delete_duplicated_ngrams(get_ngrams(" ".join(tokens), 3)) for tokens in new_simple_tokens]

        # Re-inicializar os objetos BM25
        new_bm25_simple = BM25Okapi(new_simple_tokens)
        new_bm25_2gram = BM25Okapi(new_ngram_docs_2)
        new_bm25_3gram = BM25Okapi(new_ngram_docs_3)

        # Guardar o novo snapshot
        with open(pkl_path, "wb") as f:
            pickle.dump((new_bm25_simple, new_bm25_2gram, new_bm25_3gram, new_metadata, new_documents), f)
    
    return True


if __name__ == "__main__":
    process_pdfs()
