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
MOODLE_TOKEN=MY_MOODLE_TOKEN_HERE
MOODLE_URL=http://host.docker.internal # or other
APP_DATABASE_USER=MY_DB_USER
APP_DATABASE_PASS=MY_DB_PASSWORD
APP_DATABASE_NAME=MY_DB_NAME
IS_PRODUCTION=True # True or False
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

