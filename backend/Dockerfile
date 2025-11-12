# Dockerfile (Backend)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libmecab-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first for caching
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip
RUN pip --no-cache-dir install -r /app/backend/requirements.txt

# Copy project
COPY . /app

# Create upload dir
RUN mkdir -p /app/uploads

ENV UPLOAD_DIR=/app/uploads
ENV FRONTEND_URL=http://localhost:3000

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
