# Use the official Python image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the Streamlit app files into the container
COPY ./streamlit_frontend/requirements.txt /app/requirements.txt
COPY ./streamlit_frontend/app.py /app/app.py
COPY ./streamlit_frontend/utils.py /app/utils.py
COPY ./streamlit_frontend/.streamlit /app/.streamlit
COPY ./streamlit_frontend/assets /app/assets
COPY ./shared /app/shared

# Install dependencies
RUN pip install -r requirements.txt

# Expose Streamlit's default port
EXPOSE 8501

# Command to run the Streamlit app
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
