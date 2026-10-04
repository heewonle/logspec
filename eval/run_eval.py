"""결함 주입 평가: 결함마다 검증을 돌려 정상 실행 대비 새로 걸린 검사를 센다.

  검출   정상 월드에서는 통과하던 검사가 하나라도 새로 실패/실행 불가
  위치   그중 결함이 잡혀야 할 검사(expected)가 있음
  오탐   정상 월드 자체에서 실패한 검사 수

  python -m eval.run_eval --world dev --period 2026-09-01:2026-09-15
"""
import argparse
import datetime as dt
import json
import os
import time

import pandas as pd

from logspec.runner import validate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(world: str, period: tuple, specs: str, tag: str):
    data = os.path.join(ROOT, "data")
    t0 = time.time()
    clean = validate(specs, os.path.join(data, world), period)
    clean_bad = set(clean.loc[clean["status"] != "pass", "id"])
    manifest = json.load(open(os.path.join(data, f"faults_{world}", "manifest.json"), encoding="utf-8"))
    rows, details = [], {}
    for F in manifest:
        res = validate(specs, os.path.join(data, f"faults_{world}", F["id"]), period)
        new = res[(res["status"] != "pass") & ~res["id"].isin(clean_bad)]
        fired = new["id"].tolist()
        details[F["id"]] = json.loads(new.to_json(orient="records", force_ascii=False, date_format="iso"))
        rows.append({"id": F["id"], "결함": F["name"], "검출": bool(fired),
                     "위치 맞힘": bool(set(F["expected"]) & set(fired)) if F["expected"] else None,
                     "걸린 검사": ", ".join(f"`{x}`" for x in fired[:4]) + (f" 외 {len(fired) - 4}" if len(fired) > 4 else ""),
                     "자동/사람": "/".join(sorted(set(new["judgment"].map({"auto": "자동", "human": "사람"})))) or "-"})
    df = pd.DataFrame(rows)
    secs = time.time() - t0
    out = os.path.join(ROOT, "out", f"eval_{world}_{tag}")
    os.makedirs(out, exist_ok=True)
    json.dump({"clean_failures": sorted(clean_bad), "faults": details}, open(os.path.join(out, "details.json"), "w",
              encoding="utf-8"), ensure_ascii=False, indent=1)
    covered = df[df["위치 맞힘"].notna()]
    md = [f"# 결함 주입 평가 — {world} 월드 · 설계서 `{os.path.relpath(specs, ROOT)}` ({dt.date.today()})", "",
          f"- 검사 {len(clean)}개 × (정상 1 + 결함 {len(df)}) 실행, {secs:.0f}초",
          f"- **정상 데이터 오탐: {len(clean_bad)}건**" + (f" ({', '.join(sorted(clean_bad))})" if clean_bad else ""),
          f"- **검출: {int(df['검출'].sum())}/{len(df)}**",
          f"- 위치까지 맞힘: {int(covered['위치 맞힘'].sum())}/{len(covered)} (기대 검사가 정해진 결함만)", "",
          df.to_markdown(index=False), ""]
    path = os.path.join(ROOT, "reports", f"eval_faults_{world}_{tag}.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write("\n".join(md))
    return path, df, clean_bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default="dev")
    ap.add_argument("--period", default="2026-09-01:2026-09-15")
    ap.add_argument("--specs", default=os.path.join(ROOT, "specs", "gameguard"))
    ap.add_argument("--tag", default="hand")
    a = ap.parse_args()
    path, df, clean_bad = run(a.world, tuple(a.period.split(":")), a.specs, a.tag)
    print(open(path, encoding="utf-8").read())
