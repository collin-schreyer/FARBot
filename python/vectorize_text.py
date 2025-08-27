import os
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import logging
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('vectorize_text.log'),
        logging.StreamHandler()
    ]
)

def parse_chunk_text(raw_text):
    """Parse the chunk text format with 'Heading:' and 'Text:' labels"""
    sections = []
    lines = raw_text.strip().split('\n')
    
    current_heading = None
    current_text_lines = []
    
    for line in lines:
        line = line.strip()
        if line.startswith('Heading: '):
            # Save previous section if exists
            if current_heading and current_text_lines:
                text_content = ' '.join(current_text_lines).strip()
                if text_content:
                    sections.append((current_heading, text_content))
            
            # Start new section
            current_heading = line[9:].strip()  # Remove 'Heading: '
            current_text_lines = []
            
        elif line.startswith('Text: '):
            # Start collecting text content
            text_content = line[6:].strip()  # Remove 'Text: '
            if text_content:
                current_text_lines.append(text_content)
                
        elif current_heading and line:  # Continue collecting text if we have a heading
            current_text_lines.append(line)
    
    # Don't forget the last section
    if current_heading and current_text_lines:
        text_content = ' '.join(current_text_lines).strip()
        if text_content:
            sections.append((current_heading, text_content))
    
    return sections

def vectorize_chunks(chunks, model):
    logging.info(f"Starting vectorize_chunks with {len(chunks)} chunk files")
    texts = []
    
    try:
        # Loop through the chunks and collect the text
        for file_idx, (file_name, raw_content) in enumerate(chunks):
            logging.info(f"Processing file {file_idx + 1}/{len(chunks)}: {file_name}")
            
            # Parse the raw text content
            if isinstance(raw_content, str):
                logging.debug(f"Parsing raw text content, length: {len(raw_content)}")
                sections = parse_chunk_text(raw_content)
                logging.info(f"Parsed {len(sections)} sections from {file_name}")
            else:
                logging.warning(f"Unexpected content type for {file_name}: {type(raw_content)}")
                continue
            
            section_count = 0
            for heading, section_text in sections:
                logging.debug(f"Processing section - Heading: '{heading}', Text length: {len(section_text)}")
                
                # Only process valid sections with more than a few characters
                if len(heading.strip()) > 0 and len(section_text.strip()) > 10:  # Minimum 10 chars
                    combined_text = f"{heading} {section_text}"
                    texts.append(combined_text)
                    section_count += 1
                    logging.debug(f"Added section - Heading: {heading}, Text: {section_text[:100]}...")
                else:
                    logging.warning(f"Skipping short section - Heading: '{heading}', Text length: {len(section_text)}")
            
            logging.info(f"Processed {section_count} valid sections from {file_name}")
        
        logging.info(f"Total texts collected: {len(texts)}")
        
        if len(texts) == 0:
            logging.error("No valid texts found to vectorize!")
            return [], []
        
        # Log sample texts
        for i, text in enumerate(texts[:3]):  # Show first 3 texts
            logging.info(f"Sample text {i+1}: {text[:150]}...")
        
        # Convert the text to embeddings using Sentence-BERT
        logging.info("Starting text encoding with SentenceTransformer...")
        embeddings = model.encode(texts)
        logging.info(f"Successfully generated {len(embeddings)} embeddings")
        
        # Check the shape of embeddings
        if len(embeddings) > 0:
            embedding_array = np.array(embeddings)
            logging.info(f"Embedding shape: {embedding_array.shape}")
            logging.info(f"Embedding dtype: {embedding_array.dtype}")
        else:
            logging.error("No embeddings generated!")
        
        return embeddings, texts
        
    except Exception as e:
        logging.error(f"Error in vectorize_chunks: {str(e)}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        return [], []

def save_faiss_index(embeddings, index_path):
    logging.info(f"Starting to save FAISS index to {index_path}")
    
    try:
        # Check if embeddings are empty
        if len(embeddings) == 0:
            logging.error("No embeddings found to save to FAISS")
            raise ValueError("No embeddings found to save to FAISS.")
        
        logging.info(f"Converting {len(embeddings)} embeddings to numpy array")
        # Convert embeddings to numpy array
        embeddings = np.array(embeddings).astype('float32')
        logging.info(f"Embeddings array shape: {embeddings.shape}, dtype: {embeddings.dtype}")
        
        # Ensure embeddings have the correct shape (2D)
        if embeddings.ndim != 2:
            logging.error(f"Invalid embedding dimensions: {embeddings.ndim}. Expected 2D array.")
            raise ValueError("Embeddings should have 2 dimensions: (num_embeddings, embedding_dimension).")
        
        # Create FAISS index
        logging.info(f"Creating FAISS IndexFlatL2 with dimension {embeddings.shape[1]}")
        index = faiss.IndexFlatL2(embeddings.shape[1])  # Using L2 distance
        
        logging.info("Adding embeddings to FAISS index")
        index.add(embeddings)
        logging.info(f"FAISS index now contains {index.ntotal} vectors")
        
        # Save the FAISS index to disk
        logging.info(f"Writing FAISS index to disk: {index_path}")
        faiss.write_index(index, index_path)
        logging.info(f"FAISS index successfully saved to {index_path}")
        
    except Exception as e:
        logging.error(f"Error saving FAISS index: {str(e)}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        raise

def save_texts(texts, texts_path):
    logging.info(f"Saving {len(texts)} texts to {texts_path}")
    
    try:
        # Save the texts corresponding to the embeddings (for reference)
        with open(texts_path, 'w', encoding='utf-8') as f:
            for i, text in enumerate(texts):
                f.write(f"{text}\n")
                if i < 3:  # Log first few texts
                    logging.debug(f"Saved text {i+1}: {text[:100]}...")
        
        logging.info(f"Successfully saved {len(texts)} texts to {texts_path}")
        
    except Exception as e:
        logging.error(f"Error saving texts: {str(e)}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        raise

def main():
    # Example usage
    chunks_dir = "/Users/collinschreyer/GSA/FAR_BOT/dita_html/chunks"  # Path to chunked text files
    faiss_index_path = "/Users/collinschreyer/GSA/FAR_BOT/dita_html/faiss_index.index"  # Path to save the FAISS index
    texts_path = "/Users/collinschreyer/GSA/FAR_BOT/dita_html/texts.txt"  # Path to save the texts

    logging.info("=== Starting vectorize_text.py ===")
    logging.info(f"Chunks directory: {chunks_dir}")
    logging.info(f"FAISS index path: {faiss_index_path}")
    logging.info(f"Texts path: {texts_path}")

    try:
        # Check if chunks directory exists
        if not os.path.exists(chunks_dir):
            logging.error(f"Chunks directory does not exist: {chunks_dir}")
            return
        
        # Read the chunked text from files
        logging.info(f"Reading chunk files from {chunks_dir}")
        extracted_texts = []
        
        chunk_files = [f for f in os.listdir(chunks_dir) if f.endswith('_chunks.txt')]
        logging.info(f"Found {len(chunk_files)} chunk files: {chunk_files}")
        
        for file_name in chunk_files:
            file_path = os.path.join(chunks_dir, file_name)
            logging.info(f"Reading file: {file_path}")
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                    logging.info(f"File {file_name}: {len(text)} characters")
                    logging.debug(f"First 200 chars of {file_name}: {text[:200]}")
                    extracted_texts.append((file_name, text))
            except Exception as e:
                logging.error(f"Error reading file {file_path}: {str(e)}")
                continue

        # Ensure extracted_texts isn't empty
        if not extracted_texts:
            logging.error("No text found in chunk files. Please ensure the chunked text files are correctly generated.")
            return
        else:
            logging.info(f"Successfully loaded {len(extracted_texts)} chunk files to process")

        # Initialize Sentence-BERT model
        logging.info("Initializing SentenceTransformer model: paraphrase-MiniLM-L6-v2")
        model = SentenceTransformer('paraphrase-MiniLM-L6-v2')
        logging.info("Model loaded successfully")

        # Vectorize chunks and get embeddings
        logging.info("Starting vectorization process")
        embeddings, texts = vectorize_chunks(extracted_texts, model)

        if len(embeddings) == 0 or len(texts) == 0:
            logging.error("No embeddings or texts generated. Stopping process.")
            return

        # Save the FAISS index and the texts
        logging.info("Saving FAISS index and texts")
        save_faiss_index(embeddings, faiss_index_path)
        save_texts(texts, texts_path)
        
        logging.info("=== vectorize_text.py completed successfully ===")

    except Exception as e:
        logging.error(f"Fatal error in main: {str(e)}")
        logging.error(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    main()
