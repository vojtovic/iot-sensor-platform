# ADR 0002: Vynucení ukládací politiky — capability-aware hybrid

- **Stav:** Přijato
- **Datum:** 2026-06-06
- **Souvisí:** [docs/design/rizeni-a-ukladaci-politika.md](../design/rizeni-a-ukladaci-politika.md)

## Kontext

Ukládací politika („report by exception" + heartbeat — ulož při překročení prahu,
jinak periodicky) se musí někde vyhodnocovat. Systém je **modulární a heterogenní**:
vlastní chytré jednotky i **cizí senzory** z jiných projektů (bod 10), které
nemůžeme přeprogramovat. Hlavní hodnota projektu je modularita → zásah do senzorů
má být minimální.

## Zvažované varianty

1. **Jen edge** — politiku vyhodnocuje vždy zařízení. Max. úspora přenosu/baterie,
   ale nefunguje pro cizí/hloupé senzory a ztrácí syrová data.
2. **Jen backend** — zařízení posílá vše, filtruje server. Maximální flexibilita a
   syrová data, ale žádná úspora přenosu/baterie.
3. **Capability-aware hybrid** — politika definovaná centrálně; vynucení na edge,
   pokud to zařízení deklaruje (`edge_policy: true`), jinak na backendu; backend je
   vždy pojistka.

## Rozhodnutí

Zvolena **varianta 3 (capability-aware hybrid)**. Zařízení při registraci deklaruje
schopnosti; backend podle toho buď pošle politiku dolů (edge filtruje), nebo ji
aplikuje sám.

## Důsledky

- ➕ Minimální zásah do senzorů (modularita), funguje i pro cizí jednotky (bod 10).
- ➕ Úspora přenosu/baterie u chytrých jednotek; flexibilita a pojistka na backendu.
- ➖ Logika ukládací politiky existuje **dvakrát** (edge i backend) → musí dát
  stejný výsledek (kryje to společný pseudokód + testy v TESTING.md).
- ➖ U backend-only zařízení se neušetří přenos.
