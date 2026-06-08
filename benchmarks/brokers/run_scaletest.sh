#!/usr/bin/env bash
# Test škálovatelnosti počtu spojení přes vybrané brokery.
#
# Použití:
#   ./run_scaletest.sh                      # všechny brokery
#   ./run_scaletest.sh mosquitto emqx
#   COUNTS=1000,5000,10000 ./run_scaletest.sh
set -euo pipefail

cd "$(dirname "$0")"
INFRA="../../infra"
PY=".venv/bin/python"

BROKERS="${*:-emqx mosquitto nanomq hivemq vernemq rabbitmq artemis}"
COUNTS="${COUNTS:-1000,5000,10000}"

mkdir -p results
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="results/scaletest-$STAMP.md"

{
  echo "# Test škálovatelnosti spojení — $STAMP"
  echo
  echo "Cílové počty souběžných spojení: $COUNTS (concurrency 300)."
  echo
} | tee "$OUT"

ready() {
  for _ in $(seq 1 60); do
    docker run --rm --network host eclipse-mosquitto \
      mosquitto_pub -h localhost -t scale/hc -m x >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

for b in $BROKERS; do
  echo "════════ $b ════════"
  "$INFRA/broker.sh" "$b" --no-platform
  ready || { echo "($b nenaběhl)" | tee -a "$OUT"; continue; }
  "$PY" -m brokerbench.scaletest --broker "$b" --container "iot-$b" \
    --counts "$COUNTS" --concurrency 300 | tee -a "$OUT"
  echo | tee -a "$OUT"
done

"$INFRA/broker.sh" down
echo
echo "Hotovo: $OUT"
