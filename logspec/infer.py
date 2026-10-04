"""설계서가 없는 테이블: 정상 데이터를 프로파일링해 설계서 초안(YAML)을 만든다. 사람이 검토·확정한다.

추론하는 것   타입, not_null, unique, enum(문자열 고유값 ≤ 20), 숫자 범위(관측값에 여유), 형식(고정 길이 hex·접두어+숫자),
             FK(값이 다른 테이블의 고유 키에 모두 포함되고 이름이 맞을 때), 시간 필드·기간·일별 볼륨·enum 분포
추론하지 않는 것  업무 규칙(잔액 누적, 거래 미러, 세션 안 행동 등) — 의미를 알아야 해서 사람이 쓴다

  python -m logspec.infer --data data/dev --out specs/inferred
"""
import argparse
import os
import re

import yaml

from .checks import DUCK_TYPES, q
from .runner import connect_data

ENUM_MAX = 20


def _type(duck: str) -> str:
    base = duck.split("(")[0]
    for t, s in DUCK_TYPES.items():
        if base in s and t not in ("enum",):
            return t
    return "string"


def _pattern(vals: list[str]) -> str | None:
    if not vals:
        return None
    lens = {len(v) for v in vals}
    if len(lens) == 1 and all(re.fullmatch(r"[0-9a-f]+", v) for v in vals):
        return f"^[0-9a-f]{{{lens.pop()}}}$"
    shapes = set()
    for v in vals:
        m = re.fullmatch(r"([A-Za-z]+)([0-9]+)", v)
        if not m:
            return None
        shapes.add((m.group(1), len(m.group(2))))
    if len(shapes) <= 3:
        alts = "|".join(f"{p}[0-9]{{{n}}}" for p, n in sorted(shapes))
        return f"^({alts})$" if len(shapes) > 1 else f"^{alts}$"
    return None


def infer(data_dir: str) -> list[dict]:
    con = connect_data(data_dir)
    tables = [r[0] for r in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()]
    prof = {}
    for t in tables:
        cols = con.execute(f"DESCRIBE {q(t)}").fetchall()
        n = con.execute(f"SELECT count(*) FROM {q(t)}").fetchone()[0]
        prof[t] = {"n": n, "cols": {}}
        for c, duck, *_ in cols:
            ty = _type(duck)
            st = con.execute(f"SELECT count({q(c)}), count(DISTINCT {q(c)}) FROM {q(t)}").fetchone()
            prof[t]["cols"][c] = {"type": ty, "nonnull": st[0], "distinct": st[1], "duck": duck}
    # 다른 테이블의 고유 키 후보
    keys = {(t, c) for t in prof for c, p in prof[t]["cols"].items()
            if p["type"] == "int" and p["distinct"] == prof[t]["n"] == p["nonnull"] and c.endswith("_id")}
    out = []
    for t, P in prof.items():
        fields, enums, time_fields = {}, [], []
        for c, p in P["cols"].items():
            f = {"type": p["type"]}
            if p["nonnull"] == P["n"]:
                f["not_null"] = True
            if p["type"] == "int" and p["distinct"] == P["n"] and c.endswith("_id"):
                f["unique"] = True
            if p["type"] == "string" and 0 < p["distinct"] <= ENUM_MAX:
                vals = [r[0] for r in con.execute(f"SELECT DISTINCT {q(c)} FROM {q(t)} WHERE {q(c)} IS NOT NULL ORDER BY 1").fetchall()]
                f = {"type": "enum", "values": vals, **({"not_null": True} if f.get("not_null") else {})}
                enums.append(c)
            elif p["type"] == "string":
                sample = [r[0] for r in con.execute(f"SELECT DISTINCT {q(c)} FROM {q(t)} WHERE {q(c)} IS NOT NULL LIMIT 5000").fetchall()]
                pat = _pattern(sample)
                if pat:
                    f["pattern"] = pat
            if p["type"] in ("int", "float") and not f.get("unique"):
                lo, hi = con.execute(f"SELECT min({q(c)}), max({q(c)}) FROM {q(t)}").fetchone()
                if lo is not None and lo >= 0:
                    f["min"] = 0
                if hi is not None and hi > 0:
                    f["max"] = round(float(hi) * 1.5, 2) if p["type"] == "float" else int(hi * 1.5)
            if p["type"] == "int" and not f.get("unique"):
                for kt, kc in keys:
                    if kt != t and (c == kc or c.endswith(kc)):
                        miss = con.execute(f"SELECT count(*) FROM {q(t)} WHERE {q(c)} IS NOT NULL AND {q(c)} NOT IN (SELECT {q(kc)} FROM {q(kt)})").fetchone()[0]
                        if miss == 0:
                            f["fk"] = f"{kt}.{kc}"
                            break
            if p["type"] == "timestamp":
                time_fields.append(c)
            fields[c] = f
        spec = {"table": t, "description": f"자동 추론 초안 ({P['n']:,}행) — 검토 필요", "fields": fields}
        # 시간 필드: 기간 밖 값이 거의 없는 첫 timestamp 컬럼, 행이 많은 테이블만 볼륨·분포
        if time_fields:
            tf = time_fields[0]
            spec["time_field"] = tf
            if P["n"] >= 1000:
                spec["volume"] = {"daily_ratio_vs_median7": [0.5, 2.0]}
                if enums:
                    spec["drift"] = {"fields": enums[:2], "psi_max": 0.3}
        out.append(spec)
    return out


def prune(specs: list[dict], data_dir: str, period: tuple, out_dir: str) -> list[str]:
    """초안이 자기가 나온 정상 데이터에서 실패하는 검사를 뺀다 (예: 이벤트가 아닌 생성일 컬럼의 일별 볼륨)."""
    from .runner import validate
    removed = []
    for _ in range(5):
        write(specs, out_dir)
        res = validate(out_dir, data_dir, period)
        bad = res[res["status"] != "pass"]
        if bad.empty:
            break
        by = {s["table"]: s for s in specs}
        for _, r in bad.iterrows():
            s, f = by[r["table"]], r["field"]
            if r["kind"] == "volume":
                s.pop("volume", None)
            elif r["kind"] == "drift":
                s["drift"]["fields"] = [c for c in s["drift"]["fields"] if c != f]
                if not s["drift"]["fields"]:
                    s.pop("drift")
            elif f in s["fields"]:
                key = {"not_null": "not_null", "unique": "unique", "enum": "values", "range": None, "pattern": "pattern",
                       "fk": "fk"}.get(r["kind"])
                if r["kind"] == "range":
                    key = "min" if r["id"].endswith(":min") else "max"
                if key == "values":
                    s["fields"][f] = {"type": "string"}
                elif key:
                    s["fields"][f].pop(key, None)
            removed.append(r["id"])
            s.setdefault("description", "")
            s["description"] += f" · 제외 {r['id']}"
    write(specs, out_dir)
    return removed


def write(specs: list[dict], out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    for s in specs:
        yaml.safe_dump(s, open(os.path.join(out_dir, f"{s['table']}.yaml"), "w", encoding="utf-8"),
                       allow_unicode=True, sort_keys=False, default_flow_style=None, width=120)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/dev")
    ap.add_argument("--out", default="specs/inferred")
    ap.add_argument("--period", default="2026-09-01:2026-09-15")
    a = ap.parse_args()
    s = infer(a.data)
    removed = prune(s, a.data, tuple(a.period.split(":")), a.out)
    print(f"{len(s)}개 테이블 초안 → {a.out} · 정상 데이터에서 실패해 뺀 검사 {len(removed)}개: {removed}")
