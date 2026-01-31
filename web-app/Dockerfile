FROM python:3.12-slim

WORKDIR /app

RUN mkdir -p /data

ENV PYTHONUNBUFFERED=1
ENV DATABASE_PATH=/data/pruef.db

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "run.py"]
