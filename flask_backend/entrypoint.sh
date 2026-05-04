#!/bin/bash

# Só faz init se a pasta migrations não existir
if [ ! -d "migrations" ]; then
    flask db init
fi

flask db migrate
flask db upgrade

# Corre o python a partir da raiz /app
exec python app.py