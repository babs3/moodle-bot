#!/bin/bash

# Run database migrations
flask db init
flask db migrate
flask db upgrade

# Start Flask application
exec python app.py
