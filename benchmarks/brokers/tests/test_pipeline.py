"""Testy čistých funkcí pipeline benchmarku (parse/rows) — bez brokeru i DB."""
from __future__ import annotations

import json

from brokerbench.payload import make_payload, parse_message, rows_from_message


def test_parse_message_valid():
    raw = make_payload("bench-001", 42, t_ns=123_000_000)
    parsed = parse_message(raw)
    assert parsed is not None
    device_id, seq, t_ns, meas = parsed
    assert device_id == "bench-001"
    assert seq == 42
    assert t_ns == 123_000_000
    assert {q for q, _ in meas} == {"co2", "temp", "rh"}


def test_parse_message_invalid():
    assert parse_message(b"{not json") is None
    # chybí device_id
    assert parse_message(json.dumps({"seq": 1, "t_ns": 1}).encode()) is None
    # seq není číslo
    assert parse_message(
        json.dumps({"device_id": "x", "t_ns": 1, "seq": "abc"}).encode()) is None


def test_rows_from_message_maps_channels():
    parsed = ("bench-001", 7, 1_000_000_000,
              [("co2", 800.0), ("temp", 22.5), ("rh", 40.0)])
    chan = {("bench-001", "co2"): 10, ("bench-001", "temp"): 11, ("bench-001", "rh"): 12}
    rows = rows_from_message(parsed, chan)
    assert len(rows) == 3
    ts, dev, cid, val, qual, seq = rows[0]   # (time, device_id, channel_id, value, quality, seq)
    assert dev == "bench-001"
    assert cid == 10
    assert val == 800.0
    assert qual == 0
    assert seq == 7
    assert ts.year == 1970   # t_ns = 1e9 ns = 1 s po epoše


def test_rows_from_message_skips_unknown_channel():
    parsed = ("bench-002", 1, 1_000_000_000, [("co2", 800.0), ("voc", 100.0)])
    chan = {("bench-002", "co2"): 5}   # voc není namapováno
    rows = rows_from_message(parsed, chan)
    assert len(rows) == 1
    assert rows[0][2] == 5


def test_rows_from_message_empty_when_no_match():
    parsed = ("bench-999", 1, 1_000_000_000, [("co2", 800.0)])
    assert rows_from_message(parsed, {}) == []
