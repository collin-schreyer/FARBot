# FAR Chatbot Data Files

This directory contains the processed FAR (Federal Acquisition Regulation) data files required for the chatbot to function.

## Files

### `faiss_index.index`
- **Type**: FAISS vector database index
- **Size**: ~50MB
- **Content**: 3,893 pre-computed embeddings of FAR sections
- **Format**: Binary FAISS IndexFlatL2 format
- **Dimensions**: 384 (SentenceTransformer output size)

### `texts.txt`
- **Type**: Plain text file
- **Content**: Corresponding text chunks for each vector in the FAISS index
- **Format**: One text chunk per line
- **Encoding**: UTF-8
- **Lines**: 3,893 (matches the number of vectors)

## Usage

These files are automatically loaded by the `FARChatbot` class:

```python
from src.far_chatbot import FARChatbot

# Initialize chatbot with data files
chatbot = FARChatbot(
    faiss_index_path="data/faiss_index.index",
    texts_path="data/texts.txt"
)
```

## Data Processing

The original FAR HTML files were processed through the following pipeline:

1. **HTML Parsing**: Extract text content from DITA HTML files
2. **Text Chunking**: Split into semantic chunks (~1000 characters each)
3. **Embedding Generation**: Create 384-dimensional vectors using SentenceTransformer
4. **Index Creation**: Build FAISS index for fast similarity search

## Requirements

- **FAISS**: For loading and searching the vector index
- **SentenceTransformers**: For encoding queries (must match the model used during indexing)
- **NumPy**: For vector operations

## File Integrity

Both files must be present and correspond to each other:
- Line N in `texts.txt` corresponds to vector N in `faiss_index.index`
- Any modification to one file requires regenerating the other
- The total number of vectors and text lines must match exactly

## Regeneration

If you need to regenerate these files from source FAR documents, you would need:
1. Original FAR HTML/XML files
2. Text processing pipeline
3. SentenceTransformer model for embedding generation
4. FAISS for index creation

*Note: The original source files and processing scripts are not included in this clean distribution.*