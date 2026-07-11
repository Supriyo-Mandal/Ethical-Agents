# semantic-risk-analyzer

This repository now follows a modular structure for a semantic multi-agent risk analysis platform.

## Structure

- FastAPI backend under app/
- Streamlit frontend under frontend/
- Knowledge repositories under app/knowledge/
- Tests under tests/

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
streamlit run frontend/app.py
```

## API

- POST /upload
- POST /analyze
- GET /output
- GET /reports