#!/usr/bin/env bash
# Benchmark backend stacků (Fáze 3): pro každý kandidát build image → start
# kontejner (na compose síti, připojený k emqx + timescaledb) → změř zvenčí
# (brokerbench.stackbench: zátěž + metriky z DB + cgroup CPU/RAM) → stop.
#
# Použití:
#   ./run_stacks.sh                 # všechny postavené stacky
#   ./run_stacks.sh python          # jen vybrané
#   RATES=1000,5000 REPEAT=2 ./run_stacks.sh python dotnet
#
# Adresáře stacků: python→python-fastapi, dotnet→dotnet, node→node-nestjs,
# java→java-spring. Měří se jen ty, které mají Dockerfile.
set -euo pipefail

cd "$(dirname "$0")"
INFRA="../../infra"
PY=".venv/bin/python"
NET="iot-sensor-platform_default"
DSN_HOST="postgresql://iot:iot-dev@localhost:5432/iot"
DSN_NET="postgresql://iot:iot-dev@timescaledb:5432/iot"

declare -A DIR=( [python]=python-fastapi [dotnet]=dotnet [node]=node-nestjs [java]=java-spring )

STACKS="${*:-python dotnet node java}"
RATES="${RATES:-1000,2500,5000,7500,10000}"
DURATION="${DURATION:-8}"
CLIENTS="${CLIENTS:-20}"
REPEAT="${REPEAT:-1}"

mkdir -p results
STAMP="$(date +%Y%m%d-%H%M%S)"

echo "════════ nahazuji EMQX + TimescaleDB ════════"
"$INFRA/broker.sh" emqx
for _ in $(seq 1 60); do
  docker exec iot-timescaledb pg_isready -U iot >/dev/null 2>&1 && break; sleep 2
done
docker stop iot-grafana >/dev/null 2>&1 || true
echo "  seed $CLIENTS bench zařízení…"
"$PY" -c "import asyncio; from brokerbench.pipeline import seed_devices; \
          asyncio.run(seed_devices('$DSN_HOST', $CLIENTS))"

for s in $STACKS; do
  d="${DIR[$s]:-}"
  if [ -z "$d" ] || [ ! -f "../$d/Dockerfile" ]; then
    echo "── $s: chybí ../$d/Dockerfile, přeskakuji"; continue
  fi
  echo "════════ stack: $s ($d) ════════"
  docker build -t "iot-ingest-$s" "../$d" >/dev/null
  docker rm -f "iot-ingest-$s" >/dev/null 2>&1 || true
  docker run -d --name "iot-ingest-$s" --network "$NET" \
    -e MQTT_HOST=emqx -e DSN="$DSN_NET" -e MQTT_TOPIC='bench/#' \
    "iot-ingest-$s" >/dev/null
  sleep 5   # ať se služba připojí a načte kanály
  "$PY" -m brokerbench.stackbench --stack "$s" --container "iot-ingest-$s" \
    --dsn "$DSN_HOST" --rates "$RATES" --duration "$DURATION" \
    --clients "$CLIENTS" --repeat "$REPEAT" --warmup \
    --json "results/stack-$s-$STAMP.json"
  docker rm -f "iot-ingest-$s" >/dev/null 2>&1 || true
done

"$INFRA/broker.sh" down
echo
echo "Hotovo. Grafy: $PY -m brokerbench.export  (série stack-* v pipeline grafech)"
