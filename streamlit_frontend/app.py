from urllib.parse import unquote
import streamlit as st
st.set_page_config("EngiBot", '🤖', layout="centered", initial_sidebar_state="expanded")

from streamlit_scroll_to_top import scroll_to_here
import pandas as pd
from streamlit_cookies_manager import EncryptedCookieManager
import os
import plotly.graph_objects as go
from streamlit_theme import st_theme
import plotly.express as px

from streamlit_frontend.utils import *

st.markdown("""
    <style>
        /* Target the CookieManager container by class and force it to take no space */
        .st-key-CookieManager-sync_cookies {
            display: none !important;
            height: 0 !important;
            width: 0 !important;
            overflow: hidden !important;
            padding: 0 !important;
            margin: 0 !important;
        }
        
        /* Adjust the main block container padding for larger screens */
        .stMainBlockContainer {
            padding: 2rem 1rem 2rem 1rem !important;
        }
        
        /* When the sidebar is open, limit its width */
        section[data-testid="stSidebar"][aria-expanded="true"] {
            min-width: 350px;
            max-width: 450px;
            width: 350px;
        }
        
    </style>
""", unsafe_allow_html=True)

st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Source+Sans+Pro&display=swap" rel="stylesheet">
<style>
/* Fix font for Streamlit text elements to support emoji */
body, div, p, span, label, section {
    font-family: "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", "Source Sans Pro" ,"sans-serif";
}
</style>
""", unsafe_allow_html=True)

# Generate a strong secret key for your application
SECRET_KEY = str(os.getenv("COOKIES_SECRET_KEY"))

FORM_URL = os.getenv("FORM_URL")
FINAL_FORM_URL = os.getenv("FINAL_FORM_URL")
QUIZ_URL = os.getenv("QUIZ_URL")
TEACHER_FINAL_SPREADSHEET_ID = os.getenv("TEACHER_FINAL_SPREADSHEET_ID")
TEACHER_FINAL_FORM_URL = os.getenv("TEACHER_FINAL_FORM_URL")
IS_PRODUCTION = os.getenv("IS_PRODUCTION")

if IS_PRODUCTION == "True":
    IS_PRODUCTION = True
else:
    IS_PRODUCTION = False

# Ensure SECRET_KEY is not None
if not SECRET_KEY:
    st.error("ERROR: COOKIES_SECRET_KEY is not set! Please configure your environment.")
    st.stop()  # Stop execution to prevent further errors
    
def set_cookie(key, value):
    cookies[key] = value

#@st.cache_resource
def get_cookie_manager():
    return EncryptedCookieManager(prefix="chatbot_app_", password=SECRET_KEY)

cookies = get_cookie_manager()

# Wait until cookies are ready
if not cookies.ready():
    st.warning("Initializing session... Please wait.")
    st.stop()  # Stop execution until cookies are available

# Load CSS for styling
COLOR_MODE = "dark"  # Default color mode
theme = st_theme()
if theme:
    COLOR_MODE = theme.get("base")
    load_css(COLOR_MODE)    

# google login
if st.user.is_logged_in:
    email = st.user.email
    st.session_state["user_email"] = email
    st.session_state["is_logged_in"] = True
    
    # check if user is registed in db
    if fetch_user(email):
        st.session_state["is_user_registed"] = True
    else:
        st.session_state["is_user_registed"] = False
    
    if user_filled_the_form(email, INITIAL_SPREADSHEET_ID, True):
        st.session_state["filled_the_form"] = True
    if user_filled_the_form(email, FINAL_SPREADSHEET_ID):
        st.session_state["filled_final_form"] = True
    if user_filled_the_form(email, TEACHER_FINAL_SPREADSHEET_ID):
        st.session_state["filled_final_teacher_form"] = True

# normal login - Restore login state from cookies
elif cookies.get("user_email") != "" and cookies.get("user_email") != None:
    st.session_state["user_email"] = cookies.get("user_email")
    st.session_state["is_user_registed"] = True  
    
    if user_filled_the_form(st.session_state["user_email"], INITIAL_SPREADSHEET_ID, True):
        st.session_state["filled_the_form"] = True
    if user_filled_the_form(st.session_state["user_email"], FINAL_SPREADSHEET_ID):
        st.session_state["filled_final_form"] = True
    if user_filled_the_form(st.session_state["user_email"], TEACHER_FINAL_SPREADSHEET_ID):
        st.session_state["filled_final_teacher_form"] = True
else:
    st.session_state["user_email"] = None
    
if "reset_password" not in cookies or cookies.get("reset_password") == "False":
    st.session_state["reset_password"] = False
    if "set_new_password" not in cookies or cookies.get("set_new_password") == "False":
        st.session_state["set_new_password"] = False
    
if cookies.get("reset_password") == "True":
    st.session_state["reset_password"] = True
    st.session_state["user_email"] = cookies.get("user_email")
    st.session_state["is_user_registed"] = False  
if cookies.get("set_new_password") == "True":
    st.session_state["set_new_password"] = True 
    
# Check login state
if st.session_state["user_email"] is None:
    st.session_state["is_logged_in"] = False
else:
    st.session_state["is_logged_in"] = True
    
#if "scroll_down" not in st.session_state:
st.session_state["scroll_down"] = True

st.session_state["display_message_separator"] = cookies.get("display_message_separator") == "True"
st.session_state["show_popup"] = cookies.get("show_popup") == "True"


if "input_disabled" not in st.session_state:
    st.session_state.input_disabled = "False"

if "messages" not in st.session_state:
    st.session_state["messages"] = []


# Streamlit UI
def main():
        
    # Sidebar for logout
    with st.sidebar:
        st.title(f"EngiBot for *{CURRENT_CLASS}*")
        
        # user is registed in db
        if st.session_state["is_logged_in"] and is_authorized(st.session_state["user_email"]):
            user_email = st.session_state["user_email"]
            role = get_user_role(user_email)
            user=fetch_user(user_email)
            if user:
                if role == "Teacher":
                    if not is_teacher_approved(user_email):
                        st.info("You need to log in to access the chatbot.")
                    else:
                        username = user.get('name')
                        first_name = username.split()[0]
                        #st.write(f"Hello Professor **{user.get('name')}**!")
                        with st.expander(f"Hello **Professor {first_name}**! 👋"):
                            st.markdown(f"""
                            <div style="font-size: 1rem; line-height: 1.6;">
                                <strong>Welcome to EngiBot — Instructor Mode 🎓</strong>
                                <br><br>
                                This interface provides insights into how students interact with the system and enables you to review AI-assisted learning processes.
                                <br><br>
                                Use this space to monitor student questions, track engagement, and gain insights into their learning patterns.
                                <br><br>
                            </div>
                            """, unsafe_allow_html=True)
                        
                        if not st.session_state.get("filled_final_form", False) and not st.session_state["show_popup"]:
                            st.link_button("📝 Fill the Final Feedback Form", TEACHER_FINAL_FORM_URL, use_container_width=True)
                        
                        _, col2, _ = st.columns([1, 2, 1])
                        with col2:
                            st.markdown('<span id="button-after-red"></span>', unsafe_allow_html=True)
                            if st.button("Logout", use_container_width=True):
                                logout()
                        st.divider()
                        set_teacher_insights(user_email) 
                    
                else:
                    # check if user has filled the initial form
                    if not st.session_state.get("filled_the_form", False):
                        st.info("⚠️ You need to fill the initial form to access the chatbot.")
                    else:
                        username = user.get('name')
                        first_name = username.split()[0]
                        with st.expander(f"Hi **{first_name}**, welcome to **EngiBot!** 🤖"):
                            st.markdown(f"""
                            <div style="font-size: 1rem; line-height: 1.6;">
                                Your <strong>AI-powered tutoring assistant</strong> for <em>engineering topics</em>.
                                <br><br>
                                Ask questions, explore concepts, or get help with class materials — <strong>EngiBot</strong> is here to support your learning with <em>tailored explanations</em> and <em>relevant resources</em>.
                                <br><br>
                            </div>
                            """, unsafe_allow_html=True)

                        
                        #st.markdown(f"👉 [**Click to open {CURRENT_CLASS} Quiz!**]({QUIZ_URL})")
                        if user_filled_the_form(user_email, QUIZ_SPREADSHEET_ID):
                            normal_quiz_link_button(QUIZ_URL, COLOR_MODE)
                            if not st.session_state.get("filled_final_form", False) and not st.session_state["show_popup"]:
                                st.link_button("📝 Fill the Final Feedback Form", FINAL_FORM_URL, use_container_width=True)
                                
                        else:
                            enhanced_quiz_link_button(QUIZ_URL, COLOR_MODE)
                        
                        _, col2, _ = st.columns([1, 2, 1])
                        with col2:
                            st.markdown('<span id="button-after-red"></span>', unsafe_allow_html=True)
                            if st.button("Logout", use_container_width=True):
                                logout()
                            
                        if is_uporto_email(user_email):                        
                            if role == "Student":
                                # check if is enrolled in a class
                                student = fetch_student(user_email)
                                student_class = student.get("class_id")

                                if student_class == None:
                                    st.divider()
                                    download_pdfs(COLOR_MODE)
                            else:
                                st.divider()
                                download_pdfs(COLOR_MODE)                              
                        
                        st.divider()
                        set_student_insights(user_email)
                    
        else:
            st.info("You need to log in to access the chatbot.")
            if not st.session_state.get("is_user_registed", False) and st.user.is_logged_in:
                st.markdown('<span id="button-after-red"></span>', unsafe_allow_html=True)
                if st.button("Cancel"):
                    logout()
            
        
            
    if st.session_state["is_logged_in"]:
        user_email = st.session_state["user_email"] 
        
        # check if user is verified         
        if is_authorized(user_email):
                
            role = get_user_role(user_email)
            # check if the student filled the form
            if role != "Teacher":
                
                if not st.session_state.get("filled_the_form", False):   
                    show_initial_form_prompt(FORM_URL, COLOR_MODE)
                    st.write()
                    col1, _, col3 = st.columns([2, 3, 1])
                    with col1:
                        st.markdown('<span id="button-after-green"></span>', unsafe_allow_html=True)
                        if st.button("✅ I've submitted the form"):
                            st.rerun()
                    with col3:
                        st.markdown('<span id="button-after-red"></span>', unsafe_allow_html=True)
                        st.button("Go Back", on_click=logout, use_container_width=True)
                    return

                elif not st.session_state.get("filled_final_form", False) and st.session_state["show_popup"]:
                    #st.info("final form prob!")      
                    final_form_popup(FINAL_FORM_URL, COLOR_MODE)
                    _, _, col3 = st.columns([2, 2, 1])
                    with col3:
                        if st.button("❌ Close", use_container_width=True):
                            set_cookie("show_popup", "False")  # Hide the popup
                            cookies.save()
                            st.rerun()
                            #sleep(1)
                else:
                    chat_interface()           
                        
                
            elif role == "Teacher":
                # check if teacher is approved
                if not is_teacher_approved(user_email):
                    st.warning("As you attempt to register as a teacher, your account is pending approval. Please check back later.")
                
                    col1, col2, col3 = st.columns([2, 2, 1])
                    with col1:
                        st.markdown('<span id="button-after-basic"></span>', unsafe_allow_html=True)
                        if st.button("🔄 Check account status"):
                            st.rerun()
                    with col2:
                        pass
                    with col3:
                        st.markdown('<span id="button-after-red"></span>', unsafe_allow_html=True)
                        st.button("Go Back", on_click=logout, use_container_width=True)
                    return
                
                elif not st.session_state.get("filled_final_teacher_form", False) and st.session_state["show_popup"]:
                    final_form_popup(TEACHER_FINAL_FORM_URL, COLOR_MODE)   
                    _, _, col3 = st.columns([2, 2, 1])
                    with col3:  
                        if st.button("❌ Close", use_container_width=True):
                            set_cookie("show_popup", "False")  # Hide the popup
                            cookies.save()
                            #sleep(1)
                else:
                    chat_interface()
            
        else:            
            if not st.session_state["is_user_registed"]:
                complete_registration() 
            else: # check if user is verified
                with st.container():
                    # Email verification
                    st.header("🔐 Email Verification")
                    st.write(f"We've sent a verification code to {user_email}")

                    with st.form("email_verification_form"):
                        verification_code = st.text_input("📨 Enter the 6-digit code:", key="verification_code", max_chars=6)
                        
                        col1, _, col3 = st.columns([1, 3, 1])
                        with col1:
                            st.markdown('<span id="button-after-green"></span>', unsafe_allow_html=True)  
                            verify_clicked = st.form_submit_button("✅ Verify", use_container_width=True)
                        with col3:
                            st.markdown('<span id="button-after-red"></span>', unsafe_allow_html=True)
                            cancel_clicked = st.form_submit_button("Cancel", use_container_width=True)

                    show_error = False
                    error = ""
                    
                    if verify_clicked:
                        if verify_user(user_email, verification_code):
                            #st.success("✅ Email verified successfully!")
                            if user_filled_the_form(user_email, INITIAL_SPREADSHEET_ID, True):
                                st.session_state["filled_the_form"] = True
                            st.rerun()
                        else:
                            show_error = True
                            error = "❌ Invalid verification code. Please try again."
                    if cancel_clicked:
                        logout()
                    
                    if show_error:
                        st.error(error)
                    
                    # resend verification code
                    st.divider()
                    st.write("Didn't receive the code? Check your spam folder or click the button below to resend it.")
                    st.markdown('<span id="button-after-basic"></span>', unsafe_allow_html=True)
                    if st.button("📩 Resend Code"):
                        # send verification code to email
                        if not send_confirmation_email(user_email):
                            st.error("❌ Failed to resend verification code.")
                        else:
                            st.success("✅ Verification code resent successfully!")
                        #sleep(2)
                        #st.rerun()      
            
    else:
        auth_tabs()

def auth_tabs():
    st.title("🔑 Authentication")
    
    if st.session_state.get("reset_password"):
        if st.session_state.get("set_new_password", False):
            reset_password_form()
        else: 
            forgot_password_form()
    else:                
        tab1, tab2 = st.tabs(["Login", "Register"])
        with tab1:
            login_form()
            google_login()
        with tab2:
            register_form()
    
            
def google_login(): 
    #st.subheader("Login using g.uporto")
    st.subheader("Or Login using Google")
    col1, col2 = st.columns([1, 10])
    with col1:
        st.image("assets/google_icon.png", width=40)
    with col2:
        st.markdown('<span id="button-after-basic"></span>', unsafe_allow_html=True)
        st.button("Log in with Google", on_click=st.login)  

def chat_interface():
    st.title("💬 Chat with EngiBot")
    #display_bot_header(COLOR_MODE)
    # warn the users that it only works in english
    st.warning("This chatbot is currently only available in English. Please use English to interact with it.")
    user_role = get_user_role(st.session_state["user_email"])

    if user_role == "Teacher":

        teacher_classes = fetch_teacher_classes(st.session_state["user_email"])
        if not teacher_classes:
            st.info(f"No classes found for teacher.")
            return 
        df_classes = pd.DataFrame(teacher_classes, columns=["id", "code", "number", "group"])
        
        if df_classes.empty:
            st.info("No assigned classes found.")
            return
        
        # order by code and number
        df_classes = df_classes.sort_values(by=["code", "number"])

        # Create a unique identifier for each class by concatenating code and number
        df_classes["class_identifier"] = df_classes["code"] + "-" + df_classes["number"]
        df_classes = df_classes.sort_values(by=["class_identifier"])
        
        st.write("Here you can ask questions about your classes and get insights about your students' progress.")

        col1, col2 = st.columns([1, 1])
        with col1:
            # Sidebar: Select class
            selected_class_identifier = st.selectbox("📚 Select a Class", df_classes["class_identifier"].unique(), key="selected_class_identifier")
            
            # add a selectbox to select the class group given selected_class_identifier
            selected_class_row = df_classes[df_classes["class_identifier"] == selected_class_identifier]
            # Extract the selected class code and number
            selected_class_code = selected_class_row["code"].iloc[0]
            selected_class_number = selected_class_row["number"].iloc[0]
            
        with col2:
            class_groups_list = ["-"]
            # get all possible groups for the selected class
            if selected_class_row["group"].iloc[0] != None:
                groups = list(selected_class_row["group"])
                for group in groups:
                    class_groups_list.append(group)
            # create a class_groups df
            class_groups = pd.DataFrame(class_groups_list, columns=["group"])
            selected_class_group = st.selectbox("🗂️ Select a Group", class_groups, key="select_group")
            if selected_class_group == "-":
                selected_class_group = None        

        # Display insight buttons only if a class is selected
        if selected_class_identifier:

            # Populate buttons for insights
            if not st.session_state.get("buttons", False):
                _, buttons = send_message("buttons for insights", st.session_state["user_email"])
                st.session_state["buttons"] = buttons

            # Display buttons
            if st.session_state.get("buttons"):
                buttons = st.session_state["buttons"]
                # save buttons in session state
                cols = st.columns(len(buttons))
                for i, btn in enumerate(buttons):
                    if cols[i].button(btn["title"], use_container_width=True):
                        st.session_state["selected_button_payload"] = btn["payload"]
                        process_bot_response(btn["payload"], selected_class_code, selected_class_number, selected_class_group)
                        return
    
        if st.session_state["messages"]:
            if st.session_state["messages"].__len__() > 1:
                if st.session_state["messages"][-2]["role"] == "user":
                    with st.chat_message(st.session_state["messages"][-2]["role"]):
                        st.markdown(st.session_state["messages"][-2]["content"])
            with st.chat_message(st.session_state["messages"][-1]["role"]):
                st.markdown(st.session_state["messages"][-1]["content"])

        with st.empty():
            # add an input form to get the custom query from the teacher
            with st.form(key="custom_query_form", clear_on_submit=True):
                custom_teacher_query = st.text_input("Type your question:", key="custom_teacher_query")
                st.markdown('<span id="button-after-basic"></span>', unsafe_allow_html=True)
                submit_button = st.form_submit_button("Send")
            if submit_button and custom_teacher_query.strip():
                # Append user message to the chat
                st.session_state["messages"].append({"role": "user", "content": custom_teacher_query})
                process_bot_response("/custom_teacher_query", selected_class_code, selected_class_number, selected_class_group, custom_teacher_query)
                            
    else:
        # Load previous messages
        if st.session_state["messages"] == []:
            st.session_state["messages"] = load_chat_history(st.session_state["user_email"])

        for message in st.session_state["messages"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        
        # Display separator for new messages
        if st.session_state["display_message_separator"]:
            display_message_separator()  # Display a separator for new messages 
            response, _ = send_message("set username trigger", st.session_state["user_email"])
            
            if response:
                with st.chat_message("assistant"):
                    st.markdown(response)
            
        # Handle scrolling to the bottom
        if st.session_state.scroll_down:
            scroll_to_here(0, key='bottom')  # Smooth scroll to the bottom of the page
            st.session_state.scroll_down = False  # Reset the scroll state
            
        with st.empty():
            st.markdown(
                """
                <style>
                    div[data-testid="stForm"] {
                        margin-bottom: max(-20vh, -6em) !important;  /* Reduce bottom spacing */
                    }
                </style>
                """,
                unsafe_allow_html=True
            )
            # show input form
            with st.form(key="input_form", clear_on_submit=True):
                user_input = st.text_input("Type your message:", key="user_input")
                st.markdown('<span id="button-after-basic"></span>', unsafe_allow_html=True)
                submit_button = st.form_submit_button("Send")
            if submit_button and user_input.strip():
                set_cookie("display_message_separator", "False")  # Hide the separator
                cookies.save()
                # Append user message to the chat
                st.session_state["messages"].append({"role": "user", "content": user_input})
                #st.markdown(st.session_state["messages"][-1]["content"])
                # Process the user input and get the bot response
                process_bot_response(st.session_state["messages"][-1]["content"])
            

def process_bot_response(trigger, selected_class_name=None, selected_class_number=None, selected_group=None, teacher_question=None):
    user_email = st.session_state["user_email"]
    user_role = get_user_role(user_email)

    if user_role == "Teacher":
        if teacher_question == None:
            teacher_question = ""
        with st.status(f"🤖 ... {teacher_question}", expanded=True) as status:
            response, _ = send_message(trigger, user_email, selected_class_name, selected_class_number, selected_group, teacher_question)

            if response:
                st.session_state["messages"].append({"role": "assistant", "content": response})
                save_message_history(user_email, {"question": teacher_question, "response": response})
                
                with st.chat_message("assistant"):
                    st.markdown(response)
            else:
                error_message = "Sorry, I didn't understand that."
                st.session_state["messages"].append({"role": "assistant", "content": error_message})

                with st.chat_message("assistant"):
                    st.markdown(error_message)

        # clear the selected button payload
        st.session_state["teacher_message_sent"] = False  # Allow re-triggering
    else:
        with st.status(f"🤖 ... {trigger}", expanded=True) as status:
        #with st.spinner("Thinking... 🤖"):
            response, _ = send_message(trigger, user_email)

            if response:
                st.session_state["messages"].append({"role": "assistant", "content": response})
                save_message_history(user_email, {"question": trigger, "response": response})

                with st.chat_message("assistant"):
                    st.markdown(response)
            else:
                error_message = "Sorry, I didn't understand that."
                st.session_state["messages"].append({"role": "assistant", "content": error_message})

                with st.chat_message("assistant"):
                    st.markdown(error_message)

    # ✅ Reset `bot_thinking` so input appears again
    st.session_state["bot_thinking"] = False
    st.rerun()
    
def set_student_insights(student_email):
    # UI Layout
    student_progress = get_progress(student_email)
    if student_progress == {}:  # No progress found
        return
    df = pd.DataFrame(student_progress, columns=["question", "response", "topic_id", "pdfs", "timestamp"])

    if df.empty:
        #st.info("Interact with the bot to see your progress.")
        show_no_data_message(COLOR_MODE)
    else:
        #st.title("📊 Progress Dashboard")
        show_dashboard_title("Progress Dashboard", "View your progress so far and explore how to improve.", COLOR_MODE)

        # Convert timestamp to datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["date"] = df["timestamp"].dt.date

        # Sidebar Filters
        #st.sidebar.header("📅 Filter Data")
        #styled_subheader("Filter Data", "📅", COLOR_MODE)

        start_date = min(df["date"])
        end_date = max(df["date"])

        # Date range selector
        date_range = st.sidebar.date_input(
            "📅 Filter Data",
            (start_date, end_date),  # default range
            min_value=start_date,
            max_value=end_date,
            format="MM.DD.YYYY",
        )

        # Ensure the user selected a range (tuple with 2 dates)
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            df_filtered = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
        else:
            #st.sidebar.warning("Please select a valid start and end date.")
            df_filtered = df  # fallback to full data if range not selected

        # General Stats
        #styled_subheader("Overview", "📈", COLOR_MODE)
        
        # Calculate time window and previous period
        duration = end_date - start_date
        prev_start = start_date - duration
        prev_end = start_date - timedelta(days=1)
        df_prev = df[(df["date"] >= prev_start) & (df["date"] <= prev_end)]

        # Current values
        total_questions = len(df_filtered)
        active_days = df_filtered["date"].nunique()
        questions_per_day = total_questions / active_days if active_days else 0

        # Previous values
        prev_total_questions = len(df_prev)
        prev_active_days = df_prev["date"].nunique()
        prev_questions_per_day = (
            prev_total_questions / prev_active_days if prev_active_days else 0
        )

        # Display metrics
        col1, col2 = st.columns(2)
        col1.metric(
            "Total Questions",
            total_questions,
            percent_delta(total_questions, prev_total_questions),
            border=True,
        )
        col2.metric(
            "Active Days",
            active_days,
            percent_delta(active_days, prev_active_days),
            border=True,
        )
        #col3.metric(
        #    "Questions / Day",
        #    f"{questions_per_day:.1f}",
        #    percent_delta(questions_per_day, prev_questions_per_day),
        #    border=True,
        #)


        # Topic Frequency Analysis
        #st.subheader("📚 Most Discussed Topics")
        styled_subheader("Most Discussed Topics", "📚", COLOR_MODE)
        df_topics = get_topic_id_to_name_mapping()
        # make dict keys be integers
        df_topics = {int(k): v for k, v in df_topics.items()}
        # Map topic_id to topic names
        df_filtered["topic_name"] = df_filtered["topic_id"].map(df_topics).fillna("Unknown")
        # remove rows with topic_name "Unknown"
        df_filtered = df_filtered[df_filtered["topic_name"] != "Unknown"]
        
        # Convert topics to lowercase before counting
        topic_counts = df_filtered["topic_name"].value_counts().reset_index()
        topic_counts.columns = ["Topic", "Frequency"]
        # order by frequency
        topic_counts = topic_counts.sort_values(by="Frequency", ascending=False)
        top_topics = topic_counts.head(10)  # Limit to top 10 topics
        
        if top_topics.empty:
            st.info("No topics discussed in the selected date range.")
        else:
            top_topics = top_topics.sort_values("Frequency", ascending=True)
        
            #st.bar_chart(top_topics.set_index("Topic"))
            # Define colors based on mode
            bar_color = "#0068c9" if COLOR_MODE == "light" else "#84ccfc"
            bg_color = "#f0f2f6" if COLOR_MODE == "light" else "#262730"
            text_color = "#262730" if COLOR_MODE == "light" else "#f0f2f6"
            topic_color = "#0e1117" if COLOR_MODE == "light" else "#ffffff"
            grid_color = text_color

            # === Dynamic height based on number of bars ===
            num_bars = len(top_topics)
            bar_height = 32  # height per bar in pixels
            min_height = 200
            max_height = 450
            chart_height = min(max(num_bars * bar_height + 80, min_height), max_height)

            # Create Plotly bar chart
            fig = px.bar(
                top_topics,
                x="Frequency",
                y="Topic",
                orientation="h",
                title=None,
                color_discrete_sequence=[bar_color],
            )

            # Style the chart
            fig.update_layout(
                plot_bgcolor=bg_color,
                paper_bgcolor=bg_color,
                font=dict(family="Source Sans Pro", size=14, color=text_color),
                margin=dict(t=10, b=30, l=60, r=30),
                xaxis=dict(
                    gridcolor=grid_color,
                    showline=False,
                    dtick=1  # This forces ticks to appear at every integer
                ),
                yaxis=dict(
                    showgrid=False,
                    title=None,
                    tickfont=dict(
                        color=topic_color,
                        family="Source Sans Pro",  # Will render as bold if available
                        size=14,
                        weight="bold"
                    )
                ),
                height=chart_height,
            )

            # Hover and border cleanup
            fig.update_traces(
                marker_line_color='rgba(0,0,0,0)',
                hovertemplate="%{y}: %{x}<extra></extra>"
            )

            # Display
            st.plotly_chart(fig, use_container_width=True)


        # get user role
        user_role = get_user_role(student_email)
        if user_role != "Teacher" and is_uporto_email(student_email):
        
            # Reference Materials Usage
            #st.subheader("📄 Reference Material Usage")
            styled_subheader("Reference Material Usage", "📄", COLOR_MODE)
            # drop empty pdfs
            df_filtered_pdfs = df_filtered[df_filtered["pdfs"].apply(lambda x: bool(x) and x != "{}")]
            if not df_filtered_pdfs.empty:
                pdf_list = []
                for pdfs in df_filtered_pdfs["pdfs"].dropna():
                    for pdf in pdfs.split(","):
                        pdf_list.append(pdf.split(" (Pages")[0].strip())

                # count the frequency of each pdf
                pdf_counts = pd.Series(pdf_list).value_counts().reset_index()
                pdf_counts.columns = ["PDF Name", "Frequency"]

                # order by count
                pdf_counts = pdf_counts.sort_values(by="Frequency", ascending=True) 

                # display bar chart
                #st.bar_chart(pdf_counts.set_index("PDF Name"))
                # === Dynamic height based on number of bars ===
                num_bars = len(pdf_counts)
                bar_height = 32  # height per bar in pixels
                min_height = 200
                max_height = 450
                chart_height = min(max(num_bars * bar_height + 80, min_height), max_height)

                # Create Plotly bar chart
                fig = px.bar(
                    pdf_counts,
                    x="Frequency",
                    y="PDF Name",
                    orientation="h",
                    title=None,
                    color_discrete_sequence=[bar_color],
                )

                # Style the chart
                fig.update_layout(
                    plot_bgcolor=bg_color,
                    paper_bgcolor=bg_color,
                    font=dict(family="Source Sans Pro", size=14, color=text_color),
                    margin=dict(t=10, b=30, l=60, r=30),
                    xaxis=dict(
                        gridcolor=grid_color,
                        showline=False,
                        dtick=1  # This forces ticks to appear at every integer
                    ),
                    yaxis=dict(
                        showgrid=False,
                        title=None,
                        tickfont=dict(
                            color=topic_color,
                            family="Source Sans Pro",  # Will render as bold if available
                            size=14,
                            weight="bold"
                        )
                    ),
                    height=chart_height,
                )

                # Hover and border cleanup
                fig.update_traces(
                    marker_line_color='rgba(0,0,0,0)',
                    hovertemplate="%{y}: %{x}<extra></extra>"
                )

                # Display
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.write("No reference materials used.")
            
            # Engagement Over Time
            display_past_questions(df_filtered, COLOR_MODE)
            st.divider()
            
            #st.subheader("📝 Your Question History")
            styled_subheader("Your Question History", "📝", COLOR_MODE)
            st.dataframe(df_filtered[["date", "question", "pdfs"]].rename(columns={"date": "Date", "question": "Question", "pdfs": "Referenced PDFs"}))
        else:       
            display_past_questions(df_filtered, COLOR_MODE)
            
            #st.subheader("📝 Your Question History")
            #styled_subheader("Your Question History", "📝", COLOR_MODE)
            #st.dataframe(df_filtered[["date", "question"]].rename(columns={"date": "Date", "question": "Question"}))
            
def set_teacher_insights(user_email):
    #st.title("📊 Class Engagement Dashboard")
    show_dashboard_title("Class Engagement", "Explore how your students are interacting with the material.", COLOR_MODE)

    # Fetch teacher's classes
    teacher_classes = fetch_teacher_classes(user_email)
    if not teacher_classes:
        st.info(f"No classes found for teacher.")
        return 
    df_classes = pd.DataFrame(teacher_classes, columns=["id", "code", "number", "group"])
    
    # Create a unique identifier for each class by concatenating code and number
    df_classes["class_identifier"] = df_classes["code"] + "-" + df_classes["number"]    

    # Add -All only to classes with more than one unique number for the same code
    class_counts = df_classes.groupby("code")["number"].nunique().reset_index()
    class_counts.columns = ["code", "unique_numbers"]

    for i, row in class_counts.iterrows():
        if row["unique_numbers"] > 1:  # Only add -All for classes with more than one unique number
            new_row = pd.DataFrame({
                "class_identifier": [row["code"] + "-All"],
                "code": [row["code"]],
                "number": ["-1"]
            })
            df_classes = pd.concat([df_classes, new_row], ignore_index=True)
    
    df_classes = df_classes.sort_values(by=["class_identifier"])

    # Sidebar: Select class
    selected_class_identifier = st.selectbox("📚 Select a Class", df_classes["class_identifier"].unique(), key="selected_class", help="You will be able to see the progress of all the groups you manage.")
    selected_class_row = df_classes[df_classes["class_identifier"] == selected_class_identifier]
    # Extract the selected class code and number
    selected_class_code = selected_class_row["code"].iloc[0]
    selected_class_number = selected_class_row["number"].iloc[0]
    if selected_class_number == "-1":
        selected_class_number = None
    
    classes_ids = []
    if selected_class_code and selected_class_number:
        # get all classes ids by the code and number
        #st.info(f"🏷️ Class code: {selected_class_code} | Class number: {selected_class_number}")
        classes_ids = df_classes[(df_classes["code"] == selected_class_code) & (df_classes["number"] == selected_class_number)]["id"].tolist()
    elif selected_class_code:
        # get all classes ids by the code
        #st.info(f"🏷️ Class code: {selected_class_code}")
        classes_ids = df_classes[df_classes["code"] == selected_class_code]["id"].tolist()
        
    # drop nan values from classes_ids
    classes_ids = [int(x) for x in classes_ids if pd.notna(x)]
    #st.info(f"Classes IDs: {classes_ids}")

    progress = []
    for class_id in classes_ids:
        progress += fetch_class_progress(int(class_id))

    if progress:
        df = pd.DataFrame(progress, columns=["user_id", "question", "response", "topic_id", "pdfs", "timestamp"])
    else:
        st.info(f"No interactions found for this class.")
        return 
        # To show some data so the dashboard is not empty, we fetch all the progress from all the users:
        #st.info(f"No interactions found for this class. The insights will be collected from all the other users, despite not enrolled in this class.")
        #progress = fetch_progress()
        #df = pd.DataFrame(progress, columns=["user_id", "question", "response", "topic_id", "pdfs", "timestamp"])
        
    # Convert timestamp to datetime
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date

    # Sidebar Filters
    start_date = min(df["date"])
    end_date = max(df["date"])

    # Date range selector
    date_range = st.sidebar.date_input(
        "📅 Filter Data",
        (start_date, end_date),  # default range
        min_value=start_date,
        max_value=end_date,
        format="MM.DD.YYYY",
    )

    # Ensure the user selected a range (tuple with 2 dates)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        df_filtered = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
    else:
        #st.sidebar.warning("Please select a valid start and end date.")
        df_filtered = df  # fallback to full data if range not selected


    # General Stats
    # Calculate time window and previous period
    #styled_subheader("Overview", "📈", COLOR_MODE)
    duration = end_date - start_date
    prev_start = start_date - duration
    prev_end = start_date - timedelta(days=1)
    df_prev = df[(df["date"] >= prev_start) & (df["date"] <= prev_end)]

    # Current values
    total_questions = len(df_filtered)
    unique_students = df["user_id"].nunique()

    # Previous values
    prev_total_questions = len(df_prev)
    prev_unique_students = df_prev["user_id"].nunique()

    # Display metrics
    col1, col2 = st.columns(2)
    col1.metric(
        "Total Questions",
        total_questions,
        percent_delta(total_questions, prev_total_questions),
        border=True,
    )
    col2.metric(
        "Unique Students",
        unique_students,
        percent_delta(unique_students, prev_unique_students),
        border=True,
    )

    # Topic Frequency Analysis
    #st.subheader("📚 Most Discussed Topics")
    styled_subheader("Most Discussed Topics", "📚", COLOR_MODE)
    df_topics = get_topic_id_to_name_mapping()
    # make dict keys be integers
    df_topics = {int(k): v for k, v in df_topics.items()}
    # Map topic_id to topic names
    df_filtered["topic_name"] = df_filtered["topic_id"].map(df_topics).fillna("Unknown")
    
    # Convert topics to lowercase before counting
    topic_counts = df_filtered["topic_name"].value_counts().reset_index()
    topic_counts.columns = ["Topic", "Frequency"]
    # order by frequency
    topic_counts = topic_counts.sort_values(by="Frequency", ascending=False)
    top_topics = topic_counts.head(10)  # Limit to top 10 topics
    
    if top_topics.empty:
        st.info("No topics discussed in the selected date range.")
    else:
        
        top_topics = top_topics.sort_values("Frequency", ascending=True)
    
        #st.bar_chart(top_topics.set_index("Topic"))
        # Define colors based on mode
        bar_color = "#0068c9" if COLOR_MODE == "light" else "#84ccfc"
        bg_color = "#f0f2f6" if COLOR_MODE == "light" else "#262730"
        text_color = "#262730" if COLOR_MODE == "light" else "#f0f2f6"
        topic_color = "#0e1117" if COLOR_MODE == "light" else "#ffffff"
        grid_color = text_color

        # === Dynamic height based on number of bars ===
        num_bars = len(top_topics)
        bar_height = 32  # height per bar in pixels
        min_height = 200
        max_height = 450
        chart_height = min(max(num_bars * bar_height + 80, min_height), max_height)

        # Create Plotly bar chart
        fig = px.bar(
            top_topics,
            x="Frequency",
            y="Topic",
            orientation="h",
            title=None,
            color_discrete_sequence=[bar_color],
        )

        # Style the chart
        fig.update_layout(
            plot_bgcolor=bg_color,
            paper_bgcolor=bg_color,
            font=dict(family="Source Sans Pro", size=14, color=text_color),
            margin=dict(t=10, b=30, l=60, r=30),
            xaxis=dict(
                gridcolor=grid_color,
                showline=False,
                dtick=1  # This forces ticks to appear at every integer
            ),
            yaxis=dict(
                showgrid=False,
                title=None,
                tickfont=dict(
                    color=topic_color,
                    family="Source Sans Pro",  # Will render as bold if available
                    size=14,
                    weight="bold"
                )
            ),
            height=chart_height,
        )

        # Hover and border cleanup
        fig.update_traces(
            marker_line_color='rgba(0,0,0,0)',
            hovertemplate="%{y}: %{x}<extra></extra>"
        )

        # Display
        st.plotly_chart(fig, use_container_width=True)

    # Reference Materials Usage
    #st.subheader("📄 Reference Material Usage")
    styled_subheader("Reference Material Usage", "📄", COLOR_MODE)
    # drop empty pdfs
    df_filtered_pdfs = df_filtered[df_filtered["pdfs"].apply(lambda x: bool(x) and x != "{}")]
    if not df_filtered_pdfs.empty:
        pdf_list = []
        for pdfs in df_filtered_pdfs["pdfs"].dropna():
            for pdf in pdfs.split(","):
                pdf_list.append(pdf.split(" (Pages")[0].strip())

        # count the frequency of each pdf
        pdf_counts = pd.Series(pdf_list).value_counts().reset_index()
        pdf_counts.columns = ["PDF Name", "Frequency"]

        # order by count
        pdf_counts = pdf_counts.sort_values(by="Frequency", ascending=True) 

        # display bar chart
        #st.bar_chart(pdf_counts.set_index("PDF Name"))
        # === Dynamic height based on number of bars ===
        num_bars = len(pdf_counts)
        bar_height = 32  # height per bar in pixels
        min_height = 200
        max_height = 450
        chart_height = min(max(num_bars * bar_height + 80, min_height), max_height)

        # Create Plotly bar chart
        fig = px.bar(
            pdf_counts,
            x="Frequency",
            y="PDF Name",
            orientation="h",
            title=None,
            color_discrete_sequence=[bar_color],
        )

        # Style the chart
        fig.update_layout(
            plot_bgcolor=bg_color,
            paper_bgcolor=bg_color,
            font=dict(family="Source Sans Pro", size=14, color=text_color),
            margin=dict(t=10, b=30, l=60, r=30),
            xaxis=dict(
                gridcolor=grid_color,
                showline=False,
                dtick=1  # This forces ticks to appear at every integer
            ),
            yaxis=dict(
                showgrid=False,
                title=None,
                tickfont=dict(
                    color=topic_color,
                    family="Source Sans Pro",  # Will render as bold if available
                    size=14,
                    weight="bold"
                )
            ),
            height=chart_height,
        )

        # Hover and border cleanup
        fig.update_traces(
            marker_line_color='rgba(0,0,0,0)',
            hovertemplate="%{y}: %{x}<extra></extra>"
        )

        # Display
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("No reference materials used.")

    # Engagement Over Time
    #st.subheader("📅 Engagement Over Time")
    styled_subheader("Engagement Over Time", "📅", COLOR_MODE)
    # Prepare data
    daily_counts = df_filtered.groupby("date").size().reset_index(name="questions")

    # Create Plotly figure
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=daily_counts["date"],
        y=daily_counts["questions"],
        mode="lines+markers",
        line=dict(color="#1f77b4", width=2),
        marker=dict(size=6),
        name="Questions"
    ))

    # Update layout for better usability
    fig.update_layout(
        title="User Questions Over Time",
        xaxis_title="Date",
        yaxis_title="Number of Questions",
        template="plotly_white",
        hovermode="x unified",
        margin=dict(l=40, r=40, t=50, b=40),
        height=400,
        xaxis=dict(
            showgrid=True,
            tickformat="%b %d",  # format date ticks
            rangeslider=dict(visible=True),  # adds horizontal slider
            type="date"
        )
    )

    st.plotly_chart(fig, use_container_width=True)



def register_form():
    st.subheader("Create a New Account")

    # Role selection outside the form for immediate reactivity
    role = initial_role_selection()

    with st.form("register_form"):
        # Basic user details
        email = st.text_input("📧 Email", key="register_email")
        name = st.text_input("👤 Name", key="register_name")
        password = st.text_input("🔑 Password", type="password", key="register_password")
        confirm_password = st.text_input("🔑 Confirm Password", type="password", key="confirm_password")
        
        st.divider()

        # Conditional additional fields based on external role selection
        if role == "Student":
            st.info("If you are a student, please log in with your g.uporto account to access all features of the bot.")
            up, year, course, selected_class_id = register_student_form()
        elif role == "Teacher":
            selected_class_codes = register_teacher_form()        
        elif role == "Other":
            role2, field, graduation_year, graduation_institution, graduation_area = register_other_form()
        
        agree = show_license_terms()
        
        _, col2, _ = st.columns([2, 1, 2])
        with col2:
            st.markdown('<span id="button-after-green"></span>', unsafe_allow_html=True)
            register_clicked = st.form_submit_button("Register", use_container_width=True)

    # Validation and submission handling happens here outside the form context
    show_error = False
    error = ""

    if register_clicked:
        if not is_valid_email(email):
            show_error = True
            error = "❌ Invalid email format!"
        if IS_PRODUCTION:
            if not is_strong_password(password):
                show_error = True
                error = "❌ Password must be at least 8 characters long, contain uppercase and lowercase letters and digits."
        if role == "Student" and not is_valid_up(up):
            show_error = True
            error = "❌ Invalid University ID!"
        if password != confirm_password:
            show_error = True
            error = "❌ Passwords do not match!"
        if fetch_user(email):       
            show_error = True
            error = "❌ Email already registered! Try logging in." 
        if not agree:
            show_error = True
            error = "❌ You must accept the license terms to register."
        
        if not show_error:
            hashed_password = hash_password(password)
            if role == "Student":
                response = register_student(name, email, hashed_password, up, course, year, selected_class_id)
            elif role == "Teacher":
                selected_class_codes = ",".join(selected_class_codes)
                response = register_teacher(name, email, hashed_password, selected_class_codes)
            elif role == "Other":
                response = register_other(name, email, hashed_password, role2, field, graduation_year, graduation_institution, graduation_area)
            
            set_cookie("user_email", email)
            cookies.save()
            st.rerun()

    if show_error:
        st.error(error)


def complete_registration():
    st.subheader("Login with Your Google Account")
    
    # Role selection outside the form for immediate reactivity
    role = initial_role_selection()
    
    with st.form("complete_registration_form"):
        # Basic user details
        email = st.user.email
        name = st.user.name
        st.write("📧 Email: ", email)
        st.write("👤 Name: ", name)
        password = st.text_input("🔑 Password", type="password", key="register_password")
        confirm_password = st.text_input("🔑 Confirm Password", type="password", key="confirm_password")
        
        st.divider()

        # Additional fields based on role
        if role == "Student":
            st.info("If you are a student, please log in with your g.uporto account to access all features of the bot.")
            up, year, course, selected_class_id = register_student_form()
        elif role == "Teacher":
            selected_class_codes = register_teacher_form()        
        elif role == "Other":
            role2, job, company, graduation_year, graduation_area = register_other_form()
                
        agree = show_license_terms()
        
        _, col2, _ = st.columns([2, 1, 2])
        with col2:
            st.markdown('<span id="button-after-green"></span>', unsafe_allow_html=True)
            register_clicked = st.form_submit_button("Register", use_container_width=True)
    
    show_error = False
    error = ""
    
    
    if register_clicked:
        if not is_valid_email(email):
            show_error = True
            error = "❌ Invalid email format!"
        if IS_PRODUCTION:
            if not is_strong_password(password):
                show_error = True
                error = "❌ Password must be at least 8 characters long, contain uppercase and lowercase letters and digits."
        if role == "Student" and not is_valid_up(up):
            show_error = True
            error = "❌ Invalid University ID!"
        if password != confirm_password:
            show_error = True
            error = "❌ Passwords do not match!"
        if fetch_user(email):   
            show_error = True
            error = "❌ Email already registered! Try logging in."  
        if not agree:
            show_error = True
            error = "❌ You must accept the license terms to register."
            
        if not show_error:
            # Create new user
            hashed_password = hash_password(password)

            if role == "Student":
                response = register_student(name, email, hashed_password, up, course, year, selected_class_id)
            elif role == "Teacher":
                selected_class_codes = ",".join(selected_class_codes)
                response = register_teacher(name, email, hashed_password, selected_class_codes)
            elif role == "Other":
                response = register_other(name, email, hashed_password, role2, job, company, graduation_year, graduation_area)

            #st.info(response.get("message"))
            #st.toast(response.get("message"))
            #sleep(2)
            st.rerun()
    
    if show_error:
        st.error(error)
  
def login_form():
    st.subheader("Login to Your Account")
    with st.form("login_form"):
        email = st.text_input("📧 Email", key="login_email")
        password = st.text_input("🔒 Password", type="password", key="login_password")

        col1, _, _, _, _, col5 = st.columns([1, 1, 1, 1, 1, 2])

        with col1:
            st.markdown('<span id="button-after-green"></span>', unsafe_allow_html=True)
            login_clicked = st.form_submit_button("Login", use_container_width=True)
        with col5:
            st.markdown('<span id="button-after-link"></span>', unsafe_allow_html=True)
            forgot_clicked = st.form_submit_button("Forgot Password?", use_container_width=True, type="tertiary")
            
    perform_authentication = False
    show_error = False
    error = ""
    
    if login_clicked:
        if not is_valid_email(email):
            show_error = True
            error = "❌ Invalid email format!"
        else:
            perform_authentication = True

    if forgot_clicked:
        if not fetch_user(email):
            show_error = True
            error = "🚫 Email not found in the system. Enter a valid email."
        else:
            set_cookie("reset_password", "True")
            set_cookie("user_email", email)
            cookies.save()
            st.rerun()
    
    if perform_authentication:
        with st.spinner("🔄 Authenticating..."):
            hashed_password = hash_password(password)
            user = authenticate_user(email, hashed_password)
            if user:
                if not user["is_verified"]:
                    show_error = True
                    error = "📩 Please confirm your email before logging in!"
                else:                     
                    st.session_state["is_logged_in"] = True
                    set_cookie("user_email", email)  # Store email in cookies
                    cookies.save()
                    #sleep(1)
                    st.rerun()
            else:   
                show_error = True
                error = "❌ Invalid email or password!"    
    if show_error:
        st.error(error)
   
def forgot_password_form():
    st.subheader("Forgot Password?")
    email = st.session_state["user_email"]
    with st.form("forgot_password"):
        if email is None or email == "":
            email = st.text_input("📧 Enter your registered email", key="forgot_email")
        st.write(f"📧 Email: {email}")
        
        col1, _, col3 = st.columns([2, 3, 1])
        with col1:
            st.markdown('<span id="button-after-green"></span>', unsafe_allow_html=True)
            reset_clicked = st.form_submit_button("Send Reset Link", use_container_width=True)
        with col3:
            st.markdown('<span id="button-after-red"></span>', unsafe_allow_html=True)
            cancel_clicked = st.form_submit_button("Cancel", use_container_width=True)
                
    if reset_clicked:
        generate_reset_token(email)
        send_password_reset_email(email)
        #st.success("✅ Password reset link sent to your email.")
        set_cookie("set_new_password", "True")
        cookies.save()
        st.rerun()
    if cancel_clicked:
        set_cookie("reset_password", "False")
        set_cookie("user_email", "")
        cookies.save()
        st.rerun()
        
def reset_password_form():
    raw_token = st.query_params.get("token", None)
    if isinstance(raw_token, list):
        token = raw_token[0]
    else:
        token = raw_token

    if token:
        token = unquote(token)
    else:
        st.write("✅ Password reset link sent to your email. Please check your inbox.")
        st.info("🔗 If you did not receive the email, please check your spam folder.")
        _, col, _ = st.columns([2, 1, 2])
        with col:
            st.markdown('<span id="button-after-green"></span>', unsafe_allow_html=True)
            home = st.button("Go Home", use_container_width=True)
            if home:
                set_cookie("reset_password", "False")
                set_cookie("user_email", "")
                cookies.save()
                st.rerun()
        return
        
    #st.info(f"Token from URL: {token}")
    if not token:
        st.error("❌ Invalid reset link.")
        _, col, _ = st.columns([2, 1, 2])
        with col:
            st.markdown('<span id="button-after-red"></span>', unsafe_allow_html=True)
            cancel_clicked = st.button("Cancel", use_container_width=True)
            if cancel_clicked:
                set_cookie("reset_password", "False")
                set_cookie("user_email", "")
                cookies.save()
                st.rerun()
        return

    email = fetch_reset_token(token).get("email")
    #st.info(f"email from token: {email}")
    if not email:
        st.error("❌ Invalid or expired token.")
        _, col, _ = st.columns([2, 1, 2])
        with col:
            st.markdown('<span id="button-after-red"></span>', unsafe_allow_html=True)
            cancel_clicked = st.button("Cancel", use_container_width=True)
            if cancel_clicked:
                set_cookie("reset_password", "False")
                set_cookie("user_email", "")
                cookies.save()
                st.rerun()
        return

    st.subheader(f"Reset password for {email}")

    with st.form("reset_password_form"):
        password = st.text_input("🔑 New Password", type="password")
        confirm_password = st.text_input("🔑 Confirm Password", type="password")
        
        col1, _, col3 = st.columns([2, 3, 1])
        with col1:
            st.markdown('<span id="button-after-green"></span>', unsafe_allow_html=True)
            submit = st.form_submit_button("Reset Password", use_container_width=True)
        with col3:
            st.markdown('<span id="button-after-red"></span>', unsafe_allow_html=True)
            cancel_clicked = st.form_submit_button("Cancel", use_container_width=True)
                

    if submit:
        if password != confirm_password:
            st.error("❌ Passwords do not match!")
            return

        reset_password(email, password)  # your existing password update function
        delete_reset_token(token)  # invalidate the token after use
        st.success("✅ Password reset successful! You can now log in.")
        set_cookie("set_new_password", "False")
        set_cookie("reset_password", "False")
        set_cookie("user_email", "")
        cookies.save()
        st.query_params.clear()
        
        _, col, _ = st.columns([2, 1, 2])
        with col:
            st.markdown('<span id="button-after-green"></span>', unsafe_allow_html=True)
            login_clicked = st.button("Login Now", use_container_width=True)
            if login_clicked:
                #open new page with url just the base url without params
                st.experimental_set_query_params()
                st.markdown("""<a href="./" class="login-button">🔐 Login Now</a>""", unsafe_allow_html=True)
        
    if cancel_clicked:
        set_cookie("set_new_password", "False")
        set_cookie("reset_password", "False")
        set_cookie("user_email", "")
        cookies.save()
        st.rerun()

    
def logout():
    # Remove cookies first (safe)
    set_cookie("user_email", "")
    set_cookie("display_message_separator", "True")
    set_cookie("show_popup", "True")
    cookies.save()

    # THEN trigger Streamlit's native logout (if applicable)
    if hasattr(st, "user") and st.user.is_logged_in:
        st.logout()

    # IMPORTANT: redirect user to home *before* rerunning
    st.query_params.clear()

    st.rerun()



if __name__ == "__main__":
    main()
    