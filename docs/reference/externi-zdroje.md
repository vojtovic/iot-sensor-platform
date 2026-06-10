# Externí zdroje (pro citace v textu práce)

Veřejné benchmarky a dokumentace, proti kterým jsme ověřovali vlastní měření.
U každého je uvedeno, **co podkládá**. Naše absolutní čísla se od těchto zdrojů
liší (jiný HW, jiný klient), ale **relativní pořadí a kvalitativní závěry sedí** —
to je hlavní hodnota pro obhajobu.

> Tento soubor je živý — doplňuje se při každé další rešerši.

---

## MQTT brokery (bod 2 zadání, ADR 0004)

| Zdroj | URL | Podkládá |
|---|---|---|
| EMQ — Open MQTT Benchmarking 2023 | https://www.emqx.com/en/blog/open-mqtt-benchmarking-comparison-mqtt-brokers-in-2023 | Mosquitto/NanoMQ nejnižší CPU/RAM; EMQX nižší latence; absolutní throughput (EMQX 500k/s, NanoMQ 250k/s, Mosquitto 80k/s) |
| EMQ — Mosquitto vs NanoMQ | https://www.emqx.com/en/blog/mosquitto-vs-nanomq-2023-mqtt-broker-comparison | Mosquitto single-threaded → strop spojení; NanoMQ vícejádrový |
| EMQ — EMQX 5M spojení / 1 uzel | https://www.emqx.com/en/blog/emqx-single-node-supports-5m-connections | EMQX škáluje na miliony spojení (náš 10k je konzistentní) |
| EMQ — 100M spojení s EMQX 5.0 | https://www.emqx.com/en/blog/reaching-100m-mqtt-connections-with-emqx-5-0 | paměť na spojení; VerneMQ ~18–22 KB/spoj (sedí s naším ~14–24 KB) |
| EMQ — EMQX vs VerneMQ | https://www.emqx.com/en/blog/open-mqtt-benchmarking-comparison-emqx-vs-vernemq | srovnání EMQX/VerneMQ |
| RabbitMQ — Native MQTT (3.12) | https://www.rabbitmq.com/blog/2023/03/21/native-mqtt | MQTT přes RabbitMQ; native MQTT zlepšil latenci 50–70 % (pre-3.12 ~4× pomalejší než AMQP) |
| Mosquitto — konfigurace (man) | https://mosquitto.org/man/mosquitto-conf-5.html | persistence je default **false** → po restartu se zprávy ztratí (přesná shoda s naším failtestem) |
| NanoMQ — offline messages (issue #1934) | https://github.com/nanomq/nanomq/issues/1934 | NanoMQ nedrží offline frontu; cache přidána až v0.24.14 (my měřili 0.22) |
| EMQX — durable sessions (docs) | https://docs.emqx.com/en/emqx/latest/durability/management.html | konfigurace durable sessions (`durable_sessions.enable`) — durabilita EMQX |

## Backend stacky (bod 4, ADR 0001)

| Zdroj | URL | Podkládá |
|---|---|---|
| DEV — Backend frameworks performance 2025 | https://dev.to/tuananhpham/popular-backend-frameworks-performance-benchmark-1bkh | ASP.NET Core #1; kompilované (C#/Java) > interpretované (Python/Node); Spring 9× zlepšení |
| WWT — Bun vs C# vs Go vs Node vs Python | https://www.wwt.com/blog/performance-benchmarking-bun-vs-c-vs-go-vs-nodejs-vs-python | C# top throughput; Python GIL strop; Node strádá pod zátěží |
| Medium — Node vs Go vs Rust vs C# REST 2024 | https://medium.com/@hiadeveloper/2024s-fastest-web-servers-for-rest-apis-node-js-vs-go-vs-rust-vs-c-net-benchmark-665d8efd2f44 | C#/.NET (Kestrel) vysoký výkon, ms latence |
| Medium — Spring Boot vs ASP.NET Core | https://medium.com/@putuprema/spring-boot-vs-asp-net-core-a-showdown-1d38b89c6c2d | ASP.NET Core <200 MB vs Spring 500 MB–1 GB; rychlejší start (<1 s vs 2–4 s) |
| ResearchGate (PDF) — Spring Boot vs .NET Core RESTful | https://www.researchgate.net/publication/352526403_A_Performance_Comparison_of_RESTful_Applications_Implemented_in_Spring_Boot_Java_and_MSNET_Core | akademické srovnání výkonu Spring Boot vs .NET Core |

---

## Poznámka k použití

- **Relativní vs absolutní:** naše čísla jsou relativní (stejný klient/HW pro všechny
  kandidáty), publikované benchmarky mají vyšší absolutní hodnoty (specializované
  nástroje, víc strojů). Do textu: „naše měření je v souladu s publikovanými
  srovnáními v relativním pořadí; absolutní throughput je limitován testovacím klientem."
- **I/O-bound výhrada:** pro reálnou zátěž s report-by-exception je hrdlem DB/síť,
  ne jazyk — volba stacku pak má menší dopad (uvedeno v ADR 0001).
