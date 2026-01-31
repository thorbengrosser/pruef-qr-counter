FROM python:3.12-slim

WORKDIR /app

# Create data directory for SQLite (mount volume at /data in production)
RUN mkdir -p /data

ENV PYTHONUNBUFFERED=1
ENV DATABASE_PATH=/data/pruef.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY web-app/ ./web-app/
WORKDIR /app/web-app

EXPOSE 5000

CMD ["python", "run.py"]
