#!/usr/bin/env bash
# Přepne aktivní MQTT broker. Vždy běží jen jeden — všechny sdílí port 1883,
# takže simulátor pořád míří na localhost:1883.
#
# Použití:
#   ./broker.sh <broker> [--no-platform]   # přepne na broker (default i s platformou)
#   ./broker.sh list                       # vypíše dostupné brokery
#   ./broker.sh down                       # zastaví všechno
#
# Pozn.: pokud ještě nemáš práva na docker bez sudo (čerstvě přidaná skupina),
# spusť přes:  sg docker -c './broker.sh emqx'
set -euo pipefail

cd "$(dirname "$0")"

BROKERS="emqx mosquitto nanomq hivemq vernemq rabbitmq artemis"

usage() {
  echo "Použití: ./broker.sh <$(echo "$BROKERS" | tr ' ' '|')> [--no-platform]"
  echo "         ./broker.sh list      # dostupné brokery"
  echo "         ./broker.sh down      # zastaví vše"
  exit 1
}

cmd="${1:-}"
case "$cmd" in
  "" | -h | --help) usage ;;
  list) echo "$BROKERS" | tr ' ' '\n'; exit 0 ;;
  down) docker compose --profile '*' down; exit 0 ;;
esac

if ! printf ' %s ' "$BROKERS" | grep -q " $cmd "; then
  echo "Neznámý broker: $cmd"
  usage
fi

profiles="platform,$cmd"
[ "${2:-}" = "--no-platform" ] && profiles="$cmd"

echo "→ zastavuji běžící služby…"
docker compose --profile '*' down

echo "→ spouštím broker '$cmd' (profily: $profiles)…"
COMPOSE_PROFILES="$profiles" docker compose up -d

echo
echo "Broker '$cmd' běží na tcp://localhost:1883"
case "$profiles" in
  *platform*) echo "Platforma: TimescaleDB :5432 · Grafana http://localhost:3000" ;;
esac
