FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy Python dependency files first for better caching
COPY requirements.txt ./requirements.txt
COPY app/requirements.txt ./app/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

# Copy the project files
COPY app ./app
COPY backend ./backend
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]