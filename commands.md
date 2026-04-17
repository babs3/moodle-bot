## Connect to repository
Clone the babs3/rasa-engi-bot repository. Then run the following commands:
```
git config --global user.name "babs3"
git config --global user.email "barbaraema3@gmail.com"
```

Copy the `.env` file and `materials` folder.

`.env` file template:
```
GOOGLE_API_KEY=MY_API_KEY_HERE
COOKIES_SECRET_KEY=MY_COOKIES_SECRET_KEY_HERE
CURRENT_CLASS=GEE   # GEE, SCI, LGP or GEE_LGP
APP_DATABASE_USER=MY_DB_USER
APP_DATABASE_PASS=MY_DB_PASSWORD
APP_DATABASE_NAME=MY_DB_NAME
ADMIN_EMAIL=YOUR_EMAIL_HERE
MAIL_USERNAME=NO-REPLY_EMAIL_HERE
MAIL_PASSWORD=NO-REPLY_EMAIL_APP_PASSWORD_HERE
IS_PRODUCTION=True # True or False
DOMAIN=localhost #engi-bot-gee.duckdns.org or other
#--- for GEE
INITIAL_SPREADSHEET_ID=1tPsTARWtyvpedZVDgkBW0ezP9HzGztYfhPReTq1ExyU
FORM_URL=https://forms.gle/RrxV3fnCyqv5cYBb9
QUIZ_SPREADSHEET_ID=1Uns7r9X2ENXcJdV3vQfRq6Dw3rqFk6imGYE66vfMxHk
QUIZ_URL=https://forms.gle/eVmKWH8o9mo8Zd5fA
#--- for SCI
#INITIAL_SPREADSHEET_ID=1_UeINZTkZBH7n-PCyVrki65S3cVUup_-JWWpKcYdYko
#FORM_URL=https://forms.gle/cUf3QwTTFQwiHraB7
#QUIZ_SPREADSHEET_ID=14iGhTJFvhl9p3AVyI5iDW5gKxuwqG6x_O0C5gJTEmcY
#QUIZ_URL=https://forms.gle/6mefQuZLPJFhdVTi6
#--- for LGP
#INITIAL_SPREADSHEET_ID=170XqVYEWiCirXZUJOPbbwND0g27PbkLqWL3Os_sjrO0
#FORM_URL=https://forms.gle/NgDeXJpXjfKTc4L1A
#QUIZ_SPREADSHEET_ID=1yY7HBDJsHLVH-AWgkv3UrewFyj651ac89j9Jvhx9mFU
#QUIZ_URL=https://forms.gle/UyZoApqZziuV3PVa6
#--- common in all classes:
FINAL_SPREADSHEET_ID=1olGNcw2PaeKFbSPwmdRpi61hBcm5Ye6ykdWWFBlVL1I
FINAL_FORM_URL=https://forms.gle/oeriyzjA6ELou6L66
TEACHER_FINAL_FORM_URL=https://forms.gle/n9kv7DRSFF8feNAH8
TEACHER_FINAL_SPREADSHEET_ID=1QRSf3ULa7J_gIMBKasaSjqdKam-zWXkWp-D4QMz3Pz0
```

Inside `.streamlit` folder of `./streamlit_frontend`, create a `secrets.toml` file and change to the right domain (DOMAIN_HERE). My dommains are currently mapped using **Duck DNS**. If running locally, the domain is *localhost*.

`secrets.toml` file template:
```
[auth]
redirect_uri = "http://DOMAIN_HERE/oauth2callback"
cookie_secret = MY_COOKIES_SECRET_KEY_HERE
client_id = MY_CLIENT_ID_HERE
client_secret = MY_CLIENT_SECRET_HERE
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"`
```

Create a `credentials.json` file inside `flask-backend`:
```
{
    "type": "service_account",
    "project_id": YOUR_PROJECT_ID,
    "private_key_id": YOUR_PRIVATE_KEY_ID,
    "private_key": YOUR_PRIVATE_KEY_HERE,
    "client_email": YOUR_CLIENT_SERVICE_ACCOUNT,
    "client_id": YOUR_CLIENT_ID,
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/form-responses%40uporto-chatbot-authentication.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com"
  }
```


## Install docker on VM
```
sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt install git curl unzip tar make sudo vim wget nano -y
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu
newgrp docker
rm get-docker.sh
```

## Virtual Environment
Outside of `rasa-engi-bot` folder create a virtual environment:
```
cd ..
sudo apt install python3.10-venv
python3 -m venv rasa-env
source rasa-env/bin/activate
```

## Bot Pipeline
Generate embeddings and download model
```
cd ./rasa-engi-bot
pip install -r requirements.txt
python -m spacy download en_core_web_sm
sudo apt install tesseract-ocr # to use ocr
python process_pdfs.py
python load_model.py # just if it's not already loaded
deactivate
```

Start Containers
```
sudo docker compose up -d
```
Build Containers
```
sudo docker compose up -d --build
```
Pause the containers
```
sudo docker compose stop
```
Stop and Remove Containers Gracefully
```
sudo docker compose down
```
```
sudo docker compose down -v  # Stops all services and removes named volumes
```
Check if containers are running
```
sudo docker container ls -a
```

## Test the bot

### Locally:
Open ```http://localhost/``` to test the bot.
Open ```http://localhost:8081``` to access the Adminer view of db.

### Production Server:

#### GEE
Open ```http://engi-bot-gee.duckdns.org/``` to test the bot.
Open ```http://engi-bot-gee.duckdns.org:8081``` to access the Adminer view of db.

#### LGP
Open ```http://engi-bot-lgp.duckdns.org/``` to test the bot.
Open ```http://engi-bot-lgp.duckdns.org:8081``` to access the Adminer view of db.

#### SCI
Open ```http://engi-bot-sci.duckdns.org/``` to test the bot.
Open ```http://engi-bot-sci.duckdns.org:8081``` to access the Adminer view of db.


## Useful commands:

Reports information about space on file system
```
df -h
```
Monitor the resources of the Linux operating system in real time
```
htop
```

Gain space by removing all unused containers, networks and images (both dangling and unused).
```
docker system prune
```

Command to generate requirements
```
pipreqs . --force
```

Upgrade VM volume storage, after update on AWS:
```
sudo growpart /dev/nvme0n1 1
sudo resize2fs /dev/nvme0n1p1
```

Train a model (Only train models locally‼️)
```
docker run -v ${PWD}:/app rasa/rasa:3.6.20-full train
```

