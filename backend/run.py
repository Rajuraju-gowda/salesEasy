"""Entry point script for SalesEasy Copilot Backend."""
import os
import sys

# Ensure backend directory is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import uvicorn
from app.api import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"\n" + "=" * 60)
    print(f"🚀 SalesEasy Copilot Backend is starting on http://localhost:{port}")
    print(f"📊 Interactive UI: http://localhost:{port}/")
    print(f"📑 API Docs:      http://localhost:{port}/docs")
    print(f"=" * 60 + "\n")
    uvicorn.run("app.api:app", host=host, port=port, reload=False)

