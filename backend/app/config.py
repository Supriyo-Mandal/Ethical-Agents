from pathlib import Path
import os

UPLOAD_DIRECTORY = Path(__file__).resolve().parent.parent / "uploads"
REPORT_DIRECTORY = Path(__file__).resolve().parent.parent / "reports"
DATABASE_URL = os.getenv("DATABASE_URL", "")