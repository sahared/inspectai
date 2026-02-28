# InspectAI Backend — Dockerfile for Google Cloud Run
# Multi-stage build for smaller image

# Stage 1: Build
FROM python:3.11-slim as builder

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages
COPY --from=builder /install /usr/local

# Copy application code
COPY backend/ .

# Cloud Run uses PORT env var (default 8080)
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

# Run with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
