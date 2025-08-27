#!/usr/bin/env python3
"""
FAR Chatbot Web Interface using Streamlit
"""

import streamlit as st
import os
from far_chatbot import FARChatbot
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Page config
st.set_page_config(
    page_title="FAR Chatbot",
    page_icon="🏛️",
    layout="wide"
)

@st.cache_resource
def load_chatbot():
    """Load the chatbot (cached for performance)"""
    faiss_index_path = "dita_html/faiss_index.index"
    texts_path = "dita_html/texts.txt"
    
    try:
        return FARChatbot(faiss_index_path, texts_path)
    except Exception as e:
        st.error(f"Failed to load chatbot: {e}")
        return None

def main():
    st.title("🏛️ FAR Chatbot")
    st.subheader("Federal Acquisition Regulation Assistant")
    
    # Sidebar
    with st.sidebar:
        st.header("Settings")
        top_k = st.slider("Number of documents to search", 1, 10, 5)
        
        st.header("About")
        st.info("""
        This chatbot searches through Federal Acquisition Regulation (FAR) documents 
        to answer your questions with proper citations.
        
        **Features:**
        - Semantic search through 3,893 FAR sections
        - Automatic citation generation
        - Context-aware responses
        """)
        
        # OpenAI API Key input
        st.header("OpenAI Integration")
        api_key = st.text_input("OpenAI API Key (optional)", type="password", 
                               help="For enhanced responses. Leave empty for basic search.")
        if api_key:
            os.environ['OPENAI_API_KEY'] = api_key
    
    # Load chatbot
    chatbot = load_chatbot()
    if not chatbot:
        st.error("Could not load the FAR chatbot. Please check the file paths.")
        return
    
    # Chat interface
    st.header("Ask a Question")
    
    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Ask about federal acquisition regulations..."):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Searching FAR documents..."):
                try:
                    response = chatbot.chat(prompt, top_k)
                    st.markdown(response)
                    
                    # Add assistant response to chat history
                    st.session_state.messages.append({"role": "assistant", "content": response})
                    
                except Exception as e:
                    error_msg = f"Sorry, I encountered an error: {e}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
    
    # Example queries
    st.header("Example Questions")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("What are the requirements for small business set-asides?"):
            st.session_state.messages.append({"role": "user", "content": "What are the requirements for small business set-asides?"})
            st.rerun()
    
    with col2:
        if st.button("How do I handle contract modifications?"):
            st.session_state.messages.append({"role": "user", "content": "How do I handle contract modifications?"})
            st.rerun()
    
    col3, col4 = st.columns(2)
    
    with col3:
        if st.button("What is the process for protests?"):
            st.session_state.messages.append({"role": "user", "content": "What is the process for protests?"})
            st.rerun()
    
    with col4:
        if st.button("Tell me about cost accounting standards"):
            st.session_state.messages.append({"role": "user", "content": "Tell me about cost accounting standards"})
            st.rerun()
    
    # Clear chat button
    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

if __name__ == "__main__":
    main()