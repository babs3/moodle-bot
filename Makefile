up-streamlit:
	sudo docker compose up -d streamlit-server

build-streamlit:
	sudo docker compose up -d streamlit-server --build

down-streamlit:
	sudo docker compose down streamlit-server


up-flask:
	sudo docker compose up -d flask-server

build-flask:
	sudo docker compose up -d flask-server --build

down-flask:
	sudo docker compose down flask-server


up-actions:
	sudo docker compose up -d action-server

build-actions:
	sudo docker compose up -d action-server --build

down-actions:
	sudo docker compose down action-server


up-rasa:
	sudo docker compose up -d rasa-server

build-rasa:
	sudo docker compose up -d rasa-server --build

down-rasa:
	sudo docker compose down rasa-server


up-all:
	sudo docker compose up -d

build-all:
	sudo docker compose up -d --build

down-all:
	sudo docker compose down

down-all-v:
	sudo docker compose down -v

clean:
	sudo docker system prune