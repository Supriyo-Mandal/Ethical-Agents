from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
KNOWLEDGE_DIR = BASE_DIR / "app" / "knowledge"
REPORTS_DIR = BASE_DIR / "app" / "reports"
UPLOAD_DIR = BASE_DIR / "uploads"

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
MAX_FILE_SIZE_MB = 10
THRESHOLD = 0.7

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
