#!/usr/bin/env bash
# Orchestrátor broker benchmarku: projede vybrané brokery, každý spustí,
# počká na MQTT, odběhne rampu, výsledky uloží a nakonec vše zastaví.
#
# Použití:
#   ./run_all.sh                       # všechny brokery, default parametry
#   ./run_all.sh emqx mosquitto        # jen vybrané
#   RATES=1000,5000,10000 DURATION=8 ./run_all.sh
#
# Pozn.: vyžaduje docker (případně spouštěj přes `sg docker -c './run_all.sh'`).
set -euo pipefail

cd "$(dirname "$0")"
INFRA="../../infra"
PY=".venv/bin/python"

BROKERS="${*:-emqx mosquitto nanomq hivemq vernemq rabbitmq artemis}"
RATES="${RATES:-1000,2500,5000,7500,10000}"
DURATION="${DURATION:-6}"
CLIENTS="${CLIENTS:-20}"
SAMPLE_EVERY="${SAMPLE_EVERY:-50}"

mkdir -p results
STAMP="$(date +%Y%m%d-%H%M%S)"
SUMMARY="results/summary-$STAMP.md"

{
  echo "# Broker benchmark — $STAMP"
  echo
  echo "Parametry: rates=$RATES · duration=${DURATION}s · clients=$CLIENTS · qos=1 · sample_every=$SAMPLE_EVERY"
  echo
} > "$SUMMARY"

wait_for_mqtt() {
  for _ in $(seq 1 60); do
    if docker run --rm --network host eclipse-mosquitto \
         mosquitto_pub -h localhost -t bench/hc -m x >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  return 1
}

for b in $BROKERS; do
  echo "════════ $b ════════"
  "$INFRA/broker.sh" "$b" --no-platform
  echo "  čekám na MQTT na :1883…"
  if ! wait_for_mqtt; then
    echo "  ! $b nenaběhl včas, přeskakuji" | tee -a "$SUMMARY"
    continue
  fi
  "$PY" -m brokerbench --broker "$b" --container "iot-$b" \
    --rates "$RATES" --duration "$DURATION" --clients "$CLIENTS" \
    --sample-every "$SAMPLE_EVERY" --json "results/$b-$STAMP.json" \
    | tee -a "$SUMMARY"
done

"$INFRA/broker.sh" down
echo
echo "Hotovo. Souhrn: $SUMMARY"
