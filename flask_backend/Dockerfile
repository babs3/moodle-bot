# 1. Usar Python 3.10 para compatibilidade com as versões recentes de spaCy/Thinc
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# 2. Instalar dependências de sistema (Tesseract para OCR e ferramentas de compilação)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. Copiar os ficheiros de requisitos primeiro (melhora o cache do Docker)
COPY ./flask_backend/requirements.txt /app/requirements.txt

# 4. Atualizar o pip e instalar dependências
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Download de modelos de processamento de linguagem
RUN python -m spacy download en_core_web_sm
RUN python -m nltk.downloader -d /app/nltk_data wordnet omw-1.4

# 6. Copiar o restante código da aplicação
COPY ./flask_backend/app.py /app/app.py
COPY ./flask_backend/utils.py /app/utils.py
COPY ./flask_backend/models.py /app/models.py
COPY ./flask_backend/entrypoint.sh /app/entrypoint.sh
COPY ./flask_backend/credentials.json /app/credentials.json
COPY ./flask_backend/knowledge_engine.py /app/knowledge_engine.py

# Copiar modelo local de embeddings
COPY ./models/all-MiniLM-L6-v2 /app/models/all-MiniLM-L6-v2

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
# Garantir que o NLTK encontra os dados
ENV NLTK_DATA=/app/nltk_data

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Expose the port
EXPOSE 8080

# Use entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]