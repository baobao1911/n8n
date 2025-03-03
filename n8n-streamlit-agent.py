import requests
import streamlit as st
import concurrent.futures
from psycopg2.extras import DictCursor
import psycopg2
import uuid
from dotenv import load_dotenv
import os

load_dotenv()

WEBHOOK_URL_CHAT = os.getenv("WEBHOOK_URL_CHAT")
WEBHOOK_URL_UPLOAD = os.getenv("WEBHOOK_URL_UPLOAD")
WEBHOOK_URL_RERANK = os.getenv("WEBHOOK_URL_RERANK")

# Fetch variables for PostgreSQL connection
USER = os.getenv("user")
PASSWORD = os.getenv("password")
HOST = os.getenv("host")
PORT = os.getenv("port")
DBNAME = os.getenv("dbname")

BEARER_TOKEN = os.getenv("BEARER_TOKEN")


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
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute("SELECT user_name FROM users WHERE user_name = %s AND password = %s", (user_name, password))
        user = cur.fetchone()
        if user is None:
            return None
        user = dict(user)

        cur.execute("SELECT session_id FROM user_session WHERE user_name = %s", (user["user_name"], ))
        session_ids = [session['session_id'] for session in cur.fetchall()]
        cur.execute(
            "SELECT metadata FROM documents WHERE metadata->>'user_name' = %s;",
            (user_name,)
        )
        user_docs = [] 
        for doc in cur.fetchall():
            metadata = doc["metadata"]  # doc is a dict with key 'metadata'
            if metadata["file_name"] not in user_docs:
                user_docs.append(metadata["file_name"])

        cur.close()
        conn.close()
        user["session_ids"] = session_ids
        user["docs"] = user_docs
        if user:
            return user
        else:
            return None
    except Exception as e:
        return None

def signup(user_name: str, password: str):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (user_name, password) VALUES (%s, %s)", (user_name, password))
        conn.commit()
        cur.close()
        conn.close()
        return {"user_name": user_name, "password": password}
    except psycopg2.IntegrityError:
        st.error("Signup failed: Email already exists")
        return None
    except Exception as e:
        st.error(f"Signup failed: {str(e)}")
        return None

def init_session_state():
    if "user_data" not in st.session_state:
        st.session_state.user_data = None
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "messages" not in st.session_state:
        st.session_state.messages = []

def request_rerank():
    try:
        headers = {
            "Authorization": BEARER_TOKEN,
            "user_name": str(st.session_state.user_data['user_name']),
            "session_id": str(st.session_state.session_id)
        }
        response = requests.get(WEBHOOK_URL_RERANK, headers=headers, timeout=120)
        return response
    except Exception as e:
        return e

def display_chat():
    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            if i %2 != 0:
                if "feedback" in message:
                    st.write(f"Feedback: {message['feedback']}")
                
                col1, col2 = st.columns([0.1, 0.1])
                with col1:
                    if st.button("👍", key=f"thumbs_up_{i}"):
                        st.session_state.messages[i]["feedback"] = "thumbs_up"
                        st.rerun()
                with col2:
                    if st.button("👎", key=f"thumbs_down_{i}"):
                        st.session_state.messages[i]["feedback"] = "thumbs_down"
                        st.rerun()
            

def handle_logout():
    st.session_state.user_data = None
    st.session_state.session_id = None
    st.session_state.messages = []
    st.rerun()

def auth_ui():
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    with tab1:
        user_name = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login"):
            user_data = login(user_name, password)
            new_session_id = str(uuid.uuid4())
            if user_data:
                st.session_state.user_data = user_data
                st.session_state.session_id = new_session_id
                st.rerun()

    with tab2:
        user_name = st.text_input("Email", key="signup_email")
        password = st.text_input("Password", type="password", key="signup_password")
        if st.button("Sign Up"):
            result = signup(user_name, password)
            if result:
                st.success("Sign up successful! Please log in.")

def get_user_document(user_name: str):
    try:
        conn = get_connection()
        cur =conn.cursor(cursor_factory=DictCursor)
        cur.execute(
            "SELECT metadata FROM documents WHERE metadata->>'user_name' = %s;",
            (user_name,)
        )
        docs = cur.fetchall()
        if docs:
            user_docs = [] 
            for doc in docs:
                metadata = doc["metadata"]
                if metadata["file_name"] not in user_docs:
                    user_docs.append(metadata["file_name"])
            return user_docs
        return None
    except:
        return None
        

if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0

def handle_binary_file_upload():
    """Handle multiple file uploads and submit binary data to webhook"""
    uploaded_files = st.sidebar.file_uploader(
        "Upload files", 
        type=["txt", "pdf", "xlsx"], 
        accept_multiple_files=True,
        key=f"uploader_{st.session_state['uploader_key']}"
    )
    
    if uploaded_files and len(uploaded_files) > 0:        
        if st.sidebar.button("Process Files"):
            with st.spinner("Uploading files..."):
                files = []
                
                for uploaded_file in uploaded_files:
                    file_content = uploaded_file.getvalue()
                    if isinstance(file_content, str):
                        file_content = file_content.encode("utf-8")
                    
                    # Determine MIME type based on file extension
                    ext = uploaded_file.name.split('.')[-1].lower()
                    if ext == "txt":
                        file_type = "text/plain"
                    elif ext == "pdf":
                        file_type = "application/pdf"
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
                    "user_name": str(st.session_state.user_data['user_name']),
                    "session_id": str(st.session_state.session_id)
                }
                
                response = requests.post(
                    WEBHOOK_URL_UPLOAD,
                    files=files,
                    headers=headers
                )
                
                if response.status_code == 200:
                    st.sidebar.success("Files processed successfully!")
                    st.session_state["uploader_key"] += 1
                    st.session_state.user_data["docs"] = get_user_document(str(st.session_state.user_data["user_name"]))
                    st.rerun()
                    return {"status": "success", "data": response.json()}
                else:
                    st.sidebar.error(f"Error: {response.status_code} - {response.text}")
                    return {"status": "error", "message": response.text}
        
        return {"status": "ready", "file_count": len(uploaded_files)}
    
    return None

def get_full_chat_session(user_name: str):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT session_id FROM user_session WHERE user_name = %s", (user_name, ))
        full_session = cur.fetchall()
        cur.close()
        conn.close()
        if full_session:
            session_ids = [session[0] for session in full_session]
            return session_ids
    except:
        return None

def get_chat_history(sessin_id: str):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT message FROM n8n_chat_histories WHERE session_id = %s", (sessin_id, ))
        histories_chat = cur.fetchall()
        cur.close()
        conn.close()
        if histories_chat:
            chat_message = []
            for chat in histories_chat:
                chat = chat[0]
                chat_message.append({"role": chat["type"], "content": chat["content"]})
            return chat_message
    except:
        return None

def select_chat_session():
    sessions = st.session_state.user_data.get("session_ids", [])
    if sessions is None:
        sessions = []
    sessions_with_new = ["New Chat Session"] + sessions
    with st.sidebar.form(key="session_select_form"):
        selected_session = st.selectbox("Select Chat Session", sessions_with_new)
        submit_button = st.form_submit_button("Activate Session")
        if submit_button:
            if selected_session == "New Chat Session":
                # Create a new session ID using uuid
                new_session_id = str(uuid.uuid4())
                st.session_state.session_id = new_session_id
                st.session_state.messages = []
            else:
                st.session_state.session_id = selected_session
                st.session_state.messages = get_chat_history(str(selected_session))
                st.session_state.user_data["session_ids"] = get_full_chat_session(str(st.session_state.user_data['user_name']))
            st.rerun()

def delete_document(file_name):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM documents WHERE metadata->>'file_name' = %s", (file_name,))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error deleting document: {e}")
        return False

def show_user_documents():
    if "user_data" in st.session_state and st.session_state.user_data:
        user_docs = st.session_state.user_data.get("docs", [])
        if user_docs:
            with st.expander("Your Documents"):
                for doc in user_docs:
                    col1, col2 = st.columns([0.8, 0.2])
                    with col1:
                        try:
                            st.write(f"- {str(doc).split("_", 1)[1]}")
                        except:
                            st.write(f"- {doc}")
                    with col2:
                        if st.button("x", key=f"delete_{doc}"):
                            if delete_document(doc):
                                st.success(f"Document '{doc}' deleted successfully.")
                                try:
                                    st.session_state.user_data["docs"] = get_user_document(str(st.session_state.user_data["user_name"))
                                except:
                                    None
                                st.rerun()
        else:
            st.info("No documents found for your account.")
    else:
        st.warning("Please log in to see your documents.")


def fetch_response(payload, headers):
    """Helper function to perform the HTTP request with a timeout."""
    try:
        # Adjust timeout as needed
        response = requests.post(WEBHOOK_URL_CHAT, json=payload, headers=headers, timeout=300)
        return response
    except Exception as e:
        return e

def main():
    st.title("AI Chat Interface")
    init_session_state()
    print(st.session_state.user_data)
    print(st.session_state.session_id)
    if st.session_state.user_data is None:
        auth_ui()
    else:
        st.sidebar.success(f"Logged in as {st.session_state.user_data['user_name']}")
        if st.sidebar.button("Logout"):
            handle_logout()
        
        handle_binary_file_upload()    
        select_chat_session()    
        show_user_documents()
        display_chat()

        if prompt := st.chat_input("What is your message?"):
            st.session_state.messages.append({"role": "human", "content": prompt})
            with st.chat_message("human"):
                st.markdown(prompt)

            payload = {"question": prompt}
            headers = {
                "session_id": str(st.session_state.session_id),
                "user_name": st.session_state.user_data['user_name'],
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
