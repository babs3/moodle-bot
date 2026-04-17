import streamlit as st
import re
import hashlib
from datetime import datetime, timedelta, timezone
from time import sleep
import requests
import json
import os
import io
import zipfile
from dotenv import load_dotenv
import pandas as pd
import streamlit.components.v1 as components
import logging
logging.getLogger("streamlit.runtime.caching").setLevel(logging.ERROR)

import secrets, time

from shared.flask_requests import *

load_dotenv()
CURRENT_CLASS = os.getenv("CURRENT_CLASS")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
COURSES = ["MEEE", "MEIC", "MESG", "MESW", "MM", "MIEIC", "Other"]
INITIAL_SPREADSHEET_ID = os.getenv("INITIAL_SPREADSHEET_ID")
FINAL_SPREADSHEET_ID = os.getenv("FINAL_SPREADSHEET_ID")
QUIZ_SPREADSHEET_ID = os.getenv("QUIZ_SPREADSHEET_ID")

def display_bot_header(mode):
    header = st.container()
    header.markdown(
        "<div class='fixed-header'><h1 class='engibot-title'>💬 Chat with EngiBot</h1></div>",
        unsafe_allow_html=True
    )

    # Theme colors
    if mode == "dark":
        bg_color = "#0e1117"
        text_color = "#f0f2f6"
    else:
        bg_color = "#ffffff"
        text_color = "#262730"

    # CSS with mobile visibility control
    html = f"""
    <style>
        div[data-testid="stVerticalBlock"] div:has(div.fixed-header) {{
            position: sticky;
            top: 0rem;
            background-color: {bg_color};
            color: {text_color};
            z-index: 999991;
            padding: 0.3rem 0 0.6rem 0;
        }}

        .fixed-header {{
            border-bottom: 2px solid {text_color};
        }}

        .engibot-title {{
            font-size: 2rem;
            font-weight: 700;
            margin: 0;
            
            padding: 0 1rem 0.5rem 1rem;
            line-height: 1.2;
        }}

        /* 🔒 Hide on screens narrower than 480px */
        @media screen and (max-width: 480px) {{
            .fixed-header {{
                display: none;
            }}
        }}
        
    </style>
    """
    st.markdown(html, unsafe_allow_html=True)
  
def show_no_data_message(mode):
    # Define theme-based colors
    if mode == "dark":
        box_bg = "#0e1117"
        text_color = "#f0f2f6"
    else:
        box_bg = "#ffffff"
        text_color = "#262730"

    html_code = f"""
        <div style='
            font-size: 1rem;
            font-family: "Source Sans Pro", sans-serif;
            color: {text_color};
            background-color: {box_bg};
            padding: 0.8rem 1rem;
            border-left: 4px solid #f0ad4e;
            border-radius: 8px;
            margin-top: 1rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        '>
        ⚠️ Interact with the bot to see your progress.
        </div>
        """
    
    components.html(html_code, height=85)
    
def show_initial_form_prompt(form_url, mode):
    # Define theme-based colors
    if mode == "dark":
        box_bg = "#262730"
        text_color = "#f0f2f6"
        button_bg = "#e67e22"
        button_hover = "#f39c12"
    else:
        box_bg = "#f0f2f6"
        text_color = "#262730"
        button_bg = "#f39c12"
        button_hover = "#e67e22"

    html_code = f"""
    <head>
        <link href="https://fonts.googleapis.com/css2?family=Source+Sans+Pro&display=swap" rel="stylesheet">
        <style>
            .require-form-container {{
                font-family: 'Source Sans Pro', sans-serif;
                background-color: {box_bg};
                border-left: 6px solid {button_bg};
                border-radius: 12px;
                box-shadow: 0 4px 10px rgba(0,0,0,0.08);
                padding: 1.25rem;
                margin-top: 4rem;
            }}
            .require-form-container h3 {{
                margin-top: 0;
                font-size: 1.5rem;
                color: {text_color};
            }}
            .require-form-container p {{
                font-size: 1.05rem;
                color: {text_color};
                margin-bottom: 1.2rem;
            }}
            .require-form-link {{
                text-align: center;
                margin: 1rem 0;
            }}
            .require-form-link a {{
                background-color: {button_bg};
                color: white;
                padding: 0.65rem 1.5rem;
                border-radius: 8px;
                font-weight: bold;
                text-decoration: none;
                font-size: 1rem;
                display: inline-block;
                transition: background-color 0.3s ease;
            }}
            .require-form-link a:hover {{
                background-color: {button_hover};
            }}
            .note {{
                font-size: 0.9rem;
                color: {text_color};
                text-align: center;
                margin-top: 0.5rem;
            }}
        </style>
    </head>
    <body>
        <div class="require-form-container">
            <h3>⚠️ Access Restricted</h3>
            <p>Before using the chatbot, we kindly ask you to fill out a short form. This helps us understand who's using the bot and improve it based on your needs.</p>
            <div class="require-form-link">
                <a href="{form_url}" target="_blank">✍️ Fill the Initial Form</a>
            </div>
            <p class="note">Already submitted? Confirm below to proceed.</p>
        </div>
    </body>
    """

    # Show the styled section
    components.html(html_code, height=350)

# Percent delta helpers
def percent_delta(current, previous):
    if previous == 0:
        return "New" if current > 0 else "0%"
    delta = ((current - previous) / previous) * 100
    return f"{delta:+.1f}%"

def show_dashboard_title(title, subtitle, mode):
    # Define theme-based colors
    if mode == "dark":
        box_bg = "#0e1117"
        box_border = "#84ccfc"
        box_shadow = "rgba(101, 171, 236, 0.2)"
        title_color = "#ffffff"
        text_color = "#f0f2f6"
    else:
        box_bg = "#e8f1fa"
        box_border = "#0068c9"
        box_shadow = "rgba(0, 104, 201, 0.2)"
        title_color = "#0e1117"
        text_color = "#262730"

    html_code = f"""
    <head>
        <link href="https://fonts.googleapis.com/css2?family=Source+Sans+Pro:wght@600&display=swap" rel="stylesheet">
        <style>
        div#title_box {{
            font-family: 'Source Sans Pro', sans-serif;
            background-color: {box_bg};
            padding: 0.55rem 0.8rem;
            border-radius: 10px 10px 0px 0px; 
            
            /* Set border on top, left, and right only */
            border-top: 3px solid {box_border};
            border-left: 3px solid {box_border};
            border-right: 3px solid {box_border};
            border-bottom: none;

            /* Shadow only at the bottom */
            box-shadow: 0px 8px 5px {box_shadow};
            margin: 0 -0.5rem 1rem -0.5rem;
        }}
        
        div#title_box h1 {{
            font-size: 1.65rem;
            margin: 0 0 0.4rem 0;
            color: {title_color};
        }}
        
        div#title_box p {{
            font-size: 0.95rem;
            color: {text_color};
            margin: 0;
            padding-bottom: 0.3rem;
        }}
        
        @media screen and (max-width: 480px) {{            
            div#title_box p {{
                padding-bottom: 0.1rem;
            }}
        }}
        </style>
    </head>
    <body>
        <div id="title_box">
            <h1>📊 {title}</h1>
            <p>{subtitle}</p>
        </div>
    </body>
    """
    
    components.html(html_code, height=123)
    
def styled_subheader(title, emoji, mode):
    if mode == "dark":
        box_bg = "#0e1117"
        box_border = "#84ccfc"
        text_color = "#f0f2f6"
    else:
        box_bg = "#e8f1fa"
        box_border = "#0068c9"
        text_color = "#262730"

    html_code = f"""
    <head>
    <style>
        div#subtitles_box {{
            font-family: 'Source Sans Pro', sans-serif;
            font-size: 1.3rem;
            color: {text_color};
            background-color: {box_bg};
            padding: 0.4rem 0.8rem;
            border-left: 3px solid {box_border};
            border-radius: 8px;
            margin: 1rem -0.5rem 0.5rem -0.5rem;
        }}
        
        div#subtitles_box h2 {{
            font-size: 1.2rem;
            margin: 0 0 0.4rem 0;
            color: {text_color};
        }}
        @media screen and (max-width: 480px) {{
            div#subtitles_box h2 {{
                font-size: 1rem;
                margin: 0 0 0.4rem 0;
                color: {text_color};
            }}
        }}            
    </style>
    </head>
    <body>
        <div id="subtitles_box">
            <h2>{emoji} {title}</h2>
        </div>
    </body>
    """
    components.html(html_code, height=60)
        
def normal_quiz_link_button(url, mode):
    if mode == "dark":
        bg_color = "#0e1117"
        text_color = "#ddd"
        button_bg = "#2e8b57"
        button_hover = "#3cb371"
        caption_color = "#aaa"
    else:  # light mode
        bg_color = "#e6ffe6"
        text_color = "#444"
        button_bg = "#32CD32"
        button_hover = "#228B22"
        caption_color = "#444"

    full_html = f"""
    <html>
    <head>
    <link href="https://fonts.googleapis.com/css2?family=Source+Sans+Pro&display=swap" rel="stylesheet">
    <style>
    
    #quiz-link a {{
        font-family: 'Source Sans Pro', sans-serif;
        font-size: 1.1rem;
        font-weight: bold;
        color: white;
        background-color: {button_bg};
        padding: 0.65rem 1.25rem;
        border-radius: 8px;
        text-decoration: none;
        display: inline-block;
        transition: background-color 0.3s;
    }}
    #quiz-link a:hover {{
        background-color: {button_hover};
    }}
    </style>
    </head>
    <body>
    <div style="
        background-color: {bg_color};
        padding: 0.6rem 0.1rem;
        border-radius: 10px;
        text-align: center;
        margin: 0.5rem -0.5rem 1.5rem -0.5rem;
        color: {text_color};
        ">
        <div id="quiz-link" style="text-align: center; margin: 1rem 0;">
            <a href="{url}" target="_blank">
                ✅ Take the <u>{CURRENT_CLASS}</u> Quiz again!
            </a>
        </div>
        <p style="margin-top: 0.5rem; font-family: 'Source Sans Pro', sans-serif; font-size: 0.9rem; color: {caption_color};">
            See your score and track your progress 🚀
        </p>
    </div>
    </body>
    </html>
    """
    
    components.html(full_html, height=165)

def enhanced_quiz_link_button(url, mode):
    if mode == "dark":
        bg_color = "#0e1117"
        border_color = "#90ee90"
        box_shadow = "0px 5px 4px rgba(144, 238, 144, 0.2)"
        text_color = "#ddd"
        button_bg = "#2e8b57"
        button_hover = "#3cb371"
        caption_color = "#aaa"
    else:  # light mode
        bg_color = "#e6ffe6"
        border_color = "#32CD32"
        box_shadow = "0px 5px 4px rgba(50, 205, 50, 0.2)"
        text_color = "#444"
        button_bg = "#32CD32"
        button_hover = "#228B22"
        caption_color = "#444"

    full_html = f"""
    <html>
    <head>
        <link href="https://fonts.googleapis.com/css2?family=Source+Sans+Pro&display=swap" rel="stylesheet">
    <style>
    
    #quiz-link a {{
        font-family: 'Source Sans Pro', sans-serif;
        font-size: 1.1rem;
        font-weight: bold;
        color: white;
        background-color: {button_bg};
        padding: 0.65rem 1.25rem;
        border-radius: 8px;
        text-decoration: none;
        display: inline-block;
        transition: background-color 0.3s;
    }}
    #quiz-link a:hover {{
        background-color: {button_hover};
    }}
    </style>
    </head>
    <body>
    <div style="
        background-color: {bg_color};
        padding: 1rem 0.25rem;
        border-radius: 10px;
        border: 2px solid {border_color};
        text-align: center;
        margin: 0.5rem -0.5rem 1.5rem -0.5rem;
        box-shadow: {box_shadow};
        color: {text_color};
        ">
        <div id="quiz-link" style="text-align: center; margin: 1rem 0;">
            <a href="{url}" target="_blank">
                ✅ Take the <u>{CURRENT_CLASS}</u> Quiz Now!
            </a>
        </div>
        <p style="margin-top: 0.5rem; font-family: 'Source Sans Pro', sans-serif; font-size: 0.9rem; color: {caption_color};">
            See your score and track your progress 🚀
        </p>
    </div>
    </body>
    </html>
    """
    
    components.html(full_html, height=165)

@st.cache_data
def load_css(mode):
    if mode == "dark":
        with open("assets/dark-style.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    else:
        with open("assets/light-style.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

def final_form_popup(url, mode):
    if mode == "dark":
        box_bg = "#262730"
        border_color = "#90ee90"
        text_color = "#ddd"
        caption_color = "#aaa"
        button_bg = "#2e8b57"
        button_hover = "#3cb371"
    else:
        box_bg = "#f0f2f6"
        border_color = "#32CD32"
        text_color = "#333"
        caption_color = "#555"
        button_bg = "#32CD32"
        button_hover = "#228B22"

    full_html = f"""
    <html>
    <head>
        <link href="https://fonts.googleapis.com/css2?family=Source+Sans+Pro&display=swap" rel="stylesheet">
        <style>
        
        #popup-link a {{
            background-color: {button_bg};
            color: white;
            padding: 0.65rem 1.5rem;
            border-radius: 8px;
            font-weight: bold;
            text-decoration: none;
            font-size: 1.05rem;
            display: inline-block;
            transition: background-color 0.3s ease;
        }}
        #popup-link a:hover {{
            background-color: {button_hover};
        }}
        </style>
    </head>
    <body>
    <div style="
        background-color: {box_bg};
        padding: 1rem;
        border-radius: 12px;
        border: 2px solid {border_color};
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
        color: {text_color};
        margin-top: 3em;
        ">
        <p style="font-size: 1.05rem; font-family: 'Source Sans Pro', sans-serif; line-height: 1.6;">
            🙏 <strong>We'd love your feedback!</strong> If you've explored the bot enough, please take a moment to fill out our quick feedback form. 
            Your opinion helps us make the experience even better!
        </p>
        <div id="popup-link" style="text-align: center; margin: 1rem 0; font-family: 'Source Sans Pro', sans-serif;">
            <a href="{url}" target="_blank">
                ✍️ Fill the Final Feedback Form
            </a>
        </div>
        <p style="font-size: 0.9rem; color: {caption_color}; text-align: center; font-family: 'Source Sans Pro', sans-serif;">
            Need more time? Just close this popup and come back later 💬
        </p>
    </div>
    </body>
    </html>
    """

    components.html(full_html, height=280)
   
def is_authorized(user_email):
    user = fetch_user(user_email)
    if not user:
        #st.info("❌ User not found.")
        return False
    if user.get("is_verified") == "False":
        #st.info("❌ User not verified.")
        return False
    else:
        #st.info("✅ User verified.")
        return True
    
def is_teacher_approved(user_email):
    user = fetch_user(user_email)
    if not user:
        #st.info("❌ User not found.")
        return False
    if user.get("role") == "Teacher":
        teacher = fetch_teacher(user_email)
        if teacher.get("is_approved") != "Approved":
            #st.info("❌ Teacher not approved.")   
            return False
        else:
            #st.info("✅ Teacher approved.")
            return True
    else:
        #st.info("❌ User is not a teacher.")
        return False

def get_user_role(user_email):
    user = fetch_user(user_email)
    if user:
        return user.get("role")
    return None

def is_valid_email(email):
    if not email:
        return False
    pattern = r'^[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_strong_password(password):
    pattern = r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)[A-Za-z\d@$!%*?&#^_\-+=~.,:;|<>/\\()]{8,}$'
    return re.match(pattern, password) is not None

@st.cache_data
def load_chat_history(user_email):
    history = fetch_message_history(user_email)
    if not history:
        st.info("No chat history found for this user.")
        return []

    messages = []
    for entry in history:
        messages.append({"role": "user", "content": entry.get("question")})
        messages.append({"role": "assistant", "content": entry.get("response")})

    return messages  # Return structured messages

def is_valid_up(up):
    # up must be a number
    return up.isdigit()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def display_message_separator():
    # Get current UTC time
    current_date = datetime.now(timezone.utc) # + timedelta(hours=1)

    # Format to string for display
    current_date_str = current_date.strftime("%Y-%m-%d %H:%M:%S")

    st.markdown(
        f"""
        <div style='border-top: 2px solid #4CAF50; margin-top: 20px; margin-bottom: 10px;'></div>
        <div style='text-align: center; font-size: 14px; color: #4CAF50; margin-bottom: 20px;'>
            📅 New Messages - {current_date_str}
        </div>
        """,
        unsafe_allow_html=True
    )

def send_message(user_input, user_email, selected_class_name=None, selected_class_number=None, selected_group=None, teacher_question=None):      
    
    user = fetch_user(user_email)
    username = user.get("name").split()[0] # Get the first name
    url = "http://rasa:5005/webhooks/rest/webhook"
    current_time = datetime.now(timezone.utc).isoformat() #datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "sender": user_email,
        "message": user_input,
        "metadata": {"username": username,"input_time":current_time, "selected_class_name": selected_class_name, "selected_class_number": selected_class_number, "selected_group":selected_group, "teacher_question": teacher_question}
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        response.raise_for_status()
        messages = response.json()

        bot_reply = ""
        buttons = []

        for message in messages:
            if "text" in message:
                bot_reply += f"\n\n {message['text']}"
            if "buttons" in message:
                buttons = message["buttons"]

        return bot_reply.strip(), buttons  # Return both text and buttons

    except requests.RequestException as e:
        st.error(f"⚠️ Error connecting to Rasa: {e}")
        return None
    
def show_license_terms():
    st.markdown("---")
    st.markdown("Please review and agree to the license terms before proceeding.")
    
    with st.expander("📄 See License Terms"):
        st.markdown(f"""
        ### Terms and Conditions

        Welcome to our AI-based tutoring system. By using this platform, you agree to the following terms:

        **1. Use of the Platform**  
        - For educational use by students, educators, and researchers only.  
        - Provide accurate information during registration.  
        - Misuse (e.g., offensive language) may lead to suspension.

        **2. Data Collection**  
        - We collect your name, email, UP number, course, chat messages, and progress.  
        - This data is used to personalize your experience and improve the system.

        **3. Data Privacy**  
        - Your data is securely stored and never shared with third parties.  
        - You can request access or deletion of your data at any time.

        **4. Intellectual Property**  
        - All content and software belong to the system developers.  
        - Unauthorized reuse or redistribution is prohibited.

        **5. Accuracy of Information**  
        - The tutoring system uses artificial intelligence to provide responses.  
        - While we strive for accuracy, the information provided by the bot may be incorrect, incomplete, or outdated.  
        - You are responsible for verifying any critical information through official course materials or instructors.

        **6. Account Termination**  
        - We reserve the right to remove accounts that abuse the platform or break the rules.

        **7. Agreement**  
        - By using this platform, you confirm that you accept these terms.

        **8. Contact**  
        - Reach out to us at [{ADMIN_EMAIL}](mailto:{ADMIN_EMAIL}) for any questions or concerns.
        """)

    # Checkbox for agreement
    agree = st.checkbox("I have read and agree to the License Terms")
    
    return agree

def download_pdfs(mode):
    # Path to your PDF materials folder
    pdf_folder = f"materials/{CURRENT_CLASS}"

    # Get all PDF filenames from the folder
    available_pdfs = [f for f in os.listdir(pdf_folder) if f.endswith(".pdf") and not f.startswith("BOOK_")]
    # remove 'EDITED_' from the beginning of the pdf name if needed
    available_pdfs = [f.replace("EDITED_", "") for f in available_pdfs]

    #st.sidebar.markdown("### 📚 Download Course Materials")
    styled_subheader("Download Course Materials", "📚", mode)
    
    # Multi-select for choosing PDFs
    selected_pdfs = st.sidebar.multiselect(
        "Select PDFs to download:",
        options=available_pdfs,
        default=[],
        help="**Note**: Although the books are used to generate the content of the answers, they are **not available** for download."
    )

    # If at least one file is selected, offer a ZIP download
    if selected_pdfs:
        # Create in-memory zip
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
            for pdf_name in selected_pdfs:
                pdf_path = os.path.join(pdf_folder, pdf_name)
                zip_file.write(pdf_path, arcname=pdf_name)
        zip_buffer.seek(0)

        st.sidebar.download_button(
            label="📦 Download Selected PDFs as ZIP",
            data=zip_buffer,
            file_name="selected_pdfs.zip",
            mime="application/zip"
        )
        
def register_student_form(up=None):
    if not up:
        up = st.text_input("🎓 University ID", placeholder="2020XXXXX", key="register_up_id")
    else:
        st.write("🎓 University ID: ", up)
    year = st.number_input("📅 Year", min_value=1, max_value=5, step=1, key="register_year")
    course = st.selectbox("📚 Course", COURSES, key="register_course")
    #if course == "Other":
    #    course = st.text_input("Specify the course:", key="register_course_other")

    # Get classes from Flask API
    available_classes = fetch_classes()
    df_classes = pd.DataFrame(available_classes)
    # filter classes by code (equal to CURRENT_CLASS)
    df_classes = df_classes[df_classes["code"] == CURRENT_CLASS]

    # Create class code-number pairs
    df_classes["class_identifier"] = df_classes["code"] + "-" + df_classes["number"]
    class_identifiers = df_classes["class_identifier"].unique()
    # add an option of no class
    class_identifiers = ["No Class"] + list(class_identifiers)
    selected_class_identifier = st.selectbox("📖 Select Class", class_identifiers, key="register_classes")
    
    # add option to choose group (G1, G2, G3, G4)
    # get available groups for the selected class code
    selected_group = "No Group"
    if selected_class_identifier != "No Class":
        selected_class_row = df_classes[df_classes["class_identifier"] == selected_class_identifier]
        if selected_class_row["group"].iloc[0] != None:
            groups = list(selected_class_row["group"])
            class_groups = pd.DataFrame(groups, columns=["group"])            
            selected_group = st.selectbox("🗂️ Select Group", class_groups, key="register_group", help="Select your working group")
            
    # get id of selected class
    selected_class_id = None
    if selected_class_identifier != "No Class":
        selected_class_rows = df_classes[df_classes["class_identifier"] == selected_class_identifier]
        if selected_group == "No Group":
            selected_class_id = str(selected_class_rows["id"].iloc[0])
        else:
            selected_class_row = selected_class_rows[selected_class_rows["group"] == selected_group]
            if not selected_class_row.empty:
                selected_class_id = str(selected_class_row["id"].iloc[0])
    
    return up, year, course, selected_class_id

def register_teacher_form():
    st.warning("**Note**: As you are attempting to register as a teacher, your request will be sent to the admin for approval. You will be notified once approved.")
    
    available_classes = fetch_classes()  # Get classes from Flask API
    df_classes = pd.DataFrame(available_classes, columns=["id", "code", "number", "group", "course"])
    # filter classes by code (equal to CURRENT_CLASS)
    df_classes = df_classes[df_classes["code"] == CURRENT_CLASS]
    
    # Create a unique identifier for each class by concatenating code and number
    df_classes["class_identifier"] = df_classes["code"] + "-" + df_classes["number"]
    class_identifiers_list = df_classes["class_identifier"].tolist()
    class_identifiers_list = list(set(class_identifiers_list))  # Remove duplicates
    # order by class identifier
    class_identifiers_list.sort()
    
    selected_class_codes = st.multiselect("📖 Select Classes", class_identifiers_list, key="register_classes", help="Once approved, you will have full access to the selected classes.")

    # get ids of selected classes
    selected_class_ids = []
    for class_identifier in selected_class_codes:
        class_rows = df_classes[df_classes["class_identifier"] == class_identifier]
        for index, row in class_rows.iterrows():
            selected_class_ids.append(str(row["id"]))
    
    return selected_class_ids


def register_other_form():
    
    role = st.radio("Are you...", ["🧑‍💼 Old Student/Worker", "🧑‍🔬 Researcher"], key="register_course")
    if role == "🧑‍💼 Old Student/Worker":
        role = "Worker"
    else:
        role = "Researcher"
    
    job = st.text_input("Current role or job title", key="register_job")  
    company = st.text_input("🏢 Affiliated organization or company", key="register_organization")
    graduation_year = st.number_input("📅 Graduation Year", min_value=1980, max_value=2025, step=1, key="register_graduation_year")
    graduation_area = st.text_input("🏫 Graduation Area", key="register_graduation_area",  help="Enter your field of graduation, e.g., Computer Science, Mechanical Engineering, etc.")   
                  
    return role, job, company, graduation_year, graduation_area  

def initial_role_selection():
    # Role selection
    option_map = {
        0: "🧑‍🎓 Student",
        1: "👨🏻‍🏫 Teacher",
        2: "🧑‍🔬 Other"
    }
    selection = st.pills(
        "Chose your Role:",
        options=option_map.keys(),
        format_func=lambda option: option_map[option],
        selection_mode="single",
        default=0,
    )
    if selection == 0:
        role = "Student"
    elif selection == 1:
        role = "Teacher"
    else:
        role = "Other"
        
    return role

def is_uporto_email(email):
    # Check if the email domain is "uporto.pt"
    if email.endswith("@g.uporto.pt") or email.endswith("@fe.up.pt"):
        return True
    else:
        #st.error("❌ Invalid email domain. Please use your UPorto email.")
        return False
    
def user_filled_the_form(user_email, spreadsheet_id, update_db=False):
    user = fetch_user(user_email)
    if not user:
        #st.error("❌ User not found.")
        return False
    if update_db and user.get("form_filled") == "True":
        #st.info("✅ User has already filled the form.")
        return True
    else:
        response = cached_user_form_status(user_email, spreadsheet_id)
        if response:
            #st.info("✅ User has filled the form.")
            return True
        else:
            #st.error("❌ User has not filled the form.")
            return False
        
@st.cache_data
def cached_user_form_status(user_email, spreadsheet_id):
    return has_filled_form(user_email, spreadsheet_id, update_db=False).get("filled")
        
def display_past_questions(df_filtered, mode):
    # Display Interaction History
    #st.subheader("🧠 Revisit Your Past Questions")
    styled_subheader("Revisit Past Questions", "🧠", mode)
    question_list = df_filtered["question"].tolist()
    #question_list.insert(0, "> Chose a past question to review")
    selected = st.selectbox(placeholder="Chose a past question to review", label=" ", label_visibility="collapsed", options=question_list, key="selected_question")

    # Get response if a selection exists
    if selected:
        st.divider()
        match = df_filtered[df_filtered["question"] == selected].iloc[0]
        st.subheader(f"**📥 Date:** {match['date']}")
        #st.markdown(f"**🕒 Date:** {match['date']}")
        #st.markdown(f"**🙋 Question:** {match['question']}")
        #st.markdown(f"**🤖 Bot Response:** {match['response']}")
        st.markdown(match['response'])

def generate_reset_token(email):
    token = secrets.token_urlsafe(32)
    save_reset_token(email, token)
