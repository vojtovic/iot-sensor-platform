"""Export naměřených výsledků (results/*.json) do CSV, grafů (PNG) a souhrnné MD.

Použití:
    python -m brokerbench.export                       # z results/ do results/export/
    python -m brokerbench.export --ref-rate 5000       # referenční bod pro souhrn/bary

CSV a MD nemají závislosti; grafy vyžadují matplotlib (extra [viz]).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

# Pořadí sloupců v CSV / hlavička.
CSV_FIELDS = [
    "broker", "qos", "target_rate", "throughput", "loss_pct",
    "p50_ms", "p95_ms", "p99_ms", "max_ms",
    "cpu_pct_max", "mem_mb_max",
]


def load_results(results_dir: Path) -> list[dict]:
    """Načte všechny *.json (kromě adresáře export/) a zploští na řádky kroků."""
    rows: list[dict] = []
    for jf in sorted(results_dir.glob("*.json")):
        try:
            data = json.loads(jf.read_text())
        except (ValueError, OSError):
            continue  # přeskoč rozepsané/poškozené
        broker = data.get("broker", jf.stem)
        qos = data.get("qos", "?")
        for s in data.get("steps", []):
            lat = s.get("lat", {})
            rows.append({
                "broker": broker,
                "qos": qos,
                "target_rate": s.get("target_rate"),
                "throughput": round(s.get("throughput", 0), 1),
                "loss_pct": round(s.get("loss_pct", 0), 1),
                "p50_ms": round(lat.get("p50", 0), 1),
                "p95_ms": round(lat.get("p95", 0), 1),
                "p99_ms": round(lat.get("p99", 0), 1),
                "max_ms": round(lat.get("max", 0), 1),
                "cpu_pct_max": round(s.get("cpu_pct_max", 0), 1),
                "mem_mb_max": round(s.get("mem_mb_max", 0), 1),
            })
    return rows


def write_csv(rows: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(rows)


def write_summary_md(rows: list[dict], out: Path, ref_rate: int) -> None:
    """Souhrnná tabulka v referenčním bodě zatížení, zvlášť pro každý QoS."""
    by_qos: dict = defaultdict(list)
    for r in rows:
        if r["target_rate"] == ref_rate:
            by_qos[r["qos"]].append(r)

    lines = [f"# Souhrn broker benchmarku — referenční bod {ref_rate:,} zpráv/s\n"]
    for qos in sorted(by_qos):
        lines.append(f"\n## QoS {qos}\n")
        lines.append("| Broker | propust./s | ztráta % | p99 ms | CPU % | RAM MB |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        # seřaď podle efektivity: nejdřív bez ztrát, pak podle p99
        for r in sorted(by_qos[qos], key=lambda x: (x["loss_pct"], x["p99_ms"])):
            lines.append(
                f"| {r['broker']} | {r['throughput']:,.0f} | {r['loss_pct']:.1f} "
                f"| {r['p99_ms']:.1f} | {r['cpu_pct_max']:.0f} | {r['mem_mb_max']:.0f} |"
            )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")


def write_charts(rows: list[dict], out_dir: Path, ref_rate: int) -> list[str]:
    """Grafy přes matplotlib. Vrátí seznam zapsaných souborů (prázdný bez matplotlib)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    qoses = sorted({r["qos"] for r in rows})
    brokers = sorted({r["broker"] for r in rows})

    def series(broker: str, qos, key: str):
        pts = sorted(
            ((r["target_rate"], r[key]) for r in rows
             if r["broker"] == broker and r["qos"] == qos),
            key=lambda t: t[0],
        )
        return [p[0] for p in pts], [p[1] for p in pts]

    # Křivkové grafy: propustnost a p99 vs cílová rychlost (zvlášť per QoS).
    for qos in qoses:
        for key, ylabel, fname, logy in [
            ("throughput", "propustnost (zpráv/s)", f"throughput-qos{qos}.png", False),
            ("p99_ms", "latence p99 (ms)", f"latency-p99-qos{qos}.png", True),
        ]:
            fig, ax = plt.subplots(figsize=(8, 5))
            for b in brokers:
                x, y = series(b, qos, key)
                if x:
                    ax.plot(x, y, marker="o", label=b)
            if key == "throughput":  # ideální linie x=y (jen rozsah daného QoS)
                allx = sorted({r["target_rate"] for r in rows if r["qos"] == qos})
                ax.plot(allx, allx, "k--", alpha=0.3, label="ideál (cíl)")
            ax.set_xlabel("cílová rychlost (zpráv/s)")
            ax.set_ylabel(ylabel)
            ax.set_title(f"{ylabel} — QoS {qos}")
            if logy:
                ax.set_yscale("log")
            ax.grid(True, alpha=0.3)
            ax.legend(fontsize=8)
            fig.tight_layout()
            p = out_dir / fname
            fig.savefig(p, dpi=120)
            plt.close(fig)
            written.append(str(p))

    # Sloupcové grafy v referenčním bodě: RAM a CPU per broker (per QoS).
    for qos in qoses:
        ref = {r["broker"]: r for r in rows
               if r["qos"] == qos and r["target_rate"] == ref_rate}
        if not ref:
            continue
        bs = sorted(ref)
        for key, ylabel, fname in [
            ("mem_mb_max", "RAM (MB)", f"ram-qos{qos}-{ref_rate}.png"),
            ("cpu_pct_max", "CPU (%)", f"cpu-qos{qos}-{ref_rate}.png"),
        ]:
            fig, ax = plt.subplots(figsize=(8, 5))
            ax.bar(bs, [ref[b][key] for b in bs])
            ax.set_ylabel(ylabel)
            ax.set_title(f"{ylabel} @ {ref_rate:,}/s — QoS {qos}")
            ax.grid(True, axis="y", alpha=0.3)
            fig.tight_layout()
            p = out_dir / fname
            fig.savefig(p, dpi=120)
            plt.close(fig)
            written.append(str(p))
    return written


def _latest_per_broker(results_dir: Path, prefix: str) -> dict[str, dict]:
    """Načte nejnovější JSON na broker pro daný prefix (failtest-/scaletest-)."""
    by_broker: dict[str, dict] = {}
    for jf in sorted(results_dir.glob(f"{prefix}*.json")):
        try:
            data = json.loads(jf.read_text())
        except (ValueError, OSError):
            continue
        b = data.get("broker", jf.stem)
        by_broker[b] = data  # pozdější (setříděné) přepíše dřívější
    return by_broker


def write_failtest_chart(results_dir: Path, out_dir: Path) -> list[str]:
    """Sloupcový graf ztráty zpráv (kontrola vs restart) per broker."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    data = _latest_per_broker(results_dir, "failtest-")
    if not data:
        return []
    brokers = sorted(data)
    ctrl = [data[b].get("control", {}).get("lost", 0) for b in brokers]
    rest = [(data[b].get("restart") or {}).get("lost", 0) for b in brokers]
    n = data[brokers[0]].get("n", 500)

    import numpy as np
    x = np.arange(len(brokers))
    w = 0.38
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(x - w / 2, ctrl, w, label="bez restartu")
    ax.bar(x + w / 2, rest, w, label="s restartem")
    ax.set_xticks(x, brokers, rotation=20)
    ax.set_ylabel(f"ztracené zprávy (z {n})")
    ax.set_title("Spolehlivost při výpadku — ztráta zpráv (QoS 1, trvalá session)")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "failtest-loss.png"
    fig.savefig(p, dpi=120)
    plt.close(fig)
    return [str(p)]


def write_scaletest_charts(results_dir: Path, out_dir: Path) -> list[str]:
    """Grafy škálovatelnosti: navázaná spojení a RAM vs cílový počet."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    data = _latest_per_broker(results_dir, "scaletest-")
    if not data:
        return []
    brokers = sorted(data)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    for key, ylabel, fname, ideal in [
        ("connected", "navázaná spojení", "scaletest-connected.png", True),
        ("mem_after_mb", "RAM brokeru (MB)", "scaletest-ram.png", False),
    ]:
        fig, ax = plt.subplots(figsize=(9, 5))
        for b in brokers:
            steps = data[b].get("steps", [])
            xs = [s["target"] for s in steps]
            ys = [s[key] for s in steps]
            if xs:
                ax.plot(xs, ys, marker="o", label=b)
        if ideal:
            allx = sorted({s["target"] for b in brokers for s in data[b].get("steps", [])})
            ax.plot(allx, allx, "k--", alpha=0.3, label="ideál (vše navázáno)")
        ax.set_xlabel("cílový počet spojení")
        ax.set_ylabel(ylabel)
        ax.set_title(f"Škálovatelnost spojení — {ylabel}")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        p = out_dir / fname
        fig.savefig(p, dpi=120)
        plt.close(fig)
        written.append(str(p))
    return written


def main() -> None:
    ap = argparse.ArgumentParser(prog="brokerbench.export", description="Export výsledků")
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--out", default="results/export")
    ap.add_argument("--ref-rate", type=int, default=5000)
    args = ap.parse_args()

    results_dir = Path(args.results_dir)
    out = Path(args.out)
    rows = load_results(results_dir)
    charts: list[str] = []
    if rows:
        write_csv(rows, out / "benchmark.csv")
        write_summary_md(rows, out / "summary.md", args.ref_rate)
        charts += write_charts(rows, out, args.ref_rate)
        print(f"CSV:    {out/'benchmark.csv'}  ({len(rows)} řádků)")
        print(f"Souhrn: {out/'summary.md'}")

    # grafy testů výpadku a škálovatelnosti (pokud jsou JSON výsledky)
    charts += write_failtest_chart(results_dir, out)
    charts += write_scaletest_charts(results_dir, out)

    if charts:
        print(f"Grafy:  {len(charts)} PNG v {out}/")
    elif not rows:
        print(f"Žádné výsledky v {args.results_dir}/ (nebo chybí matplotlib)")


if __name__ == "__main__":
    main()
