#!/usr/bin/env python3

import os
import sys
import subprocess
from pathlib import Path


def check_requirements():
    """Check if all requirements are met."""
    print("🔍 Checking requirements...")
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ required")
        return False
    
    # Check if .env file exists
    if not Path(".env").exists():
        print("⚠️  .env file not found. Please copy env.example to .env and add your ChatGroq API key")
        return False
    
    # Check if required packages are installed
    try:
        import fastapi
        import uvicorn
        import httpx
        import loguru
        import dotenv
        print("✅ All required packages are installed")
        return True
    except ImportError as e:
        print(f"❌ Missing package: {e}")
        print("Please run: pip install -e .")
        return False


def start_server():
    """Start the FastAPI server."""
    print("🚀 Starting NVIDIA NeMo Guardrails API...")
    
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("DEBUG", "True").lower() == "true"
    
    print(f"📍 Server will be available at: http://{host}:{port}")
    print(f"📚 API documentation: http://{host}:{port}/docs")
    print(f"🔧 Debug mode: {debug}")
    print("\n" + "="*50)
    
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "main:app", 
            "--host", host, 
            "--port", str(port), 
            "--reload" if debug else "--no-reload"
        ])
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")


def main():
    """Main function."""
    print("🛡️  NVIDIA NeMo Guardrails API Startup")
    print("="*40)
    
    if not check_requirements():
        print("\n❌ Requirements check failed. Please fix the issues above.")
        sys.exit(1)
    
    print("\n✅ All requirements met!")
    start_server()


if __name__ == "__main__":
    main()
