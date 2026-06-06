# benchmarks/

Srovnání kandidátských stacků (Fáze 3 roadmapy, metodika v TESTING.md §5).

Každý kandidát = **minimální** ingestion služba (subscribe → parse → validace →
batch insert) + 1 read endpoint. Vše ostatní (broker, DB, generátor zátěže,
CPU/RAM limity) je stejné.

```
benchmarks/
├─ python-fastapi/
├─ dotnet/
├─ node-nestjs/
├─ java-spring/
└─ results/        # naměřená data + grafy (necommituje se? viz .gitignore)
```

Výstup → tabulka + grafy + rozhodnutí v `../docs/adr/0001-vyber-implementacniho-stacku.md`.
