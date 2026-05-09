from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class MoodleUsers(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    moodle_id = db.Column(db.Integer, unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    
class TutorModeState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_moodle_id = db.Column(db.Integer, db.ForeignKey('moodle_users.moodle_id', ondelete="CASCADE"), nullable=False)
    course_id = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    last_updated = db.Column(db.DateTime, default=datetime.now)

class MoodleQuizAnalysis(db.Model):
    """
    Regista a última análise feita a um quiz específico para evitar repetições.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_moodle_id = db.Column(db.Integer, db.ForeignKey('moodle_users.moodle_id', ondelete="CASCADE"), nullable=False)
    quiz_id = db.Column(db.Integer, nullable=False)  # ID do Quiz no Moodle
    last_attempt_id = db.Column(db.Integer, nullable=False)  # ID da última tentativa analisada
    last_updated = db.Column(db.DateTime, default=datetime.now)

class MoodleQuizPolling(db.Model):
    """
    Regista os quizzes que já foram processados para evitar análises repetidas.
    """
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, unique=True, nullable=False)  # ID do Quiz no Moodle
    quiz_name = db.Column(db.String(255), nullable=False)
    questions_hash = db.Column(db.String(255), nullable=False)  # Hash das perguntas para detectar mudanças
    last_updated = db.Column(db.DateTime, default=datetime.now)
    
class MoodleQuizData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('moodle_quiz_polling.quiz_id', ondelete="CASCADE"), nullable=False)  # ID do Quiz no Moodle
    question = db.Column(db.Text, nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey('topics.id', ondelete="SET NULL"), nullable=True)
    last_updated = db.Column(db.DateTime, default=datetime.now)
    
class MoodleUserHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_moodle_id = db.Column(db.Integer, db.ForeignKey('moodle_users.moodle_id', ondelete="CASCADE"), nullable=False)
    question = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    pdfs = db.Column(db.String(255), nullable=True)
    is_tutor_interaction = db.Column(db.Boolean, default=False)
    time_to_respond = db.Column(db.String(100), nullable=False)  # Tempo que o bot levou para responder
    last_updated = db.Column(db.DateTime, default=datetime.now)
    
class TutorProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_moodle_id = db.Column(db.Integer, db.ForeignKey('moodle_users.moodle_id', ondelete="CASCADE"), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)  # Ex: "TrueFalse", "MultipleChoice", "ShortAnswer"
    topic_id = db.Column(db.Integer, db.ForeignKey('topics.id', ondelete="SET NULL"), nullable=True)  # Relaciona com a tabela de tópicos
    question = db.Column(db.Text, nullable=False)
    student_answer = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.Text, nullable=False)
    state=db.Column(db.String(20), default="pending", nullable=False)  # Ex: "pending", "reviewed", "mastered"
    last_updated = db.Column(db.DateTime, default=datetime.now)
    
class Topics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    
class KnowledgeFiles(db.Model):        
    id = db.Column(db.Integer, primary_key=True)
    courseid = db.Column(db.Integer, nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.now)

    def __repr__(self):
        return f'<File {self.filename}>'