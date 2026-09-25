from pathlib import Path
import os

UPLOAD_DIRECTORY = Path(__file__).resolve().parent.parent / "uploads"
REPORT_DIRECTORY = Path(__file__).resolve().parent.parent / "reports"
DATABASE_URL = os.getenv("DATABASE_URL", "")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_BATCH_FILES = 10
