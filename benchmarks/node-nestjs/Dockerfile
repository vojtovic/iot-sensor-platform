FROM node:20-slim

WORKDIR /app
COPY package.json .
RUN npm install --omit=dev
COPY ingest.js .

# Konfigurace přes env (MQTT_HOST, DSN, BATCH_SIZE, FLUSH_MS, …) — viz ingest.js.
CMD ["node", "ingest.js"]
