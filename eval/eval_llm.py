"""LLM 원인 추정 평가: 결함 평가(run_eval)의 '새로 걸린 검사'를 입력으로, 추정 원인이 결함의 원인과 맞는지.

  엄격 = 정답 원인과 같음 / 관대 = 정답 또는 그렇게 볼 수도 있는 원인(alt_causes)
  기준선 = LLM 없이 검사 종류 우선순위로 고른 원인

  python -m eval.eval_llm --world dev
"""
import argparse
import datetime as dt
import json
import os

import pandas as pd

import re

from logspec.llm import baseline, brief, summarize


def grounded(summary: dict, fails: list) -> bool:
    """요약의 숫자·날짜가 LLM 에 준 입력에 있는가 (지어낸 수치·날짜 검사)."""
    src = brief(fails)
    text = " ".join(str(summary.get(k, "")) for k in ("what", "how_much", "since_when"))
    for d in re.findall(r"\d{4}-\d{2}-\d{2}", text):
        if d not in src:
            return False
    nums = [n.replace(",", "") for n in re.findall(r"\d[\d,]*\.?\d*", re.sub(r"\d{4}-\d{2}-\d{2}", "", text))]
    have = set(n.replace(",", "") for n in re.findall(r"\d[\d,]*\.?\d*", src))
    return all(n in have or len(n) <= 1 for n in nums)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default="dev")
    ap.add_argument("--tag", default="hand")
    ap.add_argument("--model", default=None)
    ap.add_argument("--hybrid", action="store_true", help="규칙 기준선의 1순위 후보를 LLM에 주고 확인·수정하게 한다")
    a = ap.parse_args()
    det = json.load(open(os.path.join(ROOT, "out", f"eval_{a.world}_{a.tag}", "details.json"), encoding="utf-8"))
    man = {F["id"]: F for F in json.load(open(os.path.join(ROOT, "data", f"faults_{a.world}", "manifest.json"), encoding="utf-8"))}
    rows, raw = [], {}
    for fid, fails in det["faults"].items():
        if not fails:
            continue
        F = man[fid]
        s = summarize(fails, a.model, a.hybrid)
        raw[fid] = s
        ok = {F["cause"]} | set(F["alt_causes"])
        b = baseline(fails)
        rows.append({"id": fid, "결함": F["name"], "정답 원인": F["cause"], "LLM": s.get("cause"), "기준선": b,
                     "LLM 엄격": s.get("cause") == F["cause"], "LLM 관대": s.get("cause") in ok,
                     "기준선 엄격": b == F["cause"], "기준선 관대": b in ok, "요약 근거": grounded(s, fails),
                     "초": s["_seconds"]})
        print(fid, F["cause"], "→", s.get("cause"), "/ 기준선", b, flush=True)
    df = pd.DataFrame(rows)
    mode = "hybrid" if a.hybrid else "llm"
    out = os.path.join(ROOT, "out", f"{mode}_{a.world}_{a.tag}.json")
    json.dump(raw, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    model = next(iter(raw.values()))["_model"] if raw else "-"
    md = [f"# LLM 원인 추정 평가 ({'규칙 후보 + LLM 확인' if a.hybrid else 'LLM 단독'}) — {a.world} 월드 ({dt.date.today()})", "",
          f"- 모델 `{model}` (로컬 Ollama, 비용 0원) · 검출된 결함 {len(df)}종 · 건당 중앙값 {df['초'].median():.1f}초",
          f"- **LLM 원인 일치: 엄격 {df['LLM 엄격'].mean():.0%} ({int(df['LLM 엄격'].sum())}/{len(df)}) · "
          f"관대 {df['LLM 관대'].mean():.0%}**",
          f"- 기준선(검사 종류 우선순위): 엄격 {df['기준선 엄격'].mean():.0%} · 관대 {df['기준선 관대'].mean():.0%}",
          f"- 요약의 숫자·날짜가 입력에 있는 비율(지어내지 않음): {df['요약 근거'].mean():.0%}", "",
          df.to_markdown(index=False), "",
          "## 요약 예시", ""]
    for fid in list(raw)[:3]:
        s = raw[fid]
        md += [f"**{fid}** — {s.get('what')} / {s.get('how_much')} / {s.get('since_when')}",
               f"- 원인: {s.get('cause')} — {s.get('cause_reason')}",
               f"- 확인할 것: " + " · ".join(s.get("checks_to_do", [])) + f" (담당 {s.get('owner')})", ""]
    path = os.path.join(ROOT, "reports", f"eval_{mode}_{a.world}_{a.tag}.md")
    open(path, "w", encoding="utf-8").write("\n".join(md))
    print(open(path, encoding="utf-8").read())


if __name__ == "__main__":
    main()
