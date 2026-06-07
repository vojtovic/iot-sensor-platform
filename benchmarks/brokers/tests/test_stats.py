"""Unit testy pro čisté výpočetní funkce."""
from __future__ import annotations

from brokerbench.payload import make_payload, read_t_ns
from brokerbench.stats import (
    latency_summary,
    parse_docker_stats,
    parse_mem_mb,
    percentile,
)


def test_percentile_empty():
    assert percentile([], 50) == 0.0


def test_percentile_single():
    assert percentile([5.0], 99) == 5.0


def test_percentile_basic():
    data = [float(i) for i in range(1, 101)]  # 1..100
    assert percentile(data, 50) == 50.5
    assert percentile(data, 0) == 1.0
    assert percentile(data, 100) == 100.0


def test_latency_summary():
    s = latency_summary([10, 20, 30, 40, 50])
    assert s["max"] == 50.0
    assert s["avg"] == 30.0
    assert s["p50"] == 30.0


def test_latency_summary_empty():
    s = latency_summary([])
    assert s == {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "avg": 0.0}


def test_parse_mem_mb_units():
    assert parse_mem_mb("45.6MiB") == 45.6
    assert parse_mem_mb("1GiB") == 1024.0
    assert abs(parse_mem_mb("512KiB") - 0.5) < 1e-9
    assert parse_mem_mb("") == 0.0


def test_parse_docker_stats_ok():
    r = parse_docker_stats("12.34%|45.6MiB / 7.5GiB")
    assert r == {"cpu_pct": 12.34, "mem_mb": 45.6}


def test_parse_docker_stats_bad():
    assert parse_docker_stats("garbage") is None
    assert parse_docker_stats("--|--") is None


def test_payload_roundtrip_t_ns():
    raw = make_payload("dev1", 7, t_ns=123456789)
    assert read_t_ns(raw) == 123456789


def test_payload_missing_t_ns():
    assert read_t_ns(b'{"no":"ts"}') is None
    assert read_t_ns(b"not json") is None
