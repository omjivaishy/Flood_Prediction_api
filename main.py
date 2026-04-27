"""
main.py  — entry point
Run: python main.py
"""

import os
import gdown
import uvicorn
from app.config import settings
from app.main import app  # noqa: F401

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.pkl")
GDRIVE_FILE_ID = "1k-ltY3Vi1rHa4iXUuxulpdo7mZ0x3_-c"

if not os.path.exists(MODEL_PATH):
    print("Downloading model.pkl from Google Drive (~144MB, please wait)...")
    gdown.download(
        f"https://drive.google.com/uc?id={GDRIVE_FILE_ID}",
        MODEL_PATH,
        quiet=False,
        fuzzy=True,
    )
    print("model.pkl downloaded successfully.")
else:
    print("model.pkl already exists, skipping download.")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
