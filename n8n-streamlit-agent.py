import requests
import streamlit as st
import concurrent.futures
from psycopg2.extras import DictCursor
import psycopg2
import os

WEBHOOK_URL_CHAT = "https://baozz.app.n8n.cloud/webhook/ask-bot"
WEBHOOK_URL_UPLOAD = "https://baozz.app.n8n.cloud/webhook/upload-files"

# Fetch variables for PostgreSQL connection
USER = "postgres.fzeejyvlxgcbpwoeycky"
PASSWORD = "BaO19112002@"
HOST = "aws-0-ap-southeast-1.pooler.supabase.com"
PORT = "5432"
DBNAME = "postgres"

BEARER_TOKEN= "191122"

def get_connection():
    """Returns a new PostgreSQL connection."""
    return psycopg2.connect(
        user=USER,
        password=PASSWORD,
        host=HOST,
        port=PORT,
        dbname=DBNAME
    )


def login(user_name: str, password: str):
    try:
        conn = get_connection()
        # Use a dictionary cursor to fetch rows as dictionaries
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT * FROM users WHERE user_name = %s AND password = %s", (user_name, password))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            st.success("Login successful!")
            return dict(row)
        else:
            st.error("Invalid email or password")
            return None
    except Exception as e:
        st.error(f"Login failed: {str(e)}")
        return None

def signup(user_name: str, password: str):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (user_name, password) VALUES (%s, %s)", (user_name, password))
        cur.execute("INSERT INTO user_information (memory, user_id) VALUES (%s, %s)", ("None", user_name))
        conn.commit()
        cur.close()
        conn.close()
        st.success("Signup successful! Please log in.")
        return {"user_name": user_name, "password": password}
    except psycopg2.IntegrityError:
        st.error("Signup failed: Email already exists")
        return None
    except Exception as e:
        st.error(f"Signup failed: {str(e)}")
        return None

def init_session_state():
    if "auth" not in st.session_state:
        st.session_state.auth = None
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "messages" not in st.session_state:
        st.session_state.messages = []


def display_chat():
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

def handle_logout():
    st.session_state.auth = None
    st.session_state.session_id = None
    st.session_state.messages = []
    st.rerun()

def auth_ui():
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    with tab1:
        user_name = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login"):
            auth = login(user_name, password)
            if auth:
                st.session_state.auth = auth
                st.session_state.user_name = auth["user_name"]
                st.rerun()

    with tab2:
        user_name = st.text_input("Email", key="signup_email")
        password = st.text_input("Password", type="password", key="signup_password")
        if st.button("Sign Up"):
            result = signup(user_name, password)
            if result:
                st.success("Sign up successful! Please log in.")

def handle_binary_file_upload():
    """Handle multiple file uploads and submit binary data to webhook"""
    uploaded_files = st.sidebar.file_uploader(
        "Upload files", 
        type=["txt", "pdf", "docx", "xlsx"], 
        accept_multiple_files=True
    )
    
    if uploaded_files and len(uploaded_files) > 0:
        st.sidebar.success(f"{len(uploaded_files)} file(s) uploaded")
        
        if st.sidebar.button("Process Files"):
            with st.spinner("Uploading files..."):
                files = []
                
                for uploaded_file in uploaded_files:
                    file_content = uploaded_file.getvalue()
                    # Ensure file_content is in bytes. If it's a string, encode it.
                    if isinstance(file_content, str):
                        file_content = file_content.encode("utf-8")
                    
                    # Determine MIME type based on file extension
                    ext = uploaded_file.name.split('.')[-1].lower()
                    if ext == "txt":
                        file_type = "text/plain"
                    elif ext == "pdf":
                        file_type = "application/pdf"
                    elif ext == "docx":
                        file_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    elif ext == "xlsx":
                        file_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    else:
                        # Fallback to the provided type or generic binary type
                        file_type = uploaded_file.type if uploaded_file.type else "application/octet-stream"
                    
                    st.write(f"Processing {uploaded_file.name} | MIME: {file_type} | Size: {len(file_content)} bytes")
                    
                    files.append(
                        ('files', (uploaded_file.name, file_content, file_type))
                    )
                
                # Headers with user information; update BEARER_TOKEN and other header details as needed
                headers = {
                    "Authorization": BEARER_TOKEN,
                    "user_id": str(st.session_state.auth['user_name'])
                }
                
                response = requests.post(
                    WEBHOOK_URL_UPLOAD,
                    files=files,
                    headers=headers
                )
                
                if response.status_code == 200:
                    st.sidebar.success("Files processed successfully!")
                    return {"status": "success", "data": response.json()}
                else:
                    st.sidebar.error(f"Error: {response.status_code} - {response.text}")
                    return {"status": "error", "message": response.text}
        
        return {"status": "ready", "file_count": len(uploaded_files)}
    
    return None


def fetch_response(payload, headers):
    """Helper function to perform the HTTP request with a timeout."""
    try:
        # Adjust timeout as needed
        response = requests.post(WEBHOOK_URL_CHAT, json=payload, headers=headers, timeout=60)
        return response
    except Exception as e:
        return e

def main():
    st.title("AI Chat Interface")
    init_session_state()

    if st.session_state.auth is None:
        auth_ui()
    else:
        st.sidebar.success(f"Logged in as {st.session_state.auth['user_name']}")
        if st.sidebar.button("Logout"):
            handle_logout()
        
        handle_binary_file_upload()        
        display_chat()

        if prompt := st.chat_input("What is your message?"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            payload = {"question": prompt}
            headers = {
                "user_id": st.session_state.auth['user_name'],
                "Authorization": BEARER_TOKEN,
            }
            
            with st.spinner("AI is thinking..."):
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(fetch_response, payload, headers)
                    result = future.result()
            
            if isinstance(result, Exception):
                st.error(f"Request failed: {result}")
            elif result.status_code == 200:
                ai_message = result.json().get("output", "Sorry, I couldn't generate a response.")
                st.session_state.messages.append({"role": "assistant", "content": ai_message})
                with st.chat_message("assistant"):
                    st.markdown(ai_message)
            else:
                st.error(f"Error: {result.status_code} - {result.text}")

if __name__ == "__main__":
    main()
