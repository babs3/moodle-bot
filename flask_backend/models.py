from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# Users Table (Parent for Student and Teacher)
class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    role = db.Column(db.String(20), nullable=False)  # "student" or "teacher" or "other"
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    otp = db.Column(db.Integer, nullable=True)
    is_verified = db.Column(db.String(20), default="False") # "True" or "False"
    form_filled = db.Column(db.String(20), default="False") # "True" or "False" # TODO: remove
    
    # Relationship with Student (cascade delete enabled)
    student = db.relationship('Student', backref='user', uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    teacher = db.relationship('Teacher', backref='user', uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    other = db.relationship('Other', backref='user', uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    messages = db.relationship('MessageHistory', backref='user', cascade="all, delete-orphan", passive_deletes=True) 
    progress = db.relationship('UserProgress', backref='user', cascade="all, delete-orphan", passive_deletes=True)  
    resetToken = db.relationship('PasswordResetTokens', backref='user', cascade="all, delete-orphan", passive_deletes=True)
    
    
    
class MoodleUsers(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    moodle_id = db.Column(db.Integer, unique=True, nullable=False)  # Moodle user ID
    email = db.Column(db.String(100), unique=True, nullable=False)  # User's email

class MoodleUserHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    moodle_user_id = db.Column(db.Integer, db.ForeignKey('moodle_users.moodle_id', ondelete="CASCADE"), nullable=False)
    question = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now())
    
    

class PasswordResetTokens(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), db.ForeignKey('users.email', ondelete="CASCADE"), nullable=False)
    token = db.Column(db.String(100), nullable=False)
    expiry = db.Column(db.DateTime(timezone=True), nullable=False)

# Student Table (Extends Users)
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, unique=True)
    up = db.Column(db.Integer, nullable=False)  # Unique student identifier
    course = db.Column(db.String(100), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    class_id = db.Column(db.String, nullable=True)

# Teacher Table (Extends Users)
class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, unique=True)
    classes = db.Column(db.String, nullable=False) # Comma-separated class ids
    is_approved = db.Column(db.String(20), default="Pending")  # "Pending", "Approved", or "Rejected"

class Other(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False, unique=True)
    role = db.Column(db.String(100), nullable=False)  # e.g., "Researcher", "Worker", etc.
    job = db.Column(db.String(100)) 
    company = db.Column(db.String(100))
    graduation_year = db.Column(db.String(100))  # e.g., "2023"
    graduation_area = db.Column(db.String(100))  # e.g., "Engineering", "Arts", etc.    

# Classes Table
class Classes(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False)
    number = db.Column(db.String(20), default="1")
    group = db.Column(db.String(20), nullable=True)  # e.g., "G1", "G2", etc. ?????
    course = db.Column(db.String(100), nullable=True)
    
# Message History Table
class MessageHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    question = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now())  
    
# Student Progress Table
class UserProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.String, nullable=True) # null if not in class
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False)
    question = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    #topic = db.Column(db.String(100), nullable=True) #TODO: connect to Topics table using foreign key
    topic_id = db.Column(db.Integer, db.ForeignKey('topics.id', ondelete="SET NULL"), nullable=True)  # Foreign key to Topics table
    pdfs = db.Column(db.String(255), nullable=True)  # Comma-separated PDF references
    response_time = db.Column(db.String(100), nullable=False)  # Time taken to generate the response in seconds
    timestamp = db.Column(db.DateTime, default=datetime.now())
    
class Topics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(100), nullable=True)

