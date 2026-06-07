# simulator/

Sensor simulator / generátor zátěže — **páteř všech testů** (TESTING.md §4) a
zároveň náhrada za reálné jednotky (body 8–9) v semestrálce.

Musí umět:

- N virtuálních zařízení (každé vlastní `device_id`, topic, `seq`),    ✅
- nastavitelnou frekvenci a velikost payloadu,                          ✅ (frekvence)
- rampu (10 → 100 → 1000 … zařízení),                                   ⏳ navazující
- simulaci výpadku + replay z bufferu (s navazujícím `seq`),            ⏳ navazující
- volitelně chybné zprávy (poškozený JSON, mimo rozsah),               ⏳ navazující
- `--seed` pro opakovatelné běhy.                                       ✅

Stav (Fáze 2): hotové MVP — N zařízení, frekvence, `--seed`, publikace
telemetrie dle [ROADMAP §6](../ROADMAP.md#6-návrh-protokolu-skica-bod-6).
Rampa / výpadek+replay / chybné zprávy přijdou se zátěžovými a fault-injection
testy (TESTING.md §4).

## Instalace

```bash
cd simulator/
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Spuštění

Nejdřív musí běžet broker (`cd ../infra && docker compose up -d`).

```bash
# 2 zařízení, 1 Hz, do Ctrl+C
python -m simulator

# 100 zařízení, 5 zpráv/s, běh 30 s
python -m simulator --devices 100 --rate 5 --duration 30

# přesně 5 zpráv na zařízení, opakovatelně
python -m simulator --devices 2 --count 5 --seed 1
```

| Přepínač | Default | Význam |
|---|---|---|
| `--devices N` | 2 | počet virtuálních zařízení (id `esp32-sim-001`…) |
| `--broker H:P` | `localhost:1883` | adresa MQTT brokeru |
| `--rate Hz` | 1.0 | zpráv za sekundu na zařízení |
| `--duration S` | ∞ | délka běhu (jinak do Ctrl+C) |
| `--count N` | ∞ | max zpráv na zařízení |
| `--seed N` | náhodný | seed RNG pro opakovatelnost |

> Pro 2 zařízení sedí `device_id` na seed v DB (`esp32-sim-001/002`), takže
> telemetrie odpovídá kanálům v `infra/timescale/init/03_seed.sql`.

## Testy

```bash
pytest                      # unit testy (payload, model zařízení) — bez brokeru
```

Ověření publikace proti běžícímu brokeru (subscriber přes kontejner):

```bash
docker run --rm --network host eclipse-mosquitto \
  timeout 8 mosquitto_sub -h localhost -t 'v1/dev/+/telemetry' -v &
python -m simulator --devices 2 --count 5 --seed 1
```
