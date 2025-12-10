#!/usr/bin/env python3
"""
Enhanced Streamlit Web UI for the FAR Chatbot
Features: Inline clickable citations, modern UI, expandable sources
"""

import streamlit as st
import time
from far_chatbot import FARChatbot
import logging
import os
from datetime import datetime
import re
import markdown

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('streamlit_app.log')
    ]
)
logger = logging.getLogger(__name__)

logger.info("🚀 Starting Enhanced FAR Chatbot...")

# Configure page
st.set_page_config(
    page_title="FAR Chatbot - Federal Acquisition Regulation Assistant",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# AUTHENTICATION
# ============================================
# Credentials (in production, use environment variables or secrets)
VALID_CREDENTIALS = {
    "testuser": "farbot2025"
}

def check_password():
    """Returns True if the user has entered valid credentials."""
    
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        username = st.session_state.get("username", "")
        password = st.session_state.get("password", "")
        
        if username in VALID_CREDENTIALS and VALID_CREDENTIALS[username] == password:
            st.session_state["authenticated"] = True
            # Clear password from session state for security
            del st.session_state["password"]
            logger.info(f"User '{username}' logged in successfully")
        else:
            st.session_state["authenticated"] = False
            logger.warning(f"Failed login attempt for user '{username}'")

    # First run or not authenticated
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        # Show login form
        st.markdown("""
        <style>
            .login-container {
                max-width: 400px;
                margin: 100px auto;
                padding: 2rem;
                background: linear-gradient(135deg, #f7fafc 0%, #edf2f7 100%);
                border-radius: 16px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            }
            .login-header {
                text-align: center;
                margin-bottom: 2rem;
            }
            .login-header h1 {
                color: #1a365d;
                font-size: 2rem;
            }
            .login-header p {
                color: #718096;
            }
        </style>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("""
            <div class="login-header">
                <h1>🏛️ FAR Chatbot</h1>
                <p>Please log in to continue</p>
            </div>
            """, unsafe_allow_html=True)
            
            st.text_input("Username", key="username")
            st.text_input("Password", type="password", key="password")
            st.button("🔐 Log In", on_click=password_entered, type="primary", use_container_width=True)
            
            if st.session_state.get("authenticated") == False and st.session_state.get("password") is None:
                # Only show error after a failed attempt (password was cleared)
                if "username" in st.session_state and st.session_state["username"]:
                    st.error("❌ Invalid username or password")
        
        return False
    
    return True

# Check authentication before showing the app
if not check_password():
    st.stop()

# Enhanced CSS with clickable citations
st.markdown("""
<style>
    /* Main container */
    .main-header {
        text-align: center;
        padding: 1.5rem;
        background: linear-gradient(135deg, #1a365d 0%, #2c5282 50%, #2b6cb0 100%);
        color: white;
        border-radius: 16px;
        margin-bottom: 2rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    }
    
    .main-header h1 {
        margin: 0;
        font-size: 2.5rem;
        font-weight: 700;
    }
    
    .main-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.9;
        font-size: 1.1rem;
    }
    
    /* Chat messages */
    .chat-container {
        max-width: 900px;
        margin: 0 auto;
    }
    
    .user-message {
        background: linear-gradient(135deg, #f7fafc 0%, #edf2f7 100%);
        padding: 1rem 1.25rem;
        border-radius: 16px 16px 4px 16px;
        margin: 1rem 0;
        border-left: 4px solid #e53e3e;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    
    .bot-message {
        background: linear-gradient(135deg, #ebf8ff 0%, #e6fffa 100%);
        padding: 1.25rem 1.5rem;
        border-radius: 16px 16px 16px 4px;
        margin: 1rem 0;
        border-left: 4px solid #2b6cb0;
        box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    }
    
    .bot-content {
        line-height: 1.8;
        color: #2d3748;
    }
    
    .bot-content h1, .bot-content h2, .bot-content h3, .bot-content h4 {
        color: #1a365d;
        margin-top: 1.25rem;
        margin-bottom: 0.75rem;
        font-weight: 600;
    }
    
    .bot-content h3 {
        font-size: 1.1rem;
        border-bottom: 2px solid #bee3f8;
        padding-bottom: 0.5rem;
    }
    
    .bot-content p {
        margin: 0.75rem 0;
    }
    
    .bot-content ul, .bot-content ol {
        margin: 0.75rem 0;
        padding-left: 1.5rem;
    }
    
    .bot-content li {
        margin: 0.5rem 0;
    }
    
    .bot-content strong {
        color: #2c5282;
    }
    
    .bot-content code {
        background: #edf2f7;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.9em;
    }
    
    .message-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 0.75rem;
        font-weight: 600;
        color: #2d3748;
    }
    
    .timestamp {
        font-size: 0.75rem;
        color: #718096;
        font-weight: 400;
    }
    
    /* Clickable citations - the star of the show! */
    .citation-link {
        background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
        padding: 2px 8px;
        border-radius: 6px;
        font-family: 'SF Mono', 'Monaco', 'Inconsolata', monospace;
        font-weight: 600;
        font-size: 0.9em;
        color: #92400e;
        text-decoration: none;
        cursor: pointer;
        border: 1px solid #f59e0b;
        transition: all 0.2s ease;
        display: inline-block;
        margin: 0 2px;
    }
    
    .citation-link:hover {
        background: linear-gradient(135deg, #fde68a 0%, #fbbf24 100%);
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(245, 158, 11, 0.3);
        color: #78350f;
    }
    
    /* Source cards */
    .source-card {
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem;
        margin: 0.75rem 0;
        transition: all 0.2s ease;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    
    .source-card:hover {
        border-color: #2b6cb0;
        box-shadow: 0 4px 12px rgba(43, 108, 176, 0.15);
    }
    
    .source-header {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 0.5rem;
    }
    
    .source-citation {
        background: linear-gradient(135deg, #2b6cb0 0%, #3182ce 100%);
        color: white;
        padding: 4px 10px;
        border-radius: 6px;
        font-family: 'SF Mono', 'Monaco', monospace;
        font-weight: 600;
        font-size: 0.85rem;
    }
    
    .source-text {
        color: #4a5568;
        font-size: 0.9rem;
        line-height: 1.6;
        max-height: 150px;
        overflow-y: auto;
        padding-right: 0.5rem;
    }
    
    .source-text::-webkit-scrollbar {
        width: 4px;
    }
    
    .source-text::-webkit-scrollbar-thumb {
        background: #cbd5e0;
        border-radius: 2px;
    }
    
    /* Query analysis badge */
    .analysis-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        background: #f0fff4;
        border: 1px solid #9ae6b4;
        padding: 0.5rem 1rem;
        border-radius: 20px;
        font-size: 0.85rem;
        color: #276749;
        margin: 0.25rem;
    }
    
    /* Suggestion buttons */
    .suggestion-pill {
        background: linear-gradient(135deg, #e6fffa 0%, #b2f5ea 100%);
        border: 1px solid #38b2ac;
        border-radius: 25px;
        padding: 0.5rem 1rem;
        color: #234e52;
        font-size: 0.9rem;
        cursor: pointer;
        transition: all 0.2s ease;
        display: inline-block;
        margin: 0.25rem;
    }
    
    .suggestion-pill:hover {
        background: linear-gradient(135deg, #38b2ac 0%, #319795 100%);
        color: white;
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(56, 178, 172, 0.3);
    }
    
    /* Context indicator */
    .context-bar {
        background: linear-gradient(90deg, #faf5ff 0%, #f3e8ff 100%);
        border-left: 3px solid #9f7aea;
        padding: 0.75rem 1rem;
        border-radius: 0 8px 8px 0;
        margin: 0.5rem 0;
        font-size: 0.85rem;
        color: #553c9a;
    }
    
    /* Stats bar */
    .stats-bar {
        display: flex;
        gap: 1rem;
        flex-wrap: wrap;
        margin: 0.5rem 0;
    }
    
    .stat-item {
        background: #f7fafc;
        padding: 0.25rem 0.75rem;
        border-radius: 15px;
        font-size: 0.8rem;
        color: #4a5568;
        border: 1px solid #e2e8f0;
    }
    
    /* Sidebar styling */
    .sidebar-card {
        background: white;
        border-radius: 12px;
        padding: 1rem;
        margin: 1rem 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        border: 1px solid #e2e8f0;
    }
    
    /* Loading animation */
    .loading-step {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.5rem;
        margin: 0.25rem 0;
        border-radius: 8px;
        font-size: 0.9rem;
    }
    
    .loading-step.active {
        background: #ebf8ff;
        color: #2b6cb0;
    }
    
    .loading-step.complete {
        background: #f0fff4;
        color: #276749;
    }
    
    /* Divider */
    .fancy-divider {
        height: 2px;
        background: linear-gradient(90deg, transparent, #e2e8f0, transparent);
        margin: 1.5rem 0;
    }
</style>
<script>
    // Handle citation link clicks - runs after DOM updates
    function setupCitationLinks() {
        document.querySelectorAll('.citation-link').forEach(link => {
            if (!link.hasAttribute('data-handler-attached')) {
                link.setAttribute('data-handler-attached', 'true');
                link.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    const url = this.getAttribute('data-url') || this.getAttribute('href');
                    if (url) {
                        window.open(url, '_blank');
                    }
                    return false;
                });
            }
        });
    }
    
    // Run on load and observe for changes
    setupCitationLinks();
    
    // Use MutationObserver to handle dynamically added content
    const observer = new MutationObserver(function(mutations) {
        setupCitationLinks();
    });
    
    observer.observe(document.body, { childList: true, subtree: true });
</script>
""", unsafe_allow_html=True)

# Initialize session state
if 'chatbot' not in st.session_state:
    st.session_state.chatbot = None
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'show_sources' not in st.session_state:
    st.session_state.show_sources = True
if 'last_processed_question' not in st.session_state:
    st.session_state.last_processed_question = ""
if 'source_texts' not in st.session_state:
    st.session_state.source_texts = {}

@st.cache_resource
def load_chatbot():
    """Load the FAR chatbot (cached)"""
    try:
        logger.info("🔄 Loading FAR Chatbot...")
        
        # Handle paths for both local and Streamlit Cloud deployment
        # When running from python/ directory locally vs from repo root on cloud
        script_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.dirname(script_dir)  # Go up one level from python/
        
        # Try multiple path options
        path_options = [
            # From repo root (Streamlit Cloud)
            (os.path.join(repo_root, "dita_html/faiss_index.index"), 
             os.path.join(repo_root, "dita_html/texts.txt")),
            # Relative to current working directory
            ("dita_html/faiss_index.index", "dita_html/texts.txt"),
            # Relative from python/ directory
            ("../dita_html/faiss_index.index", "../dita_html/texts.txt"),
        ]
        
        faiss_path = None
        texts_path = None
        
        for fp, tp in path_options:
            if os.path.exists(fp) and os.path.exists(tp):
                faiss_path = fp
                texts_path = tp
                logger.info(f"✅ Found data files at: {fp}")
                break
        
        if not faiss_path:
            # List what we can find for debugging
            logger.error(f"❌ Could not find data files. CWD: {os.getcwd()}")
            logger.error(f"Script dir: {script_dir}")
            logger.error(f"Repo root: {repo_root}")
            if os.path.exists(repo_root):
                logger.error(f"Repo root contents: {os.listdir(repo_root)}")
            raise FileNotFoundError("Could not locate FAISS index and texts files")
        
        with st.spinner("🔄 Loading FAR Chatbot..."):
            chatbot = FARChatbot(
                faiss_index_path=faiss_path,
                texts_path=texts_path,
                use_gpt5=True
            )
        return chatbot
    except Exception as e:
        logger.error(f"❌ Error loading chatbot: {str(e)}")
        st.error(f"❌ Error loading chatbot: {str(e)}")
        return None

def get_acquisition_gov_url(citation: str) -> str:
    """
    Convert a FAR citation to its acquisition.gov URL.
    
    Examples:
        19.502-2 -> https://www.acquisition.gov/far/19.502-2
        2.101 -> https://www.acquisition.gov/far/2.101
        19.502-2(a) -> https://www.acquisition.gov/far/19.502-2
    """
    # Remove any parenthetical subsections for the URL (e.g., "(a)" -> "")
    base_citation = re.sub(r'\([a-z]\)$', '', citation)
    return f"https://www.acquisition.gov/far/{base_citation}"

def make_citations_clickable(response: str, search_results: list) -> str:
    """Convert citation references to clickable links that open acquisition.gov"""
    import markdown
    
    # Build a map of citations to their full text
    citation_map = {}
    for citation, full_text in search_results:
        citation_map[citation] = full_text
    
    # Store in session state for the expander
    st.session_state.source_texts = citation_map
    
    # Process citations BEFORE markdown conversion to avoid HTML interference
    text = response
    
    # Helper to create citation link HTML
    def make_link(citation):
        url = get_acquisition_gov_url(citation)
        return f'<a href="{url}" data-url="{url}" class="citation-link" title="View FAR {citation} on acquisition.gov">'
    
    # 1. Replace [FAR X.XXX] format -> clickable link
    def replace_far_bracket(match):
        citation = match.group(1)
        return f'{make_link(citation)}[{citation}]</a>'
    text = re.sub(r'\[FAR\s+(\d+\.\d+(?:-\d+)?(?:\([a-z]\))?)\]', replace_far_bracket, text)
    
    # 2. Replace [X.XXX] format (without FAR prefix) -> clickable link
    def replace_bracket(match):
        citation = match.group(1)
        return f'{make_link(citation)}[{citation}]</a>'
    text = re.sub(r'\[(\d+\.\d+(?:-\d+)?(?:\([a-z]\))?)\]', replace_bracket, text)
    
    # 3. Replace standalone "FAR X.XXX" format -> clickable link
    # But avoid matching if already inside our link tags
    def replace_standalone(match):
        citation = match.group(1)
        return f'{make_link(citation)}FAR {citation}</a>'
    # Match FAR followed by citation number, but not if preceded by "View " (our title text)
    text = re.sub(r'(?<!View )FAR\s+(\d+\.\d+(?:-\d+)?(?:\([a-z]\))?)', replace_standalone, text)
    
    # Now convert markdown to HTML (our links will be preserved)
    formatted = markdown.markdown(text, extensions=['tables', 'fenced_code', 'nl2br'])
    
    return formatted

def render_source_cards(search_results: list):
    """Render expandable source cards with links to acquisition.gov"""
    if not search_results:
        return
    
    st.markdown("### 📚 Source Documents")
    st.markdown("*Click any citation to view the full text on acquisition.gov*")
    
    for i, (citation, full_text) in enumerate(search_results[:8]):
        citation_id = citation.replace(".", "_").replace("-", "_")
        acq_url = get_acquisition_gov_url(citation)
        
        with st.expander(f"📄 FAR {citation}", expanded=False):
            st.markdown(f"""
            <div id="source_{citation_id}" class="source-card">
                <div class="source-header">
                    <a href="{acq_url}" target="_blank" class="source-citation" style="text-decoration:none;color:white;">
                        🔗 FAR {citation} ↗
                    </a>
                </div>
                <div class="source-text">{full_text[:1500]}{'...' if len(full_text) > 1500 else ''}</div>
                <div style="margin-top:0.75rem;">
                    <a href="{acq_url}" target="_blank" style="color:#2b6cb0;font-size:0.85rem;">
                        📖 View full text on acquisition.gov →
                    </a>
                </div>
            </div>
            """, unsafe_allow_html=True)

def render_chat_message(entry, index, total):
    """Render a single chat message with clickable citations"""
    # Unpack entry (handle different formats)
    if len(entry) >= 10:
        question, answer, suggestions, topics, sections, search_results, timestamp, analysis, context_size, model_used = entry[:10]
    elif len(entry) == 7:
        question, answer, suggestions, topics, sections, search_results, timestamp = entry
        analysis, context_size, model_used = {}, 0, "unknown"
    else:
        question, answer, search_results, timestamp = entry[:4]
        suggestions, topics, sections = [], [], []
        analysis, context_size, model_used = {}, 0, "unknown"
    
    # User message
    st.markdown(f"""
    <div class="user-message">
        <div class="message-header">
            👤 You <span class="timestamp">{timestamp}</span>
        </div>
        {question}
    </div>
    """, unsafe_allow_html=True)
    
    # Context bar if we have topics
    if topics:
        topics_str = ", ".join(topics[:3])
        st.markdown(f"""
        <div class="context-bar">
            💭 <strong>Topics:</strong> {topics_str}
        </div>
        """, unsafe_allow_html=True)
    
    # Bot response with clickable citations
    formatted_answer = make_citations_clickable(answer, search_results if search_results else [])
    
    st.markdown(f"""
    <div class="bot-message">
        <div class="message-header">
            🤖 FAR Bot <span class="timestamp">GPT-4 Turbo</span>
        </div>
        <div class="bot-content">
            {formatted_answer}
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Stats bar
    if analysis or context_size:
        query_type = analysis.get('type', 'general').title() if analysis else 'General'
        complexity = analysis.get('complexity', 0) if analysis else 0
        
        st.markdown(f"""
        <div class="stats-bar">
            <span class="stat-item">📊 {query_type}</span>
            <span class="stat-item">🎯 Complexity: {complexity}/5</span>
            <span class="stat-item">📚 {context_size} sources</span>
            <span class="stat-item">🤖 {model_used}</span>
        </div>
        """, unsafe_allow_html=True)
    
    # Source cards (only for most recent message)
    if index == total - 1 and search_results and st.session_state.show_sources:
        render_source_cards(search_results)
    
    # Suggestions (only for most recent)
    if index == total - 1 and suggestions:
        st.markdown("### 💡 Follow-up Questions")
        cols = st.columns(min(len(suggestions), 3))
        for i, suggestion in enumerate(suggestions):
            with cols[i % 3]:
                if st.button(f"💬 {suggestion}", key=f"sugg_{index}_{i}"):
                    st.session_state.selected_suggestion = suggestion
                    st.rerun()
    
    st.markdown('<div class="fancy-divider"></div>', unsafe_allow_html=True)

# Main header
st.markdown("""
<div class="main-header">
    <h1>🏛️ FAR Chatbot</h1>
    <p>Federal Acquisition Regulation Assistant with Clickable Citations</p>
</div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    
    # Load chatbot
    if st.session_state.chatbot is None:
        st.session_state.chatbot = load_chatbot()
    
    if st.session_state.chatbot:
        st.success("✅ Chatbot Ready!")
        st.markdown("""
        <div class="sidebar-card">
            <strong>📊 System Info</strong><br>
            • 3,893 FAR sections indexed<br>
            • GPT-4 Turbo powered<br>
            • 50+ context chunks per query<br>
            • Clickable inline citations
        </div>
        """, unsafe_allow_html=True)
    else:
        st.error("❌ Failed to load")
    
    st.markdown("---")
    
    # Display options
    st.markdown("### 🎨 Display Options")
    st.session_state.show_sources = st.checkbox("Show source documents", value=True)
    
    st.markdown("---")
    
    # Sample questions
    st.markdown("### 💡 Try These Questions")
    samples = [
        "What are small business set-asides?",
        "Explain the simplified acquisition threshold",
        "How do I protest a contract award?",
        "What are cost accounting standards?",
        "When can I use sole source?",
        "What is the micro-purchase threshold?",
        "How do contract modifications work?",
        "What are competitive bidding requirements?"
    ]
    
    for q in samples:
        if st.button(f"💬 {q}", key=f"sample_{hash(q)}"):
            st.session_state.current_question = q
    
    st.markdown("---")
    
    col_clear, col_logout = st.columns(2)
    with col_clear:
        if st.button("🗑️ Clear Chat", type="secondary", use_container_width=True):
            st.session_state.chat_history = []
            if st.session_state.chatbot:
                st.session_state.chatbot.conversation = st.session_state.chatbot.conversation.__class__()
            st.rerun()
    with col_logout:
        if st.button("🚪 Logout", type="secondary", use_container_width=True):
            st.session_state["authenticated"] = False
            st.session_state.chat_history = []
            st.rerun()
    
    st.markdown("""
    <div class="sidebar-card">
        <strong>ℹ️ Tips</strong><br>
        • Click any <span style="background:#fef3c7;padding:2px 6px;border-radius:4px;font-family:monospace;">[citation]</span> to see the source<br>
        • Ask follow-up questions for deeper info<br>
        • Use specific terms for better results
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # How it works button
    if st.button("🔍 How It Works", use_container_width=True):
        st.session_state.show_how_it_works = True

# How it works section (using expander for compatibility with older Streamlit)
if st.session_state.get('show_how_it_works', False):
    st.markdown("---")
    with st.container():
        st.markdown("### 🔍 How FAR Bot Works")
        # Image path - check both locations
        image_path = "how_it_works.png"
        if not os.path.exists(image_path):
            image_path = "../how_it_works.png"
        if os.path.exists(image_path):
            st.image(image_path, use_column_width=True)
        else:
            st.markdown("""
            **FAR Bot uses a RAG (Retrieval-Augmented Generation) pipeline:**
            1. **Vector Search**: Your question is converted to embeddings and matched against 3,893 FAR sections
            2. **Context Retrieval**: The most relevant FAR text chunks are retrieved
            3. **AI Generation**: GPT-4 reads the actual FAR text and generates an accurate, cited answer
            """)
        if st.button("✕ Close", key="close_how_it_works"):
            st.session_state.show_how_it_works = False
            st.rerun()
    st.markdown("---")

# Main content
if st.session_state.chatbot is None:
    st.error("Please wait for the chatbot to load...")
    st.stop()

# Display chat history
for i, entry in enumerate(st.session_state.chat_history):
    render_chat_message(entry, i, len(st.session_state.chat_history))

# Chat input
st.markdown("## 💬 Ask a Question")

# Handle queued questions
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
    placeholder = "Ask about FAR regulations, thresholds, procedures..."
    if st.session_state.chatbot and st.session_state.chatbot.conversation.current_topics:
        topic = st.session_state.chatbot.conversation.current_topics[0]
        placeholder = f"Follow up on {topic}, or ask something new..."
    
    question = st.text_input("Your question:", placeholder=placeholder, key="q_input")

col1, col2 = st.columns([1, 5])
with col1:
    ask_btn = st.button("🚀 Ask", type="primary")

should_process = process_question or (ask_btn and question.strip() and question != st.session_state.last_processed_question)

if should_process and st.session_state.chatbot:
    with st.status("🔍 Processing your question...", expanded=True) as status:
        st.write("📊 Analyzing query...")
        time.sleep(0.3)
        
        st.write("🔎 Searching FAR database...")
        time.sleep(0.3)
        
        st.write("📚 Gathering relevant sections...")
        time.sleep(0.3)
        
        st.write("🤖 Generating response with GPT-4 Turbo...")
        
        try:
            result = st.session_state.chatbot.chat(question, top_k=None)
            
            response = result['response']
            suggestions = result['suggestions']
            topics = result['topics']
            sections = result['sections']
            search_results = result.get('search_results', [])
            analysis = result.get('query_analysis', {})
            context_size = result.get('context_size', 0)
            model_used = result.get('model_used', 'gpt-4-turbo')
            
            timestamp = datetime.now().strftime("%H:%M")
            st.session_state.chat_history.append((
                question, response, suggestions, topics, sections, 
                search_results, timestamp, analysis, context_size, model_used
            ))
            
            st.session_state.last_processed_question = question
            status.update(label="✅ Complete!", state="complete")
            
        except Exception as e:
            st.error(f"Error: {str(e)}")
            logger.error(f"Chat error: {e}")
            status.update(label="❌ Error", state="error")
    
    st.rerun()

# Footer
st.markdown("---")
st.markdown("""
<div style="text-align:center;color:#718096;padding:1rem;">
    🏛️ FAR Chatbot | Powered by GPT-4 Turbo | Click citations to view sources
</div>
""", unsafe_allow_html=True)
