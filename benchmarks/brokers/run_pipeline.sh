#!/usr/bin/env bash
# End-to-end pipeline benchmark: broker → ingestion → TimescaleDB.
# Měří cenu ingestionu + perzistence oproti broker-only (POROVNEJ se stejným brokerem!).
#
# Použití:
#   ./run_pipeline.sh                       # default: emqx, QoS1, rampa 1k–10k
#   BROKER=mosquitto QOS=1 ./run_pipeline.sh
#   RATES=1000,5000,10000 BATCH=500 FLUSH_MS=100 ./run_pipeline.sh
#
# Pozn.: vyžaduje docker + extra závislost asyncpg (`pip install -e ".[dev,viz,db]"`).
#        Spouštěj na STEJNÉM stroji jako broker-only baseline (férové srovnání).
set -euo pipefail

cd "$(dirname "$0")"
INFRA="../../infra"
PY=".venv/bin/python"

BROKER="${BROKER:-emqx}"
RATES="${RATES:-1000,2500,5000,7500,10000}"
DURATION="${DURATION:-8}"
CLIENTS="${CLIENTS:-20}"
QOS="${QOS:-1}"
REPEAT="${REPEAT:-1}"
INFLIGHT="${INFLIGHT:-1000}"
SAMPLE_EVERY="${SAMPLE_EVERY:-20}"
BATCH="${BATCH:-500}"
FLUSH_MS="${FLUSH_MS:-100}"
DSN="${DSN:-postgresql://iot:iot-dev@localhost:5432/iot}"

mkdir -p results
STAMP="$(date +%Y%m%d-%H%M%S)"

echo "════════ pipeline: $BROKER → TimescaleDB ════════"
# broker.sh BEZ --no-platform → nahodí i TimescaleDB + Grafanu (potřebujeme DB)
"$INFRA/broker.sh" "$BROKER"

echo "  čekám na MQTT :1883…"
for _ in $(seq 1 60); do
  if docker run --rm --network host eclipse-mosquitto \
       mosquitto_pub -h localhost -t bench/hc -m x >/dev/null 2>&1; then break; fi
  sleep 2
done

echo "  čekám na TimescaleDB :5432…"
for _ in $(seq 1 60); do
  if docker exec iot-timescaledb pg_isready -U iot >/dev/null 2>&1; then break; fi
  sleep 2
done

"$PY" -m brokerbench.pipeline --broker "pipeline-$BROKER" \
  --db-container iot-timescaledb --dsn "$DSN" \
  --rates "$RATES" --duration "$DURATION" --clients "$CLIENTS" \
  --qos "$QOS" --repeat "$REPEAT" --inflight "$INFLIGHT" \
  --sample-every "$SAMPLE_EVERY" --batch-size "$BATCH" --flush-ms "$FLUSH_MS" \
  --reset --json "results/pipeline-$BROKER-qos$QOS-$STAMP.json"

echo
echo "Hotovo. Grafy (pipeline série vedle broker-only): $PY -m brokerbench.export"
echo "Porovnej 'pipeline-$BROKER' s broker-only sérií '$BROKER' (stejný broker)."
echo "Infra běží dál; zastav: $INFRA/broker.sh down"
