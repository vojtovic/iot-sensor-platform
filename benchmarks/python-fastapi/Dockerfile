FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ingest.py .

# Konfigurace přes env (MQTT_HOST, DSN, BATCH_SIZE, FLUSH_MS, …) — viz ingest.py.
CMD ["python", "-u", "ingest.py"]
