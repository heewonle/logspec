"""검증기 자체 테스트: 설계서 형식 검사, 검사별로 작은 결함을 넣으면 그 검사가 걸리는지, 초안 추론, 원인 기준선."""
import os
import sys

import pandas as pd
import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from logspec.infer import infer, prune  # noqa: E402
from logspec.llm import baseline  # noqa: E402
from logspec.runner import validate  # noqa: E402
from logspec.spec import SpecError, load_specs  # noqa: E402

PERIOD = ("2026-09-01", "2026-09-04")

SPEC = {
    "table": "events", "time_field": "ts", "key": ["event_id"],
    "fields": {
        "event_id": {"type": "int", "not_null": True, "unique": True},
        "ts": {"type": "timestamp", "not_null": True, "within_period": True},
        "user_id": {"type": "int", "not_null": True, "fk": "users.user_id"},
        "peer_id": {"type": "int", "not_equal": "user_id"},
        "kind": {"type": "enum", "values": ["a", "b"]},
        "amount": {"type": "int", "min": 0, "max": 100},
        "code": {"type": "string", "pattern": "^C[0-9]{3}$"},
    },
    "rules": [{"name": "amount_by_kind", "row": "kind <> 'b' OR amount > 0"}],
    "volume": {"daily_ratio_vs_median7": [0.5, 2.0]},
}


def make(tmp, events=None, users=None, spec=SPEC):
    d = tmp / "data"
    s = tmp / "specs"
    d.mkdir(exist_ok=True)
    s.mkdir(exist_ok=True)
    n = 300
    ev = events if events is not None else pd.DataFrame({
        "event_id": range(n), "ts": pd.date_range("2026-09-01", periods=n, freq="14min"),
        "user_id": [i % 10 for i in range(n)], "peer_id": [(i + 1) % 10 for i in range(n)],
        "kind": ["a", "b"] * (n // 2), "amount": [5] * n, "code": ["C001"] * n})
    (users if users is not None else pd.DataFrame({"user_id": range(10)})).to_parquet(d / "users.parquet")
    ev.to_parquet(d / "events.parquet")
    yaml.safe_dump(spec, open(s / "events.yaml", "w"))
    yaml.safe_dump({"table": "users", "key": ["user_id"], "fields": {"user_id": {"type": "int", "unique": True}}},
                   open(s / "users.yaml", "w"))
    return str(s), str(d), ev


def failed(res):
    return set(res.loc[res["status"] != "pass", "id"])


def test_clean_passes(tmp_path):
    s, d, _ = make(tmp_path)
    assert failed(validate(s, d, PERIOD)) == set()


@pytest.mark.parametrize("mutate, expect", [
    (lambda e: e.assign(amount=e["amount"].astype(str)), "events.amount:type"),
    (lambda e: e.drop(columns="code"), "events.code:exists"),
    (lambda e: e.assign(extra=1), "events.extra:unexpected"),
    (lambda e: e.assign(user_id=e["user_id"].where(e.index > 5)), "events.user_id:not_null"),
    (lambda e: pd.concat([e, e.head(3)]), "events.event_id:unique"),
    (lambda e: e.assign(kind=e["kind"].replace("a", "A")), "events.kind:enum"),
    (lambda e: e.assign(amount=e["amount"].where(e.index > 0, -1)), "events.amount:min"),
    (lambda e: e.assign(amount=e["amount"].where(e.index > 0, 999)), "events.amount:max"),
    (lambda e: e.assign(code=e["code"].where(e.index > 0, "X1")), "events.code:pattern"),
    (lambda e: e.assign(user_id=e["user_id"].where(e.index > 0, 77)), "events.user_id:fk"),
    (lambda e: e.assign(peer_id=e["user_id"]), "events.peer_id:not_equal"),
    (lambda e: e.assign(ts=e["ts"].where(e.index > 0, pd.Timestamp("2030-01-01"))), "events.ts:period"),
    (lambda e: e.assign(amount=e["amount"].where(e["kind"] != "b", 0)), "events:rule:amount_by_kind"),
    (lambda e: e[e["ts"].dt.date != pd.Timestamp("2026-09-02").date()], "events:volume"),
])
def test_each_check_catches_its_fault(tmp_path, mutate, expect):
    s, d, ev = make(tmp_path)
    make(tmp_path, events=mutate(ev))
    assert expect in failed(validate(s, d, PERIOD))


def test_spec_rejects_unknown_keys(tmp_path):
    bad = dict(SPEC, fields={**SPEC["fields"], "amount": {"type": "int", "minimum": 0}})
    s, _, _ = make(tmp_path, spec=bad)
    with pytest.raises(SpecError):
        load_specs(s)


def test_spec_rejects_bad_type(tmp_path):
    bad = dict(SPEC, fields={**SPEC["fields"], "amount": {"type": "integer"}})
    s, _, _ = make(tmp_path, spec=bad)
    with pytest.raises(SpecError):
        load_specs(s)


def test_inferred_spec_passes_its_own_data(tmp_path):
    _, d, _ = make(tmp_path)
    specs = infer(d)
    out = str(tmp_path / "inferred")
    prune(specs, d, PERIOD, out)
    assert failed(validate(out, d, PERIOD)) == set()
    ev = next(s for s in specs if s["table"] == "events")
    assert ev["fields"]["kind"]["type"] == "enum"
    assert ev["fields"]["user_id"].get("fk") == "users.user_id"


def test_baseline_cause_priority():
    assert baseline([{"kind": "not_null"}, {"kind": "missing_column"}]) == "스키마 변경"
    assert baseline([{"kind": "volume"}]) == "적재 누락"
    assert baseline([{"kind": "fk"}]) == "참조 데이터 불일치"
