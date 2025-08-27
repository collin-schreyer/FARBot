#!/usr/bin/env python3
"""
Setup validation script for FAR Chatbot
Run this to check if your environment is properly configured.
"""

import sys
from pathlib import Path
import os

def check_python_version():
    """Check Python version"""
    if sys.version_info < (3, 8):
        return False, f"Python 3.8+ required, found {sys.version}"
    return True, f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

def check_dependencies():
    """Check if required packages are installed"""
    required_packages = [
        'sentence_transformers',
        'faiss',
        'openai',
        'streamlit',
        'numpy',
        'python-dotenv'
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing.append(package)
    
    if missing:
        return False, f"Missing packages: {', '.join(missing)}"
    return True, "All required packages installed"

def check_data_files():
    """Check if data files exist"""
    base_dir = Path(__file__).parent
    data_dir = base_dir / "dita_html"
    
    required_files = [
        data_dir / "faiss_index.index",
        data_dir / "texts.txt"
    ]
    
    missing = []
    for file_path in required_files:
        if not file_path.exists():
            missing.append(str(file_path))
    
    if missing:
        return False, f"Missing data files: {', '.join(missing)}"
    return True, "All data files found"

def check_environment():
    """Check environment variables"""
    env_file = Path(__file__).parent / ".env"
    
    if not env_file.exists():
        return False, ".env file not found"
    
    # Load .env file
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        return False, "python-dotenv not installed"
    
    openai_key = os.getenv('OPENAI_API_KEY')
    gsai_key = os.getenv('GSAI_API_KEY')
    
    if not openai_key and not gsai_key:
        return False, "No API key found in .env (need OPENAI_API_KEY or GSAI_API_KEY)"
    
    if openai_key:
        return True, "OpenAI API key configured"
    else:
        return True, "GSAI API key configured"

def main():
    """Run all checks"""
    print("🔍 FAR Chatbot Setup Validation")
    print("=" * 40)
    
    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Data Files", check_data_files),
        ("Environment", check_environment)
    ]
    
    all_passed = True
    
    for name, check_func in checks:
        try:
            passed, message = check_func()
            status = "✅" if passed else "❌"
            print(f"{status} {name}: {message}")
            
            if not passed:
                all_passed = False
                
        except Exception as e:
            print(f"❌ {name}: Error - {e}")
            all_passed = False
    
    print("\n" + "=" * 40)
    
    if all_passed:
        print("🎉 Setup complete! You can now run the chatbot:")
        print("   python run_chatbot_ui.py")
    else:
        print("❌ Setup incomplete. Please fix the issues above.")
        print("📖 See README.md and private_data/README.md for help")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())