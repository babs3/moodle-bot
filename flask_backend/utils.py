from flask import Flask, jsonify
from flask_cors import CORS
import hashlib
from flask_mail import Mail, Message
import os
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from google.oauth2 import service_account
from googleapiclient.discovery import build
from flask_backend.models import *

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
DOMAIN = os.getenv("DOMAIN")

app = Flask(__name__)
CORS(app) # Isto permite que o Moodle aceda à API

# Flask-Mail Configuration
app.config["MAIL_SERVER"] = "smtp.gmail.com"  # Use your SMTP provider
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")  # Your no-reply email address
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_USERNAME") 
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")  # App-specific password

app.config["SQLALCHEMY_DATABASE_URI"] = f'postgresql://{os.getenv("POSTGRES_USER")}:{os.getenv("POSTGRES_PASSWORD")}@db/{os.getenv("POSTGRES_DB")}'
app.config["JWT_SECRET_KEY"] = "super-secret-key"  # Change in production!
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

mail = Mail(app)

db.init_app(app)
migrate = Migrate(app, db)  # For database migrations
jwt = JWTManager(app)

def send_email_to_admin_about_teacher_request(user):
    subject = "New Teacher Registration Request"
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f9f9f9; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background-color: #ffffff; border-radius: 8px; padding: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
        <h2 style="color: #2c3e50;">📬 New Teacher Registration Request</h2>
        
        <p style="font-size: 16px; color: #34495e;">
            A new teacher has requested to register on the AI-Based Tutoring System:
        </p>

        <table style="width: 100%; margin-top: 20px; font-size: 16px;">
            <tr>
            <td style="font-weight: bold; color: #2c3e50;">👤 Name:</td>
            <td>{user.name}</td>
            </tr>
            <tr>
            <td style="font-weight: bold; color: #2c3e50;">📧 Email:</td>
            <td>{user.email}</td>
            </tr>
        </table>

        <p style="margin-top: 30px; font-size: 15px; color: #555;">
            Please review this request in your admin panel or reply to this email with further instructions.
        </p>

        <p style="margin-top: 40px; font-size: 14px; color: #999;">
            This is an automated message from the EngiBot Tutoring System.
        </p>
        </div>
    </body>
    </html>
    """

    try:
        msg = Message(subject, recipients=[ADMIN_EMAIL], html=html_body)
        mail.send(msg)
        #print(f"Confirmation email sent to {email}")
        return jsonify({"message": f"✅ Confirmation email sent to {ADMIN_EMAIL}"}), 200
    except Exception as e:
        print(f"Failed to send email: {e}")
        return jsonify({"message": f"❌ Failed to send email: {e}"}), 500

def send_confirmation_email(email, otp):

    subject = "✅ Verify Your Email Address"
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
  <style>
    body {{
      font-family: Arial, sans-serif;
      background-color: #f4f4f4;
      color: #333;
      padding: 20px;
    }}
    .container {{
      background-color: #fff;
      padding: 20px;
      border-radius: 10px;
      max-width: 500px;
      margin: auto;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }}
    .otp {{
      font-size: 24px;
      font-weight: bold;
      background-color: #e8f0fe;
      padding: 10px;
      border-radius: 6px;
      display: inline-block;
      letter-spacing: 2px;
    }}
    .footer {{
      margin-top: 20px;
      font-size: 12px;
      color: #888;
    }}
  </style>
</head>
<body>
  <div class="container">
    <h2>🔐 Email Verification</h2>
    <p>Hi there,</p>
    <p>Use the code below to verify your account:</p>
    <div class="otp">{otp}</div>
    <p>If you didn’t request this, you can safely ignore this email.</p>
    <p>Thanks,<br><strong>Your Chatbot Team</strong></p>
    <div class="footer">
      &copy; 2025 Your Chatbot Platform. All rights reserved.
    </div>
  </div>
</body>
</html>
    """
    try:
        msg = Message(subject, recipients=[email], html=html_body)
        mail.send(msg)
        #print(f"Confirmation email sent to {email}")
        return jsonify({"message": f"✅ Confirmation email sent to {email}"}), 200
    except Exception as e:
        print(f"Failed to send email: {e}")
        return jsonify({"message": f"❌ Failed to send email: {e}"}), 500

def send_reset_password_email(reset_link, email):
    subject = "🔐 Reset Your Password"

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
  <style>
    body {{
      font-family: Arial, sans-serif;
      background-color: #f4f4f4;
      color: #333;
      padding: 20px;
    }}
    .container {{
      background-color: #fff;
      padding: 25px;
      border-radius: 10px;
      max-width: 520px;
      margin: auto;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }}
    .button {{
      display: inline-block;
      background-color: #4CAF50;
      color: white !important;
      padding: 12px 20px;
      border-radius: 6px;
      text-decoration: none;
      font-size: 16px;
      font-weight: bold;
      margin: 20px 0;
    }}
    .button:hover {{
      background-color: #45a049;
    }}
    .link-box {{
      background-color: #e8f0fe;
      padding: 10px;
      border-radius: 6px;
      word-break: break-all;
      font-size: 14px;
    }}
    .footer {{
      margin-top: 25px;
      font-size: 12px;
      color: #888;
      text-align: center;
    }}
  </style>
</head>
<body>
  <div class="container">
    <p>Hello,</p>

    <p>You requested a <strong>password reset</strong>. Click the button below to choose a new password:</p>

    <a class="button" href="{reset_link}" target="_blank">Reset Password</a>

    <p>This link will expire in <strong>30 minutes</strong> for security reasons.</p>

    <p>If you did not request this change, you can safely ignore this email.</p>

    <p>Thanks,<br><strong>EngiBot Team</strong></p>

    <div class="footer">
      &copy; 2025 EngiBot Platform. All rights reserved.
    </div>
  </div>
</body>
</html>
"""
    
    try:
        msg = Message(subject, recipients=[email], html=html_body)
        mail.send(msg)
        #print(f"Confirmation email sent to {email}")
        return jsonify({"message": f"✅ Confirmation email sent to {email}"}), 200
    except Exception as e:
        print(f"Failed to send email: {e}")
        return jsonify({"message": f"❌ Failed to send email: {e}"}), 500
    
def get_form_emails(spreadsheet_id):
    SERVICE_ACCOUNT_FILE = 'credentials.json'
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    RANGE_NAME = 'Form Responses!B2:B'  # assuming email is in column B

    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)

    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=spreadsheet_id,range=RANGE_NAME).execute()
    values = result.get('values', [])
    
    return [row[0].strip().lower() for row in values if row]

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def seed_database():
    with app.app_context():
        # Check if table is empty before seeding
        if not Classes.query.first():
            classes = [
                Classes(code="GEE", number="3", group="G11", course="MEIC"),
                Classes(code="GEE", number="3", group="G12", course="MEIC"),
                Classes(code="GEE", number="3", group="G13", course="MEIC"),
                Classes(code="GEE", number="3", group="G14", course="MEIC"),
                
                Classes(code="GEE", number="4", group="G51", course="MEIC"),
                Classes(code="GEE", number="4", group="G52", course="MEIC"),
                Classes(code="GEE", number="4", group="G53", course="MEIC"),
                Classes(code="GEE", number="4", group="G54", course="MEIC"),
                Classes(code="GEE", number="4", group="G55", course="MEIC"),
                
                Classes(code="GEE", number="5", group="G31", course="MEIC"),
                Classes(code="GEE", number="5", group="G32", course="MEIC"),
                Classes(code="GEE", number="5", group="G33", course="MEIC"),
                Classes(code="GEE", number="5", group="G34", course="MEIC"),
                
                Classes(code="GEE", number="6", group="G21", course="MEIC"),
                Classes(code="GEE", number="6", group="G22", course="MEIC"),
                Classes(code="GEE", number="6", group="G23", course="MEIC"),
                Classes(code="GEE", number="6", group="G24", course="MEIC"),
                
                Classes(code="GEE", number="7", group="G41", course="MEIC"),
                Classes(code="GEE", number="7", group="G42", course="MEIC"),             
                Classes(code="GEE", number="7", group="G43", course="MEIC"),             
                Classes(code="GEE", number="7", group="G44", course="MEIC"),             
                
                
                Classes(code="SCI", number="1", course="MEIC"),


                Classes(code="LGP", number="01", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="02", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="03", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="04", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="05", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="06", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="07", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="08", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="09", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="10", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="11", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="12", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="13", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="14", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="15", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="16", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="17", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="18", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="19", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="20", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="21", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="22", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="23", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="24", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="25", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="26", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="27", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="28", course="MEEE,MEIC,MESG,MESW,MM"),
                Classes(code="LGP", number="29", course="MEEE,MEIC,MESG,MESW,MM")
                
            ]
            db.session.bulk_save_objects(classes)
            db.session.commit()
            print("Database seeded successfully!")
        else:
            print("Database already seeded. Skipping.")

        # Seed Default Student
        student_email = "student@example.com"
        default_student = Users.query.filter_by(email=student_email).first()
        if not default_student:
            student_user = Users(
                name="Default Student",
                role="Student",  # Ensure lowercase matches database
                email=student_email,
                password=hash_password("pass"),  # Hash password for security
                otp="000000",
                is_verified="True",
                form_filled="True"  # Assuming the form is filled for the default student
            )
            db.session.add(student_user)
            db.session.commit()  # Commit to get ID

            student_entry = Student(
                up="000000000",
                user_id=student_user.id,  # Now it exists
                course="MEIC",
                year=1,
                class_id="1",
            )
            db.session.add(student_entry)
            db.session.commit()
            print("Default student added!")
        else:
            print("Default student already exists. Skipping seeding.")

        # Seed Default Professor
        professor_email = "professor@example.com"
        default_professor = Users.query.filter_by(email=professor_email).first()
        if not default_professor:
            professor_user = Users(
                name="Default Professor",
                role="Teacher",  # Ensure lowercase matches database
                email=professor_email,
                password=hash_password("pass"),  # Hash password
                otp="000001",
                is_verified="True",
                form_filled="True" # Assuming the form is filled for the default professor
            )
            db.session.add(professor_user)
            db.session.commit()  # Commit to get ID

            professor_entry = Teacher(
                user_id=professor_user.id,  # Now it exists
                classes="1,2,3,4,5,6,7,8,9,10,11,12,13,14,15", # ... all classes
                is_approved="Approved"  # Default approval status
            )
            db.session.add(professor_entry)
            db.session.commit()
            print("Default professor added!")
        else:
            print("Default professor already exists. Skipping seeding.")
            
        # Seed Default Worker
        worker_email = "worker@example.com"
        default_worker = Users.query.filter_by(email=worker_email).first()
        if not default_worker:
            worker_user = Users(
                name="Default Worker",
                role="Other",  # Ensure lowercase matches database
                email=worker_email,
                password=hash_password("pass"),  # Hash password for security
                otp="000002",
                is_verified="True",
                form_filled="True" # Assuming the form is filled for the default worker
            )
            db.session.add(worker_user)
            db.session.commit()
            
            worker_entry = Other(
                user_id=worker_user.id,  # Now it exists
                role="Worker",
                job="Worker",
                company="Default Company",
                graduation_year="2025",
                graduation_area="Engineering"
            )
            db.session.add(worker_entry)
            db.session.commit()
            
            print("Default worker added!")
        else:
            print("Default worker already exists. Skipping seeding.")
        