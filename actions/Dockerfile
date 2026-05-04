FROM rasa/rasa-sdk:3.6.2

WORKDIR /app

# 1. Mudar para root logo no início para preparar o terreno
USER root

# 2. Instalar dependências de sistema (se necessário) e atualizar pip
RUN pip install --no-cache-dir --upgrade pip

# 3. Cache das dependências (requirements)
# Copiamos APENAS o requirements primeiro. 
# Se o requirements não mudar, o Docker salta a instalação no próximo build.
COPY ./actions/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# 4. Cache de Modelos Pesados
# Modelos de spaCy, NLTK e o teu modelo local mudam raramente.
# Mantê-los aqui garante que não perdes tempo a baixá-los novamente.
RUN python -m spacy download en_core_web_sm && \
    python -m nltk.downloader -d /app/nltk_data wordnet omw-1.4

# Copiar o modelo local (se ele for grande, deve estar antes do código)
COPY ./models/all-MiniLM-L6-v2 /app/models/all-MiniLM-L6-v2

# 5. Configurações de Ambiente e Pastas
ENV NLTK_DATA=/app/nltk_data
ENV TRANSFORMERS_CACHE=/app/cache
RUN mkdir -p /app/cache /app/db && chown -R 1000:1000 /app/cache /app/db /app/nltk_data

# 6. O ERRO FATAL: REMOVER A CÓPIA DO VECTOR_STORE
# Não faças COPY ./vector_store. Porquê?
# - O volume no docker-compose já faz esse trabalho.
# - Se o fizeres aqui, o build vai demorar imenso a copiar gigas de dados que vão ser 
#   substituídos pelo volume assim que o container ligar.

# 7. Código das Actions (Muda frequentemente, por isso fica no fim)
COPY ./actions /app/actions

# Voltar para o utilizador da Rasa
USER 1000

CMD ["start", "--actions", "actions"]