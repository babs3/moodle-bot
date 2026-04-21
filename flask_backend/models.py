from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()
    
class MoodleUsers(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    moodle_id = db.Column(db.Integer, unique=True, nullable=False)  # Moodle user ID
    email = db.Column(db.String(100), unique=True, nullable=False)  # User's email

class MoodleUserHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    moodle_user_id = db.Column(db.Integer, db.ForeignKey('moodle_users.moodle_id', ondelete="CASCADE"), nullable=False)
    question = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    pdfs = db.Column(db.String(255), nullable=True)  # Comma-separated PDF references
    timestamp = db.Column(db.DateTime, default=datetime.now())
    
