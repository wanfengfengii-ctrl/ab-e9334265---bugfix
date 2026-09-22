"""API 层测试：校验、健康检查与对位端点。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

BLADES12 = [f"B{i:02d}" for i in range(1, 13)]
REF_INTERVALS = [50, 52, 48, 51, 49, 53, 47, 55, 45, 49, 51, 50]  # 周长 600
MEAS_INTERVALS = [50, 100, 51, 49, 53, 47, 55, 45, 49, 51, 50]     # 周长 600


def _payload(**overrides):
    body = {
        "reference": {"blades": BLADES12, "intervals": REF_INTERVALS},
        "measured": {"intervals": MEAS_INTERVALS},
        "tolerance": 2,
        "budget": 4,
    }
    body.update(overrides)
    return body


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_match_unique():
    r = client.post("/api/match", json=_payload())
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "unique"
    assert data["objective"] == {
        "modifications": 1,
        "totalAbsError": 0,
        "maxGroupError": 0,
    }
    assert data["budget"] == {"limit": 4, "used": 1, "within": True}
    assert data["circumference"] == 600
    assert data["configurationsExamined"] == 2 * len(MEAS_INTERVALS)
    assert len(data["witnesses"]) == 1
    w = data["witnesses"][0]
    assert w["direction"] == "forward" and w["offset"] == 0
    assert len(w["groups"]) == 11
    merged = [g for g in w["groups"] if g["modifications"] > 0]
    assert len(merged) == 1
    assert merged[0]["refBlades"] == ["B02", "B03"]
    assert merged[0]["refSum"] == 100 and merged[0]["measSum"] == 100
    # 组完整覆盖参考环
    assert sum(g["refCount"] for g in w["groups"]) == 12
    assert sum(len(g["measIndices"]) for g in w["groups"]) == len(MEAS_INTERVALS)


def test_match_ambiguous_two_witnesses():
    payload = _payload(
        reference={"blades": BLADES12, "intervals": [40, 40, 55] * 4},
        measured={"intervals": [40, 40, 55] * 4},
        tolerance=1,
    )
    r = client.post("/api/match", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ambiguous"
    assert data["optimalMappingCount"] >= 2
    assert len(data["witnesses"]) == 2
    a, b = data["witnesses"]
    assert a["mappingId"] != b["mappingId"]
    # 两份见证都达到同一最优目标
    for w in (a, b):
        mods = sum(g["modifications"] for g in w["groups"])
        tot = sum(g["absError"] for g in w["groups"])
        mx = max(g["absError"] for g in w["groups"])
        assert (mods, tot, mx) == (0, 0, 0)


def test_match_no_solution():
    payload = _payload(
        reference={"blades": BLADES12, "intervals": [50] * 12},
        measured={"intervals": [53, 53, 53, 41] * 3},
        tolerance=1,
    )
    r = client.post("/api/match", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "no_solution"
    assert data["witnesses"] == []
    assert data["objective"] is None


def test_match_over_budget_flag():
    r = client.post("/api/match", json=_payload(budget=0))
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "unique"
    assert data["budget"]["within"] is False
    assert data["budget"]["used"] == 1


def test_circumference_mismatch_422():
    payload = _payload(measured={"intervals": [51] * 12})  # 周长 612 ≠ 600
    r = client.post("/api/match", json=payload)
    assert r.status_code == 422
    assert "周长" in str(r.json()["detail"])


def test_duplicate_blades_422():
    blades = BLADES12.copy()
    blades[3] = blades[0]
    r = client.post("/api/match", json=_payload(reference={"blades": blades, "intervals": REF_INTERVALS}))
    assert r.status_code == 422
    assert "唯一" in str(r.json()["detail"])


def test_blade_count_bounds_422():
    r = client.post(
        "/api/match",
        json=_payload(reference={"blades": BLADES12[:11], "intervals": REF_INTERVALS[:11]}),
    )
    assert r.status_code == 422


def test_measured_count_bounds_422():
    r = client.post("/api/match", json=_payload(measured={"intervals": [60] * 9}))
    assert r.status_code == 422


def test_non_positive_interval_422():
    meas = MEAS_INTERVALS.copy()
    meas[0] = 0
    r = client.post("/api/match", json=_payload(measured={"intervals": meas}))
    assert r.status_code == 422


def test_interval_length_mismatch_422():
    r = client.post(
        "/api/match",
        json=_payload(reference={"blades": BLADES12, "intervals": REF_INTERVALS[:11]}),
    )
    assert r.status_code == 422


def test_negative_tolerance_422():
    r = client.post("/api/match", json=_payload(tolerance=-1))
    assert r.status_code == 422
