FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy application files
COPY ./flask_backend/app.py /app/app.py
COPY ./flask_backend/utils.py /app/utils.py
COPY ./flask_backend/requirements.txt /app/requirements.txt
COPY ./flask_backend/models.py /app/models.py
COPY ./flask_backend/entrypoint.sh /app/entrypoint.sh
COPY ./flask_backend/credentials.json /app/credentials.json

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Expose the port
EXPOSE 8080

# Use entrypoint script to initialize DB before running Flask
ENTRYPOINT ["/app/entrypoint.sh"]
#CMD ["python", "app.py"]
