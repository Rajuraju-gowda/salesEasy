#!/usr/bin/env python3
"""Convenient root launcher for SalesEasy Copilot."""
import os
import sys

backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import uvicorn
from app.api import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    print("\n" + "=" * 65)
    print("  🚀 SalesEasy FMCG AI Sales Copilot")
    print(f"  🌐 Application & React UI: http://localhost:{port}")
    print(f"  📑 Interactive API Docs:   http://localhost:{port}/docs")
    print("=" * 65 + "\n")
    uvicorn.run("app.api:app", host=host, port=port, reload=False)
