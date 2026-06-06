# 3D vizualizace budovy — „digital twin"

> Doplněk k [ROADMAP.md](../../ROADMAP.md) bod **5** (vizualizace). Návrh prostorové
> vizualizace senzorů na modelu budovy. Rozhodnutí viz
> [ADR 0003](../adr/0003-vizualizace-budovy.md). **Implementace = navazující / showcase (bod 12).**

---

## 1. Koncept: progresivní detail (LOD)

- **Přehled (2,5D):** všechna patra naskládaná na sobě jako půdorysy (obrázky),
  senzory jako barevné značky. Rychlý přehled o celé budově.
- **Detail (3D):** po **rozkliknutí patra** se dané patro zobrazí jako plnohodnotná
  **3D scéna** se senzory v reálných pozicích.

Proč takhle: rychlý přehled, bohatý detail jen kde je potřeba, **lazy-load** 3D
modelů (výkon) a dá se stavět **inkrementálně** (nejdřív 2,5D, pak 3D).

```
[ Přehled 2,5D ]            klik na patro          [ Detail 3D ]
 ▦ 3. NP  ── senzory ──┐   ───────────────▶   ┌─ 3D model patra
 ▦ 2. NP  ── senzory ──┤                       │  senzory v (x,y,z)
 ▦ 1. NP  ── senzory ──┘                       └─ klik na senzor → graf
```

---

## 2. Jak to vykreslit (frontend)

- **Vlastní React frontend** + **react-three-fiber / three.js**. (Grafana 3D neumí —
  viz důsledky v [ADR 0003](../adr/0003-vizualizace-budovy.md).)
- **Elegantní varianta — jedna three.js scéna:** patra jsou texturované roviny
  naskládané v prostoru (přehled); po kliknutí se rovina patra nahradí 3D modelem a
  kamera „nazoomuje" → plynulý přechod 2,5D → 3D.
- **MVP varianta:** přehled jako 2D (SVG/canvas), 3D detail samostatně. Méně plynulé,
  ale rychlejší na postavení.
- **Lazy-load:** glTF model patra se načte až při rozkliknutí.
- **Živá data přes WebSocket** (už v API): značky mění barvu v reálném čase; klik na
  značku → graf historie (REST).

---

## 3. Prostorová data — rozšíření datového modelu

Souřadnice jsou **per-patro lokální** (jednodušší než globální systém budovy).
Modely a obrázky jsou soubory (statický server / object storage), DB drží odkazy + metadata.

```json
// floor — patro + jeho assety
{
  "id": "f-2", "site_id": "b-1", "level_index": 2, "name": "2. NP",
  "elevation_m": 7.0,
  "floorplan": { "asset": "/assets/floors/f-2/plan.png",
                 "width_px": 2000, "height_px": 1400, "scale_m_per_px": 0.02 },
  "model3d":  { "asset": "/assets/floors/f-2/model.glb" }    // volitelné (pro 3D detail)
}

// device_position — kde senzor fyzicky je
{ "device_id": "esp32-ab12cd", "floor_id": "f-2",
  "x": 1180, "y": 540,   // poloha na půdorysu (px)
  "z": 1.2 }             // volitelně výška pro 3D
```

---

## 4. Umístění senzorů (editor)

- **Editor mód:** klikneš na půdorys → přiřadíš `device_id` → uloží se `(x, y)` + patro.
- Pro 3D detail buď stejné `(x, y)` promítneš do modelu, nebo doplníš `z` / přesnou
  pozici v 3D editoru.
- Persistence přes API: `PUT /devices/{id}/position`.

---

## 5. Zobrazení dat

- **Barevná škála** podle veličiny (CO₂ zelená→červená; práh konfigurovatelný).
- **Klik na senzor:** aktuální hodnoty všech kanálů + graf historie + stav (online/offline).
- **Volitelně heatmapa** po ploše patra (interpolace mezi senzory) — pokročilé.

---

## 6. Co frontend potřebuje z API (body 4–5)

| Endpoint | Účel |
|---|---|
| `GET /floors` | seznam pater + odkazy na assety, `elevation`, pořadí |
| `GET /floors/{id}/devices` | zařízení na patře + jejich pozice |
| `PUT /devices/{id}/position` | uložení pozice z editoru |
| `GET /devices/{id}/telemetry` + WS | historie + živé hodnoty (už navrženo) |

---

## 7. Doporučený postup (inkrementálně)

1. **2,5D přehled** — půdorysy + značky + klik → graf. (MVP, největší poměr hodnota/úsilí.)
2. **3D detail patra** — jeden glTF model, drill-down.
3. **Vychytávky** — heatmapa, plynulý přechod 2,5D→3D, editor pozic.

---

## 8. Rozsah a hranice

- **Teď (bod 5):** návrh + rozšíření datového modelu a API (assety pater, pozice senzorů).
- **Navazující / showcase (bod 12):** samotný 3D frontend.
- **Implikace:** vyžaduje **vlastní React frontend** (vedle/místo Grafany) — viz
  [ADR 0003](../adr/0003-vizualizace-budovy.md).
