#!/usr/bin/env python3
"""
Launch script for FAR Chatbot Web UI
"""

import subprocess
import sys
import os
from pathlib import Path

def main():
    """Launch the Streamlit web interface"""
    
    # Check if we're in the right directory
    if not Path("src/streamlit_app.py").exists():
        print("❌ Error: src/streamlit_app.py not found")
        print("Make sure you're running this from the far-chatbot-clean directory")
        return 1
    
    # Check if data files exist
    if not Path("data/faiss_index.index").exists() or not Path("data/texts.txt").exists():
        print("❌ Error: Data files not found in data/ directory")
        print("Run python setup_check.py to validate your setup")
        return 1
    
    print("🚀 Starting FAR Chatbot Web Interface...")
    print("📊 Loading 3,893 FAR sections...")
    print("🌐 Web interface will open at http://localhost:8501")
    print("\n" + "="*50)
    
    try:
        # Launch Streamlit
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", 
            "src/streamlit_app.py",
            "--server.port=8501",
            "--server.address=localhost",
            "--server.headless=false"
        ], check=True)
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error launching Streamlit: {e}")
        print("Make sure Streamlit is installed: pip install streamlit")
        return 1
    except KeyboardInterrupt:
        print("\n👋 FAR Chatbot stopped by user")
        return 0

if __name__ == "__main__":
    sys.exit(main())