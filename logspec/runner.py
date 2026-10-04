"""적재 데이터(Parquet 폴더)에 설계서 검사를 돌린다.

  python -m logspec.runner --specs specs/gameguard --data data/dev --period 2026-09-01:2026-09-15 --out out/dev
"""
import argparse
import glob
import json
import os
import time

import duckdb
import pandas as pd

from .checks import DUCK_TYPES, Check, build_checks, q
from .spec import load_specs

SAMPLE_ROWS = 3


def connect_data(data_dir: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for f in sorted(glob.glob(os.path.join(data_dir, "*.parquet"))):
        name = os.path.splitext(os.path.basename(f))[0]
        con.execute(f"CREATE VIEW {q(name)} AS SELECT * FROM read_parquet('{f.replace(chr(92), '/')}')")
    return con


def _columns(con, table):
    try:
        return {r[0]: r[1] for r in con.execute(f"DESCRIBE {q(table)}").fetchall()}
    except duckdb.Error:
        return None


def schema_checks(con, spec) -> list[dict]:
    """테이블·컬럼 존재와 타입. SQL 검사보다 먼저 돈다."""
    out = []
    cols = _columns(con, spec.table)
    base = dict(table=spec.table, category="schema", judgment="auto", severity="error")
    if cols is None:
        return [dict(base, id=f"{spec.table}:exists", field=None, kind="missing_table",
                     description="테이블이 적재돼 있어야 함", status="fail", n_bad=1, detail="테이블 없음")]
    for name, f in spec.fields.items():
        if name not in cols:
            out.append(dict(base, id=f"{spec.table}.{name}:exists", field=name, kind="missing_column",
                            description="설계서의 컬럼이 있어야 함", status="fail", n_bad=1, detail="컬럼 없음"))
            continue
        actual = cols[name].split("(")[0]
        ok = actual in DUCK_TYPES[f["type"]]
        out.append(dict(base, id=f"{spec.table}.{name}:type", field=name, kind="type",
                        description=f"타입 {f['type']}", status="pass" if ok else "fail", n_bad=0 if ok else 1,
                        detail=None if ok else f"설계 {f['type']} / 실제 {cols[name]}"))
    for extra in sorted(set(cols) - set(spec.fields)):
        out.append(dict(base, id=f"{spec.table}.{extra}:unexpected", field=extra, kind="unexpected_column",
                        description="설계서에 없는 컬럼", status="fail", n_bad=1, severity="warn", judgment="human",
                        detail=f"설계서에 없음 ({cols[extra]})"))
    return out


def run_check(con, c: Check, cols: dict | None, time_field: str | None) -> dict:
    res = dict(id=c.id, table=c.table, field=c.field, kind=c.kind, category=c.category, description=c.description,
               severity=c.severity, judgment=c.judgment)
    missing = [n for n in c.needs if cols is None or n not in cols]
    if missing:
        return dict(res, status="error", n_bad=None, detail=f"실행 불가: 컬럼 없음 {missing}")
    t0 = time.time()
    try:
        if c.count_sql:
            n = int(con.execute(c.count_sql).fetchone()[0] or 0)
            return dict(res, status="fail" if n else "pass", n_bad=n, ms=int((time.time() - t0) * 1000))
        n = con.execute(f"SELECT count(*) FROM ({c.sql})").fetchone()[0]
        out = dict(res, status="fail" if n else "pass", n_bad=int(n), ms=int((time.time() - t0) * 1000))
        if n:
            sample = con.execute(f"SELECT * FROM ({c.sql}) LIMIT {SAMPLE_ROWS}").df()
            out["sample"] = json.loads(sample.to_json(orient="records", date_format="iso", force_ascii=False))
            tf = time_field
            if c.kind in ("volume", "drift"):
                out["days"] = {str(r[0])[:10]: r[1] for r in con.execute(f"SELECT * FROM ({c.sql})").fetchall()}
            elif tf and tf in sample.columns:
                days = con.execute(f"SELECT {q(tf)}::DATE AS d, count(*) FROM ({c.sql}) GROUP BY 1 ORDER BY 1").fetchall()
                out["days"] = {str(d): int(k) for d, k in days if d is not None}
        return out
    except duckdb.Error as e:
        return dict(res, status="error", n_bad=None, detail=f"실행 오류: {str(e).splitlines()[0][:200]}")


def validate(specs_path: str, data_dir: str, period: tuple | None) -> pd.DataFrame:
    con = connect_data(data_dir)
    rows = []
    for spec in load_specs(specs_path):
        cols = _columns(con, spec.table)
        rows += schema_checks(con, spec)
        if cols is None:
            continue
        n_rows = con.execute(f"SELECT count(*) FROM {q(spec.table)}").fetchone()[0]
        for c in build_checks(spec, period):
            r = run_check(con, c, cols, spec.time_field)
            r["n_rows"] = n_rows
            rows.append(r)
    df = pd.DataFrame(rows)
    df["rate"] = df["n_bad"] / df.get("n_rows")
    return df


def parse_period(s: str | None):
    if not s:
        return None
    a, b = s.split(":")
    return (a, b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", default="specs/gameguard")
    ap.add_argument("--data", required=True)
    ap.add_argument("--period", help="적재 기간 시작:끝 (끝 미포함), 예 2026-09-01:2026-09-15")
    ap.add_argument("--out", default="out/latest")
    ap.add_argument("--summarize", action="store_true",
                    help="이슈 요약 추가: 원인 분류는 규칙(검사 종류), 요약·확인할 것은 로컬 LLM")
    a = ap.parse_args()
    t0 = time.time()
    res = validate(a.specs, a.data, parse_period(a.period))
    os.makedirs(a.out, exist_ok=True)
    res.to_json(os.path.join(a.out, "results.json"), orient="records", force_ascii=False, indent=1, date_format="iso")
    from .report import write_report
    notes = None
    bad = res[res["status"] != "pass"]
    if a.summarize and len(bad):
        from .llm import baseline, summarize
        fails = json.loads(bad.to_json(orient="records", force_ascii=False, date_format="iso"))
        s = summarize(fails)
        notes = {"summary": "\n".join([
            f"**추정 원인 (규칙): {baseline(fails)}**", "",
            f"- 무엇이: {s.get('what')}", f"- 얼마나: {s.get('how_much')}", f"- 언제부터: {s.get('since_when')}",
            "- 확인할 것: " + " · ".join(s.get("checks_to_do", [])), f"- 담당: {s.get('owner')}", "",
            f"> LLM 의견: {s.get('cause')} — {s.get('cause_reason')} "
            "(원인 분류는 평가에서 규칙 기준선이 더 정확해 규칙을 따른다)"])}
    path = write_report(res, a.out, data=a.data, period=a.period, seconds=time.time() - t0, llm_notes=notes)
    fail = res[res["status"] != "pass"]
    print(f"검사 {len(res)}개 · 실패 {int((res['status'] == 'fail').sum())} · 실행 불가 {int((res['status'] == 'error').sum())} "
          f"· {time.time() - t0:.1f}초 → {path}")
    if len(fail):
        print(fail[["id", "status", "n_bad"]].to_string(index=False))


if __name__ == "__main__":
    main()
