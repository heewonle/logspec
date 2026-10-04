"""로그 설계서(YAML) 읽기와 형식 검사.

설계서에 모르는 키가 있으면 바로 에러를 낸다 — 오타 하나로 검사가 조용히 빠지는 것을 막기 위해.
"""
import glob
import os
from dataclasses import dataclass, field

import yaml

TYPES = {"int", "float", "string", "timestamp", "enum", "bool"}
FIELD_KEYS = {"type", "not_null", "unique", "values", "min", "max", "pattern", "fk", "not_equal",
              "within_period", "description"}
TABLE_KEYS = {"table", "description", "key", "time_field", "fields", "rules", "duplicates", "volume", "drift"}
RULE_KEYS = {"name", "description", "row", "violations", "count", "running_balance", "judgment", "severity"}
RULE_KINDS = {"row", "violations", "count", "running_balance"}


class SpecError(ValueError):
    pass


@dataclass
class TableSpec:
    table: str
    fields: dict
    description: str = ""
    key: list = field(default_factory=list)
    time_field: str | None = None
    rules: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)
    volume: dict = field(default_factory=dict)
    drift: dict = field(default_factory=dict)
    source: str = ""


def _check_table(d: dict, src: str) -> TableSpec:
    where = f"{os.path.basename(src)}:{d.get('table', '?')}"
    unknown = set(d) - TABLE_KEYS
    if unknown:
        raise SpecError(f"{where}: 모르는 테이블 키 {sorted(unknown)}")
    if "table" not in d or "fields" not in d:
        raise SpecError(f"{where}: table, fields 는 필수")
    for name, f in d["fields"].items():
        f = f or {}
        bad = set(f) - FIELD_KEYS
        if bad:
            raise SpecError(f"{where}.{name}: 모르는 필드 키 {sorted(bad)}")
        if f.get("type") not in TYPES:
            raise SpecError(f"{where}.{name}: type 은 {sorted(TYPES)} 중 하나 (현재 {f.get('type')!r})")
        if f["type"] == "enum" and not f.get("values"):
            raise SpecError(f"{where}.{name}: enum 은 values 필요")
        if "fk" in f and "." not in f["fk"]:
            raise SpecError(f"{where}.{name}: fk 는 '테이블.컬럼' 형식")
        if "not_equal" in f and f["not_equal"] not in d["fields"]:
            raise SpecError(f"{where}.{name}: not_equal 대상 {f['not_equal']} 이 fields 에 없음")
    for c in d.get("key", []) + d.get("duplicates", []):
        if c not in d["fields"]:
            raise SpecError(f"{where}: key/duplicates 의 {c} 가 fields 에 없음")
    tf = d.get("time_field")
    if tf and d["fields"].get(tf, {}).get("type") != "timestamp":
        raise SpecError(f"{where}: time_field {tf} 는 timestamp 필드여야 함")
    for r in d.get("rules", []):
        bad = set(r) - RULE_KEYS
        if bad:
            raise SpecError(f"{where}: 룰 {r.get('name')} 의 모르는 키 {sorted(bad)}")
        kinds = RULE_KINDS & set(r)
        if len(kinds) != 1:
            raise SpecError(f"{where}: 룰 {r.get('name')} 는 {sorted(RULE_KINDS)} 중 정확히 하나가 필요")
        if "name" not in r:
            raise SpecError(f"{where}: 이름 없는 룰")
    for c in (d.get("drift") or {}).get("fields", []):
        if c not in d["fields"]:
            raise SpecError(f"{where}: drift 필드 {c} 가 fields 에 없음")
    if (d.get("volume") or d.get("drift")) and not tf:
        raise SpecError(f"{where}: volume/drift 는 time_field 가 필요")
    return TableSpec(table=d["table"], fields={k: (v or {}) for k, v in d["fields"].items()},
                     description=d.get("description", ""), key=d.get("key", []), time_field=tf,
                     rules=d.get("rules", []), duplicates=d.get("duplicates", []),
                     volume=d.get("volume") or {}, drift=d.get("drift") or {}, source=src)


def load_specs(path: str) -> list[TableSpec]:
    files = sorted(glob.glob(os.path.join(path, "*.yaml"))) if os.path.isdir(path) else [path]
    out = []
    for f in files:
        doc = yaml.safe_load(open(f, encoding="utf-8")) or {}
        tables = doc["tables"] if "tables" in doc else [doc]
        out += [_check_table(t, f) for t in tables]
    names = [t.table for t in out]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        raise SpecError(f"같은 테이블이 여러 번 정의됨: {sorted(dup)}")
    return out
