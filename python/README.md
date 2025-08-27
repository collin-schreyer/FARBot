# FAR Chatbot 🏛️

A Retrieval-Augmented Generation (RAG) chatbot that searches through Federal Acquisition Regulation (FAR) documents and provides accurate responses with proper citations.

## Features

- **Semantic Search**: Uses SentenceTransformers to find relevant FAR sections
- **FAISS Vector Database**: Fast similarity search through 3,893 FAR sections
- **Automatic Citations**: Provides proper FAR section references
- **Multiple Interfaces**: Command-line, interactive chat, and web interface
- **OpenAI Integration**: Optional GPT-powered responses for enhanced answers

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Verify Files Exist**:
   - FAISS index: `/Users/collinschreyer/GSA/FAR_BOT/dita_html/faiss_index.index`
   - Texts file: `/Users/collinschreyer/GSA/FAR_BOT/dita_html/texts.txt`

3. **Optional - OpenAI API Key**:
   ```bash
   export OPENAI_API_KEY="your-api-key-here"
   ```

## Usage

### 1. Command Line (Single Query)
```bash
python far_chatbot.py --query "What are small business set-asides?"
```

### 2. Interactive Chat
```bash
python far_chatbot.py
```

### 3. Web Interface
```bash
streamlit run far_chatbot_web.py
```

### 4. Test the System
```bash
python test_chatbot.py
```

## How It Works

1. **Query Processing**: User question is encoded using SentenceTransformers
2. **Semantic Search**: FAISS finds the most similar FAR sections
3. **Context Retrieval**: Relevant sections are retrieved with similarity scores
4. **Response Generation**: 
   - With OpenAI: GPT generates contextual response with citations
   - Without OpenAI: Returns formatted search results with citations
5. **Citation Extraction**: Automatically extracts FAR section numbers for references

## Example Queries

- "What are the requirements for small business set-asides?"
- "How do I handle contract modifications?"
- "What is the process for bid protests?"
- "Tell me about cost accounting standards"
- "What are the competitive bidding requirements?"

## Architecture

```
User Query
    ↓
SentenceTransformer (Encoding)
    ↓
FAISS Index (Similarity Search)
    ↓
Context Retrieval (Top-K Results)
    ↓
Response Generation (OpenAI/Fallback)
    ↓
Cited Response
```

## Files

- `far_chatbot.py` - Main chatbot class and CLI interface
- `far_chatbot_web.py` - Streamlit web interface
- `test_chatbot.py` - Test script with sample queries
- `vectorize_text.py` - Script that created the vector database
- `requirements.txt` - Python dependencies

## Configuration

You can customize the chatbot behavior by modifying these parameters:

- `top_k`: Number of documents to retrieve (default: 5)
- `model_name`: SentenceTransformer model (default: 'paraphrase-MiniLM-L6-v2')
- `temperature`: OpenAI response creativity (default: 0.3)
- `max_tokens`: Maximum response length (default: 500)

## Troubleshooting

1. **"Failed to load chatbot"**: Check that FAISS index and texts files exist
2. **"No OpenAI API key"**: Either set the environment variable or use retrieval-only mode
3. **Import errors**: Run `pip install -r requirements.txt`
4. **Slow responses**: Reduce `top_k` parameter or use a smaller model

## Performance

- **Index Size**: 3,893 FAR sections
- **Vector Dimensions**: 384 (SentenceTransformer)
- **Search Speed**: ~10ms per query
- **Memory Usage**: ~50MB for loaded models and index

## Next Steps

- Add conversation memory for multi-turn dialogues
- Implement query expansion for better search results
- Add support for document upload and indexing
- Create API endpoints for integration
- Add more sophisticated citation formatting