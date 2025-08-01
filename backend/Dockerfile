FROM python:3.12-slim

# ---------- system deps ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential tesseract-ocr libtesseract-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---------- Python deps ----------
COPY requirements.txt .
ARG PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt \
    && rm -rf /root/.cache/pip          # throw away the wheel cache
# ---------- project code ----------
COPY . /app/backend
WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]