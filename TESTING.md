# TESTING — Testovací strategie IoT systému

> Doprovází [ROADMAP.md](ROADMAP.md). Cíl: ověřit **funkčnost, spolehlivost,
> latenci a škálovatelnost** navrženého systému a získat čísla, která půjdou
> přímo do textu práce (a později do bodu 11).
>
> **Zlaté pravidlo:** každý test musí mít (a) jasnou hypotézu, (b) měřenou metriku,
> (c) cílovou/akceptační hodnotu. Bez čísla to není test, ale dojem.

---

## 1. Co a na jaké úrovni testovat

Testovací pyramida přizpůsobená IoT:

```
        /\        E2E (simulátor → broker → ingestion → DB → API)   ← málo, drahé
       /  \       Zátěž / škálovatelnost / fault injection           ← klíčové pro práci
      /----\      Integrační (reálný broker + DB, testcontainers)
     /------\     Kontraktní / schema (validace payloadů, verze protokolu)
    /--------\    Unit (parsování, validace, mapování, topic logika)  ← hodně, rychlé
```

| Vlastnost (z ROADMAP §1) | Jak ji ověřím | Sekce |
|---|---|---|
| Funkčnost | unit + integrační + E2E | §3 |
| Škálovatelnost | zátěžové testy s rampou zařízení | §6 |
| Spolehlivost při výpadku | fault injection (broker/backend/DB/síť) | §7 |
| Latence | měření ts vzniku → ts uložení | §8 |
| Interoperabilita | kontraktní/schema testy | §3.3 |

---

## 2. Testovací data a prostředí

- Testy běží proti **stejnému `docker-compose`** stacku jako vývoj (broker + DB +
  Grafana). Pro CI lehčí varianta (Mosquitto + Postgres/Timescale).
- **Determinismus:** simulátor má `--seed`, ať jsou běhy opakovatelné.
- **Izolace:** každý test/běh do vlastního DB schématu nebo s prefixem topiců, ať
  se navzájem neovlivní.
- **Realistická data:** hodnoty v reálných rozsazích (CO₂ 400–2000 ppm, teplota
  18–28 °C, RH 30–60 %) — kvůli smysluplným alertům i dashboardům.

---

## 3. Funkční testy

### 3.1 Unit (rychlé, bez infrastruktury)
Testuj čistou logiku, žádné I/O:
- parsování payloadu (validní / poškozený / chybějící pole / špatný typ),
- validace proti schématu (hraniční hodnoty, neznámý kanál),
- mapování payload → kanonický model (jednotky, kalibrace),
- parsování topiců (`v1/dev/{id}/telemetry` → `device_id`),
- deduplikace podle `device_id`+`seq`, detekce mezery v `seq`.

### 3.2 Integrační (s reálným brokerem + DB)
Použij **testcontainers** (rozjede broker i DB v kontejneru pro test) nebo sdílený
compose:
- publish na broker → ingestion zapíše → dotaz do DB vrátí stejnou hodnotu,
- retained `config` topic → nový subscriber ho hned dostane,
- LWT → po „tvrdém" odpojení se na `status` objeví `offline`,
- batch insert → N zpráv skončí jako N řádků (žádná ztráta, žádný duplikát).

### 3.3 Kontraktní / schema testy `(interoperabilita)`
- Telemetrie se validuje proti **JSON Schema**; nevalidní zpráva je odmítnuta a
  zalogována (ne tiše zahozena).
- **Verzování:** `schema:"v1"` vs `v2` — starší i novější zpráva se zpracuje
  předvídatelně (back/forward compat test).
- Cizí payload (bod 10 `[NAVAZUJÍCÍ]`) → adapter ho převede na kanonický model;
  test ověří mapování.

### 3.4 API testy
- REST: dotazy na časové rozsahy, agregace, poslední hodnoty, stránkování,
  chybové stavy (404, 400, 401).
- Autentizace: bez tokenu → 401; cizí token → 403.
- WebSocket: po subscribe přijde živá hodnota do X ms.
- Nástroje: `pytest`+`httpx` / `newman` (Postman) / REST client.

### 3.5 E2E
Jeden „happy path" přes celý systém: simulátor publikuje → data jsou v DB →
viditelná přes API → zobrazí se na dashboardu. Plus jeden „smutný path" (výpadek).

---

## 4. Sensor simulator / generátor zátěže

Srdce všech testů. Postav ho jednou, použiješ pořád. Musí umět:

- spustit **N virtuálních zařízení** (každé vlastní `device_id`, topic, `seq`),
- nastavit **frekvenci** publikace a velikost payloadu,
- **rampu** (postupně přidávat zařízení: 10 → 100 → 1000 …),
- simulovat **výpadek**: přestat publikovat / odpojit, pak **replay** z bufferu
  (s navazujícím `seq`) — tím testuješ spolehlivost (§7) i bez reálného HW,
- volitelně **chybné zprávy** (poškozený JSON, mimo rozsah) pro robustnost.

> Tenhle simulátor je zároveň náhrada za reálné jednotky (body 8–9) v semestrálce —
> proto stojí za to ho udělat pořádně.

Hotové nástroje na čistě zátěžovou část (když nepotřebuješ vlastní logiku):
**emqtt_bench**, **MQTTX CLI** (`mqttx bench`), **mqtt-stresser**, **k6** (xk6-mqtt),
**JMeter** (MQTT plugin).

---

## 5. Benchmark stacků

Tohle je experiment, který rozhodne o stacku (ROADMAP §2). Drž **vše konstantní
kromě testovaného stacku**.

**Uspořádání:**
- stejný broker, stejná DB, stejný generátor zátěže, stejný HW (tvůj stroj),
- každý kandidát = identická ingestion služba (subscribe → parse → validace →
  batch insert), 1 read endpoint,
- jeden kontejner na službu, **stejné limity** (CPU/RAM) přes `docker` limits.

**Postup měření (pro každý stack):**
1. Warm-up (zahoď první ~30 s).
2. Rampa zátěže, dokud se neobjeví **backlog** (fronta roste = překročen throughput).
3. Zaznamenej **max. udržitelný throughput** (zpráv/s bez růstu fronty).
4. Při ~70 % max. throughputu měř **latenci** (p50/p95/p99) a **zdroje** (CPU%, RSS).
5. Opakuj 3×, ber medián.

**Srovnávací tabulka (vyplň měřením):**

| Stack            | Max msg/s | p50 / p95 / p99 latence | CPU @70 % | RAM | Image | Dev effort* |
| ---------------- | --------- | ----------------------- | --------- | --- | ----- | ----------- |
| Python (FastAPI) |           |                         |           |     |       |             |
| C# / .NET        |           |                         |           |     |       |             |
| Node.js (NestJS) |           |                         |           |     |       |             |
| Java / Spring    |           |                         |           |     |       |             |

\* Dev effort = subjektivní (1–5) + řádky kódu na stejnou funkci + čas.

**Výstup:** graf throughput/latence + tabulka + **ADR** s váženým rozhodnutím.

---

## 6. Zátěžové a škálovací testy `(škálovatelnost)`

**Scénáře (rampa zařízení):**

| Scénář | Zařízení | Frekvence | Cíl |
|---|---|---|---|
| Smoke | 10 | 1/s | systém vůbec jede |
| Normál | 100 | 1/10 s | typická budova |
| Zátěž | 1 000 | 1/10 s | velká budova / kampus |
| Stress | 10 000+ | mix | najít strop |

**Metriky, které měř a reportuj:**
- **throughput** (přijatých / uložených zpráv/s),
- **ingestion lag / backlog** (roste fronta? = nestíháš),
- **latence** p50/p95/p99 (§8),
- **zdroje**: CPU/RAM brokeru, ingestionu, DB; rychlost zápisu DB,
- **ztrátovost**: odeslané vs uložené (musí sedět, jinak ztrácíš data),
- **connection scaling**: kolik souběžných MQTT spojení broker unese.

**Realistická poznámka (Windows laptop):** 10 000 reálných TCP spojení z jednoho
stroje je problém. Řešení: víc publisher procesů, multiplex, nebo krátkodobá
**cloud VM** na velké běhy. **Limity vždy popiš** — i to je validní výsledek.

---

## 7. Testy spolehlivosti / fault injection `(klíčové, bod 9 a 11)`

Tady ověřuješ „chování při výpadku komunikace nebo backendových služeb". Pro každý
scénář definuj: **co vypnu → co očekávám → jak ověřím, že se nic neztratilo.**

| Scénář (co vypadne) | Očekávané chování | Jak ověřit |
|---|---|---|
| **Broker spadne** | zařízení bufferuje + reconnect s backoff; QoS1 doručí po obnově | simulátor pokračuje v `seq`, po obnově dorazí vše |
| **Ingestion spadne** | zprávy zůstanou v brokeru (persistent session / QoS1), po startu se doženou | porovnej `seq` před/po, žádná mezera |
| **DB spadne** | ingestion drží backpressure / lokální frontu, nezahazuje | po obnově DB data dotečou |
| **Pomalá / ztrátová síť** | reconnect, žádná korupce dat | inject latence/ztráty, ověř integritu |
| **Zařízení offline** | LWT → `status:offline` do X s; po návratu `online` | sleduj retained `status` |
| **Restart zařízení** | naváže `seq`/buffer, server deduplikuje | žádné duplikáty v DB |

**Nástroje pro injekci poruch:**
- **Toxiproxy** — proxy mezi službami, přidává latenci / drop / cut (skvělé,
  skriptovatelné).
- **Pumba** — chaos pro Docker (`pumba kill`, `pumba netem delay …`).
- **Clumsy** — Windows GUI pro lag/drop/throttle na síti (hodí se lokálně).
- `docker compose stop <service>` / `pause` — nejjednodušší výpadek služby.

**Test ztráty dat (nejdůležitější):** simulátor pošle přesně N zpráv se
sekvenčním `seq`, během toho vypadne broker/ingestion → po obnově v DB musí být
**N unikátních** `seq` bez mezer a bez duplikátů. Tohle je tvůj hlavní důkaz
spolehlivosti.

---

## 8. Měření latence (metodicky správně)

End-to-end latence = `čas_uložení_v_DB − ts_vzniku_na_zařízení`.

**Pozor na hodiny (častá chyba ve studentských pracích):**
- Pokud zařízení a server mají **nesladěné hodiny**, latence je nesmysl (může vyjít
  i záporná).
- Řešení: (a) běž generátor i backend na **jednom hostu** a použij jeden
  (monotónní) zdroj času; nebo (b) **NTP** sync; nebo (c) měř **round-trip**
  (request→ack) a vezmi polovinu.

**Rozpad latence po komponentách** (ať víš, co je úzké hrdlo):
`device → broker`, `broker → ingestion`, `ingestion → DB`. Měř razítka na každém
přechodu.

**Reportuj percentily, ne průměr:** p50/p95/p99. Průměr schová ocas (a ten ocas je
to, co uživatele bolí).

---

## 9. Datová integrita

- **Žádná ztráta:** odeslané = uložené (viz §7 test `seq`).
- **Žádné duplikáty:** dedup podle (`device_id`,`seq`) ověřen i pod zátěží.
- **Řazení:** out-of-order doručení (po reconnectu) se srovná podle `ts`/`seq`.
- **Správnost hodnot:** uložená hodnota == odeslaná (vč. jednotek/kalibrace).
- **Odmítnutí špatných dat:** nevalidní payload se nezapíše, ale zaloguje.

---

## 10. Bezpečnostní testy (základ)

- MQTT vyžaduje autentizaci; anonymní připojení odmítnuto.
- **ACL:** zařízení smí publikovat jen do svých topiců (zkus cizí → odmítnuto).
- API: endpointy vyžadují token; chybí/špatný → 401/403.
- Validace vstupů (API i payload) → odolnost proti injection / malformed.
- (Volitelně) **TLS** na brokeru i API.

---

## 11. Observabilita pro testování

Bez měření „naslepo" netestuješ. Měj připravené:
- **Prometheus metriky** z ingestionu (přijaté/zapsané/odmítnuté zprávy, lag,
  doba zápisu),
- **dashboard brokeru** (EMQX má vlastní; jinak exporter),
- **Grafana** panel „test run" (throughput, lag, latence, CPU/RAM) — screenshot
  rovnou do práce.

---

## 12. Akceptační kritéria (příklad — uprav podle svých cílů)

Nastav si **konkrétní čísla předem**, ať máš co obhájit:

| Metrika | Cílová hodnota (příklad) |
|---|---|
| Ztrátovost při normální zátěži | 0 % |
| Ztrátovost po výpadku brokeru (QoS1) | 0 % (vše dohnáno) |
| Latence p95 (normální zátěž) | < 500 ms |
| Max. udržitelný throughput | změřeno + zdokumentováno |
| Detekce offline zařízení (LWT) | < 30 s |
| Souběžná spojení | změřeno + zdokumentováno |
| Duplikáty v DB | 0 |

---

## 13. CI (kontinuální integrace)

Minimum, ať se nic nerozbije potichu:
- na každý push: **lint + unit testy** (rychlé, bez infry),
- noční / on-demand: **integrační** testy (testcontainers) + smoke E2E,
- zátěžové a fault testy ručně / on-demand (jsou pomalé a potřebují zdroje).

---

## 14. Windows-specifické poznámky

- **Docker Desktop** (WSL2 backend) pro celý stack.
- **Clumsy** na simulaci špatné sítě (lag, drop, throttle) lokálně.
- Velké zátěžové běhy: zvaž Linux VM / cloud VM (limity TCP spojení na Windows).
- Generátor zátěže pouštěj radši ve více procesech (obejdeš limity jednoho procesu).

---

## 15. Checklist před odevzdáním

- [ ] Unit + integrační testy zelené, běží v CI
- [ ] E2E happy path i výpadkový scénář prokázané
- [ ] Benchmark stacků: tabulka + grafy + ADR
- [ ] Zátěžové testy: rampa + metriky + popsané limity prostředí
- [ ] Fault injection: důkaz **0 ztracených zpráv** (test `seq`)
- [ ] Latence: percentily + popis metodiky (hodiny!)
- [ ] Bezpečnost: auth + ACL ověřeny
- [ ] Screenshoty dashboardů + naměřené grafy v textu práce
- [ ] README: jak testy spustit (`docker compose up`, příkazy)
