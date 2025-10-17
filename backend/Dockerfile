FROM python:3.12-slim

# ---------- system deps ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential tesseract-ocr libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------- Python deps ----------
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt \
    && rm -rf /root/.cache/pip          # throw away the wheel cache
# ---------- project code ----------
COPY . /app/backend
WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
# backend/Dockerfile
CMD ["sh","-lc","python -m alembic -c app/alembic.ini upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]