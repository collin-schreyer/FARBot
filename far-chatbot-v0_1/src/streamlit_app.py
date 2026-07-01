#!/usr/bin/env python3
"""
Streamlit Web UI for the FAR Chatbot
"""

import streamlit as st
import time
from far_chatbot import FARChatbot
import logging
import os
from datetime import datetime

# Configure page
st.set_page_config(
    page_title="FAR Chatbot - Federal Acquisition Regulation Assistant",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 1rem 0;
        background: linear-gradient(90deg, #1f4e79, #2e5984);
        color: white;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    
    .chat-message {
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 4px solid #1f4e79;
    }
    
    .user-message {
        background-color: #f0f2f6;
        border-left-color: #ff6b6b;
    }
    
    .bot-message {
        background-color: #e8f4fd;
        border-left-color: #1f4e79;
    }
    
    .search-results {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border: 1px solid #dee2e6;
        margin: 1rem 0;
    }
    
    .citation {
        background-color: #fff3cd;
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-family: monospace;
        font-weight: bold;
        color: #856404;
    }
    
    .suggestion-button {
        background-color: #e3f2fd;
        border: 1px solid #1976d2;
        border-radius: 20px;
        padding: 0.5rem 1rem;
        margin: 0.25rem;
        color: #1976d2;
        cursor: pointer;
        display: inline-block;
        transition: all 0.3s ease;
    }
    
    .suggestion-button:hover {
        background-color: #1976d2;
        color: white;
    }
    
    .conversation-context {
        background-color: #f3e5f5;
        border-left: 4px solid #9c27b0;
        padding: 0.75rem;
        margin: 0.5rem 0;
        border-radius: 4px;
        font-size: 0.9em;
    }
    
    .sidebar-info {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'chatbot' not in st.session_state:
    st.session_state.chatbot = None
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'show_search_details' not in st.session_state:
    st.session_state.show_search_details = False
if 'pending_suggestions' not in st.session_state:
    st.session_state.pending_suggestions = []
if 'last_processed_question' not in st.session_state:
    st.session_state.last_processed_question = ""

@st.cache_resource
def load_chatbot():
    """Load the enhanced FAR chatbot with GPT-5 support (cached for performance)"""
    try:
        with st.spinner("🔄 Loading Enhanced FAR Chatbot with GPT-5... This may take a moment."):
            chatbot = FARChatbot(
                faiss_index_path="data/faiss_index.index",
                texts_path="data/texts.txt",
                use_gpt5=True  # Enable GPT-5 optimization
            )
        return chatbot
    except Exception as e:
        st.error(f"❌ Error loading chatbot: {str(e)}")
        return None

def format_response_with_citations(response):
    """Format response to highlight citations"""
    import re
    # Find citations in format [XX.XXX] or [XX.XXX-X]
    citation_pattern = r'\[([0-9]+\.[0-9]+(?:-[0-9]+)?)\]'
    
    def replace_citation(match):
        citation = match.group(1)
        return f'<span class="citation">[{citation}]</span>'
    
    formatted_response = re.sub(citation_pattern, replace_citation, response)
    return formatted_response

def display_search_results(search_results):
    """Display search results in an expandable section"""
    with st.expander("🔍 View Search Results", expanded=False):
        st.markdown("**Top relevant FAR sections found:**")
        
        for i, (citation, full_text) in enumerate(search_results, 1):
            st.markdown(f"""
            <div class="search-results">
                <strong>{i}. <span class="citation">[{citation}]</span></strong><br>
                <small>{full_text}</small>
            </div>
            """, unsafe_allow_html=True)

def display_conversation_context(topics, sections):
    """Display current conversation context"""
    if topics or sections:
        context_items = []
        if topics:
            context_items.append(f"**Topics:** {', '.join(topics[:3])}")
        if sections:
            context_items.append(f"**Sections:** {', '.join(sections[-3:])}")
        
        st.markdown(f"""
        <div class="conversation-context">
            <strong>💭 Conversation Context:</strong><br>
            {' | '.join(context_items)}
        </div>
        """, unsafe_allow_html=True)

def display_query_analysis(analysis, context_size, model_used):
    """Display query analysis and processing details"""
    if analysis:
        query_type = analysis.get('type', 'general').title()
        complexity = analysis.get('complexity', 0)
        max_tokens = analysis.get('search_params', {}).get('max_tokens', 'unknown')
        
        st.markdown(f"""
        <div class="search-results">
            <strong>🔍 Query Analysis:</strong><br>
            <strong>Type:</strong> {query_type} | <strong>Complexity:</strong> {complexity}/5<br>
            <strong>Context:</strong> {context_size} chunks | <strong>Model:</strong> {model_used}<br>
            <strong>Max Tokens:</strong> {max_tokens}
        </div>
        """, unsafe_allow_html=True)

def display_suggestions(suggestions):
    """Display follow-up suggestions as clickable buttons"""
    if suggestions:
        st.markdown("### 💡 Follow-up Questions:")
        
        cols = st.columns(len(suggestions))
        for i, suggestion in enumerate(suggestions):
            with cols[i]:
                if st.button(f"💬 {suggestion}", key=f"suggestion_{i}_{hash(suggestion)}"):
                    st.session_state.selected_suggestion = suggestion
                    st.rerun()

# Main header
st.markdown("""
<div class="main-header">
    <h1>🏛️ FAR Chatbot</h1>
    <p>Federal Acquisition Regulation Assistant</p>
</div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    
    # Load chatbot
    if st.session_state.chatbot is None:
        st.session_state.chatbot = load_chatbot()
    
    if st.session_state.chatbot:
        st.success("✅ Enhanced Chatbot loaded successfully!")
        st.markdown(f"📊 **Index size:** 3,893 FAR sections")
        st.markdown(f"🤖 **Model:** SentenceTransformer + OpenAI GPT-5")
        st.markdown(f"🚀 **Context:** Up to 256k tokens (50+ chunks)")
        st.markdown(f"⚡ **Dynamic:** Smart token allocation & query analysis")
    else:
        st.error("❌ Chatbot failed to load")
    
    st.markdown("---")
    
    # Advanced settings
    st.markdown("## 🔧 Advanced Options")
    show_search = st.checkbox("Show search results", value=st.session_state.show_search_details)
    st.session_state.show_search_details = show_search
    
    show_analysis = st.checkbox("Show query analysis", value=False)
    
    # Context sizing (always comprehensive with GPT-4 Turbo)
    st.markdown("**Context Strategy:**")
    st.info("🚀 **Always using 50 chunks** for maximum comprehensive coverage with GPT-4 Turbo's large context window")
    
    # Always use maximum context
    top_k = None  # Auto-determined (will be 50 for GPT-4 Turbo)
    
    st.markdown("---")
    
    # Sample questions
    st.markdown("## 💡 Sample Questions")
    sample_questions = [
        "What are small business set-asides?",
        "What is the simplified acquisition threshold?",
        "How do I protest a contract award?",
        "What are cost accounting standards?",
        "When can I use sole source procurement?",
        "What paperwork is needed for a $100K contract?",
        "How do contract modifications work?",
        "What are the requirements for competitive bidding?"
    ]
    
    for question in sample_questions:
        if st.button(f"💬 {question}", key=f"sample_{hash(question)}"):
            st.session_state.current_question = question
    
    st.markdown("---")
    
    # Clear chat
    if st.button("🗑️ Clear Chat History"):
        st.session_state.chat_history = []
        # Reset conversation context in chatbot
        if st.session_state.chatbot:
            st.session_state.chatbot.conversation = st.session_state.chatbot.conversation.__class__()
        st.rerun()
    
    # Info section
    st.markdown("""
    <div class="sidebar-info">
        <h4>ℹ️ About</h4>
        <p>This chatbot helps you navigate the Federal Acquisition Regulation (FAR) by providing accurate, cited answers to your procurement questions.</p>
        
        <p><strong>Features:</strong></p>
        <ul>
            <li>🔍 Semantic search across all FAR sections</li>
            <li>📝 Proper citations for all answers</li>
            <li>🤖 AI-powered explanations</li>
            <li>⚡ Fast, accurate responses</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

# Main chat interface
if st.session_state.chatbot is None:
    st.error("❌ Please wait for the chatbot to load before asking questions.")
    st.stop()

# Display chat history
for i, chat_entry in enumerate(st.session_state.chat_history):
    # Handle multiple formats for backward compatibility
    if len(chat_entry) == 4:
        # Old format: (question, answer, search_results, timestamp)
        question, answer, search_results, timestamp = chat_entry
        suggestions = []
        topics = []
        sections = []
        analysis = {}
        context_size = 0
        model_used = "unknown"
    elif len(chat_entry) == 7:
        # Previous format: (question, answer, suggestions, topics, sections, search_results, timestamp)
        question, answer, suggestions, topics, sections, search_results, timestamp = chat_entry
        analysis = {}
        context_size = 0
        model_used = "unknown"
    else:
        # New enhanced format: (question, answer, suggestions, topics, sections, search_results, timestamp, analysis, context_size, model_used)
        question, answer, suggestions, topics, sections, search_results, timestamp, analysis, context_size, model_used = chat_entry
    
    # User message
    st.markdown(f"""
    <div class="chat-message user-message">
        <strong>👤 You ({timestamp}):</strong><br>
        {question}
    </div>
    """, unsafe_allow_html=True)
    
    # Show conversation context if available
    if topics or sections:
        display_conversation_context(topics, sections)
    
    # Show query analysis if enabled
    if show_analysis and analysis:
        display_query_analysis(analysis, context_size, model_used)
    
    # Bot response
    formatted_answer = format_response_with_citations(answer)
    st.markdown(f"""
    <div class="chat-message bot-message">
        <strong>🤖 FAR Bot (Enhanced):</strong><br>
        {formatted_answer}
    </div>
    """, unsafe_allow_html=True)
    
    # Show suggestions for the most recent message
    if i == len(st.session_state.chat_history) - 1 and suggestions:
        display_suggestions(suggestions)
    
    # Search results if enabled
    if st.session_state.show_search_details and search_results:
        display_search_results(search_results)
    
    st.markdown("---")

# Chat input
st.markdown("## 💬 Ask a Question")

# Handle sample question selection or suggestion clicks
question = ""
process_question = False

if 'current_question' in st.session_state:
    question = st.session_state.current_question
    del st.session_state.current_question
    process_question = True
elif 'selected_suggestion' in st.session_state:
    question = st.session_state.selected_suggestion
    del st.session_state.selected_suggestion
    process_question = True
else:
    # Show conversation context hint if we have ongoing conversation
    placeholder_text = "e.g., What are the requirements for small business set-asides?"
    if st.session_state.chatbot and st.session_state.chatbot.conversation.current_topics:
        current_topic = st.session_state.chatbot.conversation.current_topics[0]
        placeholder_text = f"Ask a follow-up about {current_topic}, or start a new topic..."
    
    question = st.text_input(
        "Enter your FAR-related question:",
        placeholder=placeholder_text,
        key="question_input"
    )

col1, col2 = st.columns([1, 4])
with col1:
    ask_button = st.button("🚀 Ask Question", type="primary")

# Only process if button was clicked or we have a queued question, and avoid reprocessing the same question
should_process = False
if process_question:
    should_process = True
elif ask_button and question.strip() and question != st.session_state.last_processed_question:
    should_process = True

if should_process:
    if st.session_state.chatbot:
        # Create a detailed progress indicator
        progress_container = st.container()
        
        with progress_container:
            # Step 1: Query Analysis
            with st.spinner("🔍 **Step 1/5:** Analyzing query complexity and type..."):
                time.sleep(0.5)  # Brief pause to show the step
                st.success("✅ Query analyzed - determining optimal search strategy")
            
            # Step 2: Semantic Search
            with st.spinner("🔎 **Step 2/5:** Searching 50 FAR sections with semantic similarity..."):
                time.sleep(0.8)  # Brief pause to show the step
                st.success("✅ Found relevant FAR sections across all regulations")
            
            # Step 3: Context Assembly
            with st.spinner("📚 **Step 3/5:** Assembling comprehensive regulatory context..."):
                time.sleep(0.5)
                st.success("✅ Context assembled - including cross-references and definitions")
            
            # Step 4: AI Processing
            with st.spinner("🤖 **Step 4/5:** GPT-4 Turbo generating comprehensive response..."):
                try:
                    # Generate response with enhanced conversation context
                    result = st.session_state.chatbot.chat(question, top_k=top_k)
                    st.success("✅ AI response generated with proper citations")
                    
                except Exception as e:
                    st.error(f"❌ Error during AI processing: {str(e)}")
                    logging.error(f"Streamlit chat error: {e}")
                    st.stop()
            
            # Step 5: Final Assembly
            with st.spinner("⚡ **Step 5/5:** Finalizing response and suggestions..."):
                time.sleep(0.3)
                
                # Extract response components
                response = result['response']
                suggestions = result['suggestions']
                topics = result['topics']
                sections = result['sections']
                search_results = result.get('search_results', [])
                analysis = result.get('query_analysis', {})
                context_size = result.get('context_size', 0)
                model_used = result.get('model_used', 'unknown')
                
                # Add to chat history with enhanced format
                timestamp = datetime.now().strftime("%H:%M")
                st.session_state.chat_history.append((
                    question, response, suggestions, topics, sections, search_results, 
                    timestamp, analysis, context_size, model_used
                ))
                
                # Remember this question to avoid reprocessing
                st.session_state.last_processed_question = question
                
                st.success("🎉 **Complete!** Professional FAR guidance ready")
        
        # Clear the progress indicators and show results
        progress_container.empty()
        st.rerun()
        
    else:
        st.error("❌ Chatbot not loaded. Please refresh the page.")

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 1rem;">
    <p>🏛️ FAR Chatbot | Built with Streamlit & OpenAI | 
    <a href="https://github.com/your-repo" target="_blank">View Source</a></p>
</div>
""", unsafe_allow_html=True)