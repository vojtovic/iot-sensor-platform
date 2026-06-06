# simulator/

Sensor simulator / generátor zátěže — **páteř všech testů** (TESTING.md §4) a
zároveň náhrada za reálné jednotky (body 8–9) v semestrálce.

Musí umět:

- N virtuálních zařízení (každé vlastní `device_id`, topic, `seq`),
- nastavitelnou frekvenci a velikost payloadu,
- rampu (10 → 100 → 1000 … zařízení),
- simulaci výpadku + replay z bufferu (s navazujícím `seq`),
- volitelně chybné zprávy (poškozený JSON, mimo rozsah) pro test robustnosti,
- `--seed` pro opakovatelné běhy.
