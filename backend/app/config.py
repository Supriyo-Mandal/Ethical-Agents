from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()
import os
from dotenv import load_dotenv

UPLOAD_DIRECTORY = Path(__file__).resolve().parent.parent / "uploads"
REPORT_DIRECTORY = Path(__file__).resolve().parent.parent / "reports"

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "ethical_agents")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")