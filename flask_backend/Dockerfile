FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY ./flask_backend/requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN python -m spacy download en_core_web_sm
RUN python -m nltk.downloader -d /app/nltk_data wordnet omw-1.4

ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV NLTK_DATA=/app/nltk_data

EXPOSE 8080

# O entrypoint agora vai ler o script que o volume do docker-compose disponibilizar
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]