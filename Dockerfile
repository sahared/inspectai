FROM python:3.11-slim AS builder

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY backend/ .

ENV PORT=8080
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
