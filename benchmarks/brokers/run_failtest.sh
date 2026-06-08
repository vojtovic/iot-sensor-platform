#!/usr/bin/env bash
# Test spolehlivosti při výpadku přes vybrané brokery.
# Pro každý broker: kontrola (bez restartu) + ostrý test (s restartem).
#
# Použití:
#   ./run_failtest.sh                 # všechny brokery
#   ./run_failtest.sh mosquitto hivemq
#   N=1000 ./run_failtest.sh
set -euo pipefail

cd "$(dirname "$0")"
INFRA="../../infra"
PY=".venv/bin/python"

BROKERS="${*:-emqx mosquitto nanomq hivemq vernemq rabbitmq artemis}"
N="${N:-500}"

mkdir -p results
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="results/failtest-$STAMP.md"

{
  echo "# Test výpadku brokeru — $STAMP"
  echo
  echo "N=$N zpráv (seq 1..N), QoS 1, trvalá session. Restart = \`docker restart\`."
  echo
  echo "| Broker | bez restartu (ztráta/dup) | s restartem (ztráta/dup) | persistuje? |"
  echo "|---|---|---|---|"
} | tee "$OUT"

ready() {
  for _ in $(seq 1 60); do
    docker run --rm --network host eclipse-mosquitto \
      mosquitto_pub -h localhost -t fail/hc -m x >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

for b in $BROKERS; do
  echo "════════ $b ════════"
  "$INFRA/broker.sh" "$b" --no-platform
  ready || { echo "| $b | nenaběhl | — | — |" | tee -a "$OUT"; continue; }

  # jeden běh dělá kontrolu i restart a zapíše JSON
  out=$("$PY" -m brokerbench.failtest --broker "$b" --n "$N" --container "iot-$b" \
        --json "results/failtest-$b-$STAMP.json" 2>/dev/null)
  ctrl=$(echo "$out" | grep -i 'kontrola' | sed -E 's/.*ztráta ([0-9]+).*duplikáty ([0-9]+)/\1\/\2/')
  rest=$(echo "$out" | grep -i 'S RESTARTEM' | sed -E 's/.*ztráta ([0-9]+).*duplikáty ([0-9]+)/\1\/\2/')

  lost_rest="${rest%%/*}"
  if [ "$lost_rest" = "0" ]; then pers="✅ ano"; else pers="❌ ne"; fi

  echo "| $b | $ctrl | $rest | $pers |" | tee -a "$OUT"
done

"$INFRA/broker.sh" down
echo
echo "Hotovo: $OUT"
