# ADR 0003: Vizualizace budovy — 2,5D přehled + 3D detail po patrech

- **Stav:** Přijato
- **Datum:** 2026-06-06
- **Souvisí:** [docs/design/3d-vizualizace-budovy.md](../design/3d-vizualizace-budovy.md)

## Kontext

Chceme prostorovou vizualizaci senzorů na modelu budovy („digital twin") — uživatel
vidí senzory tam, kde fyzicky jsou. Plné 3D celé budovy je drahé na tvorbu i výkon a
**Grafana 3D nezvládne**. Zároveň chceme něco působivého do showcase (bod 12).

## Zvažované varianty

1. **Jen 2,5D** — půdorysy se značkami. Levné, ale méně působivé.
2. **Plné 3D celé budovy** — jeden velký 3D model. Působivé, ale drahé a náročné na výkon.
3. **BIM / IFC** — reálný architektonický model. Nejvěrnější, ale potřeba reálný IFC
   soubor a těžké nástroje.
4. **Hybrid LOD** — 2,5D přehled pater + 3D drill-down jednotlivého patra (lazy-load).

## Rozhodnutí

Zvolen **hybrid LOD (varianta 4):** v přehledu se zobrazí všechna patra naskládaná
jako 2,5D půdorysy; po rozkliknutí patra se načte jeho **3D model (glTF)** se senzory
v reálných pozicích. Frontend: **vlastní React appka + react-three-fiber**.

## Důsledky

- ➕ Plní 3D záměr, ale s rozumnou pracností a výkonem (lazy-load modelů pater).
- ➕ Dá se stavět **inkrementálně** (2,5D MVP → 3D detail → vychytávky).
- ➖ Znamená **vlastní React frontend** (ne jen Grafana) — větší kus práce.
- ➖ Nutno udržovat assety (půdorysy, 3D modely) a pozice senzorů (`device_position`).
- Datový model se rozšíří o `floor` (assety, elevation) a `device_position`.
