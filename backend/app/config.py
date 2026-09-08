from pathlib import Path
import os

UPLOAD_DIRECTORY = Path(__file__).resolve().parent.parent / "uploads"
REPORT_DIRECTORY = Path(__file__).resolve().parent.parent / "reports"
DATABASE_URL = os.getenv("DATABASE_URL", "")
OBJECT_STORAGE_ENDPOINT = os.getenv("OBJECT_STORAGE_ENDPOINT", "")
OBJECT_STORAGE_BUCKET = os.getenv("OBJECT_STORAGE_BUCKET", "")
OBJECT_STORAGE_ACCESS_KEY = os.getenv("OBJECT_STORAGE_ACCESS_KEY", "")
OBJECT_STORAGE_SECRET_KEY = os.getenv("OBJECT_STORAGE_SECRET_KEY", "")
OBJECT_STORAGE_REGION = os.getenv("OBJECT_STORAGE_REGION", "us-east-1")
