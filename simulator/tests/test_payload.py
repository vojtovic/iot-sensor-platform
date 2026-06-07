"""Unit testy pro sestavení payloadu (žádný broker není potřeba)."""
from __future__ import annotations

import random

from simulator.device import SimulatedDevice
from simulator.payload import (
    CHANNEL_UNITS,
    SCHEMA_VERSION,
    build_telemetry,
    telemetry_topic,
)


def test_topic_format():
    assert telemetry_topic("esp32-sim-001") == "v1/dev/esp32-sim-001/telemetry"


def test_build_telemetry_schema():
    msg = build_telemetry("dev1", 5, [("co2", 812.0), ("temp", 23.4)], ts=1000)
    assert msg["schema"] == SCHEMA_VERSION
    assert msg["device_id"] == "dev1"
    assert msg["ts"] == 1000
    assert msg["seq"] == 5
    assert msg["measurements"][0] == {"ch": "co2", "v": 812.0, "u": "ppm"}
    assert msg["measurements"][1] == {"ch": "temp", "v": 23.4, "u": "Cel"}


def test_value_rounded_to_2dp():
    msg = build_telemetry("d", 1, [("co2", 500.126)], ts=0)
    assert msg["measurements"][0]["v"] == 500.13


def test_units_are_canonical():
    assert CHANNEL_UNITS["co2"] == "ppm"
    assert CHANNEL_UNITS["temp"] == "Cel"
    assert CHANNEL_UNITS["rh"] == "%RH"


def test_meta_optional():
    assert "meta" not in build_telemetry("d", 1, [("rh", 40.0)], ts=0)
    msg = build_telemetry("d", 1, [("rh", 40.0)], ts=0, meta={"fw": "1.0.0"})
    assert msg["meta"]["fw"] == "1.0.0"


def test_device_seq_monotonic():
    dev = SimulatedDevice("esp32-sim-001", random.Random(42))
    p1 = dev.next_payload(ts=0)
    p2 = dev.next_payload(ts=0)
    assert p1["seq"] == 1
    assert p2["seq"] == 2
    assert {m["ch"] for m in p1["measurements"]} == {"co2", "temp", "rh"}


def test_device_values_within_bounds():
    dev = SimulatedDevice("d", random.Random(1))
    for _ in range(500):
        msg = dev.next_payload(ts=0)
        by_ch = {m["ch"]: m["v"] for m in msg["measurements"]}
        assert 400 <= by_ch["co2"] <= 2000
        assert 15 <= by_ch["temp"] <= 30
        assert 20 <= by_ch["rh"] <= 70


def test_seed_reproducible():
    a = SimulatedDevice("d", random.Random(7)).next_payload(ts=0)
    b = SimulatedDevice("d", random.Random(7)).next_payload(ts=0)
    assert a == b
