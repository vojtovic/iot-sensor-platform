# IoT systém pro sběr senzorických dat v budovách

Modulární, škálovatelný distribuovaný systém pro **sběr, ukládání a zpřístupnění
dat z heterogenních senzorových jednotek** v budovách — se zaměřením na HVAC a
kvalitu vnitřního prostředí (teplota, vlhkost, CO₂, VOC, tlak).

> **Stav:** návrh architektury a backendu — semestrální projekt (**body 1–7**).
> Plán a postup viz [ROADMAP.md](ROADMAP.md), testovací strategie viz
> [TESTING.md](TESTING.md).

---

## O projektu

Cílem je obecná architektura, která umožní:

- **škálovatelnost** — stovky až tisíce jednotek bez přepisu systému,
- **modularitu senzorů** — jednotka = N kanálů (čidel); nový typ čidla bez změny schématu,
- **interoperabilitu** — jednotný kanonický datový model napříč různými payloady,
- **nasazení v různých budovách** — hierarchie tenant → budova → patro → místnost.

**Vzdálené řízení a chytré ukládání (návrh):**

- příkazy zařízení (start/stop měření, `measure_now`, restart, kalibrace, …),
- vzdálená konfigurace (interval měření, kalibrace),
- ukládací politika „report by exception" + heartbeat — ukládej při překročení
  prahu (s hysterezí), jinak periodicky,
- vynucení na zařízení (umí-li), jinak na backendu — viz
  [docs/design/rizeni-a-ukladaci-politika.md](docs/design/rizeni-a-ukladaci-politika.md).

**Vizualizace „digital twin" (návrh):**

- 2,5D přehled pater na sobě; po rozkliknutí patra 3D scéna se senzory v reálných pozicích,
- živé hodnoty barevně + klik na senzor → graf historie — viz
  [docs/design/3d-vizualizace-budovy.md](docs/design/3d-vizualizace-budovy.md).

## Architektura (přehled)

```
Senzory ──MQTT──> Broker ──> Ingestion ──> Time-series DB ─┐
                    │                       Metadata DB ────┼──> API ──> Dashboard
                    └── Device registry + konfigurace ──────┘
```

Detailní návrh (diagramy, datový model, protokol, registrace) je v
[ROADMAP.md](ROADMAP.md).

## Struktura repozitáře

| Složka | Obsah |
|---|---|
| `docs/` | rešerše, návrhové dokumenty, diagramy, ADR (rozhodnutí) |
| `infra/` | docker-compose, konfigurace brokeru, init DB |
| `backend/` | ingestion + device registry + API (vítězný stack) |
| `benchmarks/` | tenké ingestion služby kandidátů + výsledky srovnání |
| `simulator/` | sensor simulator / generátor zátěže |
| `dashboards/` | Grafana dashboardy (JSON) |
| `tests/` | testy (viz [TESTING.md](TESTING.md)) |

## Rozsah

- **Semestrální projekt:** body 1–7 (analýza, architektura, backend, vizualizace,
  protokol, registrace).
- **Navazující práce:** body 8–12 (HW jednotka, firmware, integrace cizích jednotek,
  experiment v reálném prostředí, publikace) — v dokumentaci značeno `[NAVAZUJÍCÍ]`.

## Jak spustit

> ⚠️ Spouštěcí prostředí (docker-compose: broker + DB + Grafana) se připravuje ve
> **Fázi 2** roadmapy. Až bude hotové, postup bude zde.

Plánovaně:

```bash
# až bude infra/ hotová
docker compose -f infra/docker-compose.yml up -d
```

## Dokumentace

- [ROADMAP.md](ROADMAP.md) — plán, fáze, návrh architektury / protokolu / datového modelu
- [TESTING.md](TESTING.md) — testovací strategie (funkčnost, zátěž, výpadky, latence)
- `docs/` — rešerše a rozhodnutí (ADR)

## Licence

MIT — viz [LICENSE](LICENSE).

## Autor

**Václav Vojtovič** — semestrální projekt.
