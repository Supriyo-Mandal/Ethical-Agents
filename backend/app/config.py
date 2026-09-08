from pathlib import Path

UPLOAD_DIRECTORY = Path(__file__).resolve().parent.parent / "uploads"
REPORT_DIRECTORY = Path(__file__).resolve().parent.parent / "reports"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_BATCH_FILES = 10
