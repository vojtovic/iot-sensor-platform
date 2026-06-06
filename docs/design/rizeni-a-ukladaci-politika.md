# Řízení zařízení, příkazy a ukládací politika

> Doplněk k [ROADMAP.md](../../ROADMAP.md) — rozpracovává body **4–7** o:
> vzdálené řízení senzorů, rozšíření konfigurace a **ukládací politiku**
> („report by exception" + heartbeat). Rozhodnutí o místě vynucení viz
> [ADR 0002](../adr/0002-vynuceni-ukladaci-politiky.md).

---

## 1. Vůdčí princip: politika centrálně, vynucení podle schopností

Systém je **modulární a heterogenní** (vlastní i cizí senzory) → cílem je
**sahat na senzory co nejméně**.

- **Politika a konfigurace se definují centrálně** (jeden zdroj pravdy: registry/backend).
- **Vynucení je adaptivní podle schopností zařízení:**
  - zařízení to umí (`edge_policy: true`) → backend mu pošle politiku v konfiguraci
    a ono **filtruje samo** (šetří přenos i baterii),
  - zařízení to neumí / cizí jednotka → posílá vše a **politiku aplikuje backend**
    při příjmu (rozhodne, co uložit).
- **Backend je vždy pojistka** — i u edge zařízení dělá agregace/downsampling a
  případná dodatečná pravidla.

Tím modularita zůstává zachovaná a **integrace cizích jednotek (bod 10)** nevyžaduje
zásah do jejich firmwaru.

---

## 2. Deklarace schopností při registraci

Zařízení při registraci pošle, co umí. Backend podle toho zvolí edge/backend vynucení.

```json
{
  "capabilities": {
    "edge_policy": true,
    "commands": ["start", "stop", "measure_now", "set_interval",
                 "set_policy", "reboot", "calibrate", "identify"],
    "store_and_forward": { "supported": true, "capacity": 5000 },
    "max_channels": 8
  }
}
```

| Pole | Význam |
|---|---|
| `edge_policy` | umí lokálně vyhodnotit ukládací politiku? |
| `commands` | které příkazy zařízení podporuje |
| `store_and_forward` | umí bufferovat při výpadku a poslat znovu (bod 9) |
| `max_channels` | kolik kanálů/čidel zvládne |

> Cizí jednotka, která jen publikuje telemetrii, deklaruje `edge_policy: false`
> (nebo capabilities vůbec nepošle) → backend ji bere jako „raw" a filtruje za ni.

---

## 3. Konfigurace — žádaný stav (retained, verzovaná)

Doručena přes **retained** topic `config` (vzor device shadow/twin). Zařízení po
aplikaci potvrdí `config_version` ve `status`/`ack` → backend pozná, že konfigurace „dosedla".

```json
{
  "config_version": 7,
  "sample_interval_s": 10,
  "report_policy": { "...": "viz §4" },
  "calibration": { "co2": { "offset": -12 }, "temp": { "offset": 0.3 } }
}
```

> Pokud zařízení nepodporuje `edge_policy`, backend mu pošle jen `sample_interval_s`
> (případně nic) a `report_policy` si nechá u sebe.

---

## 4. Ukládací politika — „report by exception" + heartbeat

Přesně to, co dává smysl: neukládat celý den stejnou hodnotu, ale zachytit
**události** a občas potvrdit, že čidlo žije. Pravidla **per kanál**:

```json
{
  "report_policy": {
    "min_interval_s": 30,
    "heartbeat_s": 300,
    "deadband": 0.3,
    "thresholds": [
      { "op": ">", "value": 23, "hysteresis": 0.5 }
    ]
  }
}
```

| Pravidlo | Co dělá |
|---|---|
| `heartbeat_s` | ulož aspoň 1× za N s, i když se nic neděje (důkaz, že hodnota platí) |
| `thresholds` | ulož při překročení meze (např. > 23 °C) — s **hysterezí** |
| `deadband` | ulož při změně o víc než Δ od poslední uložené hodnoty |
| `min_interval_s` | neukládej častěji než X (proti záplavě) |

**Hystereze (důležité!):** bez ní by hodnota kmitající kolem 23,0 spustila ukládání
při každém vzorku. S hysterezí 0,5 se „nad" sepne při `> 23,0` a „pod" až při
`< 22,5` → ukládají se jen **přechody** (náběžná/sestupná hrana), což jsou ty
zajímavé události.

**Vyhodnocení (pseudokód, stejné na edge i na backendu):**

```python
def should_store(value, st, p, now):
    triggers = []
    if now - st.last_ts >= p.heartbeat_s:
        triggers.append("heartbeat")
    if abs(value - st.last_value) >= p.deadband:
        triggers.append("deadband")
    for th in p.thresholds:                      # hystereze
        if not st.above[th] and value > th.value:
            st.above[th] = True;  triggers.append("rising")
        elif st.above[th] and value < th.value - th.hysteresis:
            st.above[th] = False; triggers.append("falling")

    # heartbeat obchází min_interval; jinak respektuj anti-flood
    if triggers and ("heartbeat" in triggers or now - st.last_ts >= p.min_interval_s):
        store(value); st.last_value = value; st.last_ts = now
```

> Předpoklad: `heartbeat_s >= min_interval_s`. I při edge-filteringu si backend může
> držet další agregace (continuous aggregates) pro plynulé grafy.

---

## 5. Příkazy — jednorázové akce (downlink)

**Příkaz ≠ konfigurace.** Konfigurace je *žádaný stav* (retained, drží se).
Příkaz je *jednorázová akce* (NEretained, s expirací) — jinak by se po reconnectu
přehrál starý příkaz.

| Příkaz | Účel |
|---|---|
| `start` / `stop` | spustit / zastavit měření |
| `measure_now` | změřit a poslat okamžitě |
| `set_interval` | změnit periodu vzorkování |
| `set_policy` | nastavit ukládací politiku (§4) |
| `calibrate` | kalibrace (offset/reference) |
| `reboot` | restart jednotky |
| `identify` | blikni LED / pípni (fyzická identifikace) |

**Příkaz (downlink, topic `cmd/{cmd}`):**

```json
{ "cmd_id": "f3a9-…", "cmd": "set_interval", "args": { "interval_s": 60 },
  "ts": 1717490000, "expiry_s": 120 }
```

**Potvrzení (uplink, topic `ack`):**

```json
{ "cmd_id": "f3a9-…", "status": "ok", "ts": 1717490002, "detail": null }
```
`status`: `ok` · `error` · `unsupported` (zařízení příkaz nezná).

- **Offline:** příkaz se **neretainuje**. Backend drží **frontu příkazů** a doručí
  při připojení (nebo MQTT 5 message expiry + persistent session). Po `expiry_s`
  → příkaz označen `expired`.
- **Bezpečnost:** ACL (velet smí jen oprávněný), **audit log** každého příkazu
  (kdo, kdy, co, výsledek).

---

## 6. Dopad na datový model

Rozšíření modelu z [ROADMAP §5](../../ROADMAP.md#5-návrh-datového-modelu-skica):

```
device_capabilities(device_id, json, updated_at)
measurement_policy(device_id|channel_id, json_policy, version, enforced_at: edge|backend)
command_log(cmd_id, device_id, cmd, args, issued_by, issued_at,
            status[pending|sent|acked|expired|error], acked_at, detail)
# device_config už existuje — rozšířen o report_policy a sample_interval
```

---

## 7. Dopad na API a správu (body 4–5)

| Endpoint | Účel |
|---|---|
| `POST /devices/{id}/commands` | vydej příkaz → vrátí `cmd_id`, stav sleduješ |
| `GET  /devices/{id}/commands/{cmd_id}` | stav příkazu (acked/expired/…) |
| `PUT  /devices/{id}/config` | nastav interval + politiku (verzováno) |
| `GET  /devices/{id}/capabilities` | co zařízení umí |

**UI (správa):** tlačítka příkazů, formulář politiky (práh, hystereze, heartbeat),
indikace **edge vs. backend** vynucení, a stav `config_version` (dosedla nová konfigurace?).

---

## 8. Rozsah a hranice

- **Semestrálka (body 4–7):** návrh protokolu, schémat, datového modelu a API pro
  příkazy, konfiguraci a ukládací politiku + **backendové** vynucení politiky.
- **Navazující (body 8–9):** vynucení politiky a store-and-forward **ve firmwaru**.
- **Mimo rozsah:** kamera / video stream (prozatím vynecháno).
