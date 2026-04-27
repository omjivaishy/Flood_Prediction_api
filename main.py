"""
main.py  — entry point
Run: python main.py
"""

import uvicorn
from app.config import settings
from app.main import app  # noqa: F401

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
