#!/usr/bin/env python3
"""
Launch the FAR Chatbot Web UI
"""

import subprocess
import sys
import os

def main():
    print("🏛️ Starting FAR Chatbot Web UI...")
    print("📝 Loading environment variables...")
    print("🚀 Launching Streamlit app...")
    print("\n" + "="*50)
    print("🌐 The web interface will open in your browser")
    print("🔗 URL: http://localhost:8501")
    print("⏹️  Press Ctrl+C to stop the server")
    print("="*50 + "\n")
    
    try:
        # Change to python directory and run streamlit
        os.chdir('python')
        subprocess.run([
            sys.executable, '-m', 'streamlit', 'run', 'streamlit_app.py',
            '--server.port', '8501',
            '--server.address', 'localhost'
        ])
    except KeyboardInterrupt:
        print("\n👋 FAR Chatbot UI stopped. Goodbye!")
    except Exception as e:
        print(f"❌ Error starting UI: {e}")
        print("💡 Make sure you're in the project root directory")

if __name__ == "__main__":
    main()