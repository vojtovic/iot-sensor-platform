#!/usr/bin/env bash
# End-to-end pipeline benchmark: broker → ingestion → TimescaleDB.
# Měří cenu ingestionu + perzistence oproti broker-only (POROVNEJ se stejným brokerem!).
#
# Použití:
#   ./run_pipeline.sh                       # default: emqx, QoS1, rampa 1k–10k, warm-up
#   BROKER=mosquitto QOS=1 ./run_pipeline.sh
#   RATES=1000,5000,10000 BATCH=500 FLUSH_MS=100 ./run_pipeline.sh
#   for f in 50 100 200; do FLUSH_MS=$f ./run_pipeline.sh; done   # křivka latence vs propustnost
#
# Pozn.: vyžaduje docker + extra `pip install -e ".[dev,viz,db]"` (asyncpg, psutil).
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
DRAIN="${DRAIN:-5}"
WARMUP="${WARMUP:-1}"
DSN="${DSN:-postgresql://iot:iot-dev@localhost:5432/iot}"

WARMUP_FLAG=""
[ "$WARMUP" = "1" ] && WARMUP_FLAG="--warmup"

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

# Férové měření: Grafana není potřeba a jen by ujídala CPU brokeru → zastavit.
docker stop iot-grafana >/dev/null 2>&1 || true
echo "  Grafana zastavena (uvolnění CPU pro férové srovnání s broker-only)"

"$PY" -m brokerbench.pipeline --broker "pipeline-$BROKER" \
  --db-container iot-timescaledb --dsn "$DSN" \
  --rates "$RATES" --duration "$DURATION" --clients "$CLIENTS" \
  --qos "$QOS" --repeat "$REPEAT" --inflight "$INFLIGHT" \
  --sample-every "$SAMPLE_EVERY" --batch-size "$BATCH" --flush-ms "$FLUSH_MS" \
  --drain "$DRAIN" $WARMUP_FLAG --reset \
  --json "results/pipeline-$BROKER-qos$QOS-$STAMP.json"

echo
echo "Hotovo. Grafy (pipeline série vedle broker-only): $PY -m brokerbench.export"
echo "Porovnej 'pipeline-$BROKER' s broker-only sérií '$BROKER' — POZOR: pro čistý"
echo "rozdíl přeměř i broker-only se zapnutou DB (broker.sh $BROKER), ať mají obě"
echo "varianty stejné běžící kontejnery."
echo "Infra běží dál; zastav: $INFRA/broker.sh down"
