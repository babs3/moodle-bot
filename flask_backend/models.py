from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class MoodleUsers(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    moodle_id = db.Column(db.Integer, unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    # Define se o utilizador está no modo normal (False) ou tutor (True)
    tutor_mode_active = db.Column(db.Boolean, default=False)

class MoodleQuizAnalysis(db.Model):
    """
    Regista a última análise feita a um quiz específico para evitar repetições.
    """
    id = db.Column(db.Integer, primary_key=True)
    moodle_user_id = db.Column(db.Integer, db.ForeignKey('moodle_users.moodle_id', ondelete="CASCADE"), nullable=False)
    quiz_id = db.Column(db.Integer, nullable=False)  # ID do Quiz no Moodle
    last_attempt_id = db.Column(db.Integer, nullable=False)  # ID da última tentativa analisada
    timestamp = db.Column(db.DateTime, default=datetime.now())

class MoodleUserHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    moodle_user_id = db.Column(db.Integer, db.ForeignKey('moodle_users.moodle_id', ondelete="CASCADE"), nullable=False)
    question = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    pdfs = db.Column(db.String(255), nullable=True)
    # Útil para saber, ao ler o histórico, se aquela conversa foi pedagógica ou geral
    is_tutor_interaction = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.now())