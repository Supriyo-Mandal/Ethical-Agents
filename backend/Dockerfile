FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
COPY app/requirements.txt ./app/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY backend ./backend
COPY config ./config
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]