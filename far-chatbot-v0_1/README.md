# FAR Chatbot 🏛️
*Federal Acquisition Regulation Assistant with AI-Powered Search*

---

## 🎯 High-Level Overview (Executive Summary)

The FAR Chatbot is an **intelligent assistant** that helps government procurement professionals navigate the complex Federal Acquisition Regulation (FAR). Instead of manually searching through thousands of pages of regulations, users can ask natural language questions and receive accurate, cited answers in seconds.

**What it does:**
- Answers questions about federal procurement regulations
- Provides proper citations to specific FAR sections
- Explains complex regulatory concepts in plain language
- Maintains conversation context for follow-up questions

**Key Benefits:**
- ⚡ **Fast**: Get answers in 2-5 seconds vs. hours of manual research
- 🎯 **Accurate**: AI-powered search with proper regulatory citations
- 💬 **Conversational**: Ask follow-up questions naturally
- 📱 **Accessible**: Web interface works on any device

**Perfect for:** Contracting officers, procurement specialists, vendors, legal teams, and anyone working with federal acquisitions.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up Environment
Copy the example environment file and add your API key:
```bash
cp .env.example .env
```

Then edit `.env` and add your actual OpenAI API key:
```
OPENAI_API_KEY=your_actual_api_key_here
```

### 3. Validate Setup
Run the setup checker to ensure everything is configured correctly:
```bash
python setup_check.py
```

### 4. Launch Web UI
```bash
python run_chatbot_ui.py
```

The web interface will open at `http://localhost:8501`

## 💬 Sample Questions

- "What are small business set-asides?"
- "What is the simplified acquisition threshold?"
- "How do I protest a contract award?"
- "What are cost accounting standards?"
- "When can I use sole source procurement?"

## 🛠️ Command Line Usage

### Interactive Chat
```bash
cd src
python far_chatbot.py
```

### Single Query
```bash
cd src
python far_chatbot.py --query "What are small business set-asides?"
```

### Run Tests
```bash
python -m pytest tests/
```

---

## 📁 Project Structure

```
far-chatbot-clean/
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── setup_check.py           # Environment validation
├── run_chatbot_ui.py        # Launch script for web UI
├── .env.example             # Environment template
├── .gitignore              # Git ignore rules
├── src/                    # Core application code
│   ├── far_chatbot.py      # Main chatbot class
│   ├── streamlit_app.py    # Web interface
│   └── far_chatbot_web.py  # Web-specific functionality
├── data/                   # FAR regulation data
│   ├── faiss_index.index  # Vector database
│   ├── texts.txt          # Text chunks
│   └── README.md          # Data documentation
├── tests/                  # Test suite
│   ├── test_chatbot.py    # Core functionality tests
│   └── __init__.py
├── docs/                   # Documentation
│   ├── INDEX.md           # Documentation index
│   ├── DESIGN.md          # Technical design
│   ├── executive_overview.md
│   ├── overview_design.md
│   ├── production_design.md
│   └── GPT5_Enhancement_Summary.md
└── config/                 # Configuration files
    └── .env.example       # Environment template
```

This clean structure separates concerns and makes the project easy to navigate and maintain.