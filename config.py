"""
Configuration file for FAR Chatbot
"""
import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).parent

# Data paths
DATA_DIR = BASE_DIR / "dita_html"
FAISS_INDEX_PATH = DATA_DIR / "faiss_index.index"
TEXTS_PATH = DATA_DIR / "texts.txt"

# Environment variables
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
GSAI_ENDPOINT_URL = os.getenv('GSAI_ENDPOINT_URL')
GSAI_API_KEY = os.getenv('GSAI_API_KEY')

# Model settings
DEFAULT_MODEL = 'paraphrase-MiniLM-L6-v2'
USE_GPT5 = True

# Validate required files exist
def validate_setup():
    """Validate that required files exist"""
    missing_files = []
    
    if not FAISS_INDEX_PATH.exists():
        missing_files.append(str(FAISS_INDEX_PATH))
    
    if not TEXTS_PATH.exists():
        missing_files.append(str(TEXTS_PATH))
    
    if not OPENAI_API_KEY and not GSAI_API_KEY:
        missing_files.append(".env file with OPENAI_API_KEY or GSAI_API_KEY")
    
    return missing_files

if __name__ == "__main__":
    missing = validate_setup()
    if missing:
        print("❌ Missing required files:")
        for file in missing:
            print(f"  - {file}")
        print("\n📖 See private_data/README.md for setup instructions")
    else:
        print("✅ All required files found!")