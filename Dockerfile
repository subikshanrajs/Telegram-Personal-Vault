FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist the sqlite index across restarts if the platform gives you a volume
VOLUME ["/app/data"]
ENV DB_PATH=/app/data/vault.db

CMD ["python", "main.py"]
