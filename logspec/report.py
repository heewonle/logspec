"""검증 결과 → 사람이 읽는 리포트(md). 이슈 + 검증 체크리스트(검증 절차 문서 역할)."""
import datetime as dt
import json
import os

import pandas as pd

CAT_KO = {"schema": "스키마", "field": "필드 값", "business": "업무 규칙", "sequence": "순서·기간",
          "duplicate": "중복", "volume": "볼륨", "drift": "분포"}
STATUS_KO = {"pass": "통과", "fail": "위반", "error": "실행 불가"}


def _days(d):
    if not isinstance(d, dict) or not d:
        return "-"
    ks = sorted(d)
    span = ks[0] if len(ks) == 1 else f"{ks[0]} ~ {ks[-1]} ({len(ks)}일)"
    return span


def _issue_block(r) -> list[str]:
    n = r.get("n_bad")
    rate = r.get("rate")
    amount = "-" if n is None or pd.isna(n) else f"{int(n):,}행" + (f" ({rate:.2%})" if pd.notna(rate) and rate else "")
    lines = [f"#### `{r['id']}` — {r['description']}",
             f"- 무엇이: {CAT_KO.get(r['category'], r['category'])} / {r['kind']} · 상태 **{STATUS_KO[r['status']]}**",
             f"- 얼마나: {amount}",
             f"- 언제: {_days(r.get('days'))}"]
    if isinstance(r.get("detail"), str):
        lines.append(f"- 내용: {r['detail']}")
    if isinstance(r.get("sample"), list) and r["sample"]:
        lines.append("- 예시: `" + json.dumps(r["sample"][0], ensure_ascii=False)[:300] + "`")
    return lines + [""]


def write_report(res: pd.DataFrame, out_dir: str, data: str, period: str | None, seconds: float,
                 llm_notes: dict | None = None) -> str:
    bad = res[res["status"] != "pass"]
    auto = bad[bad["judgment"] == "auto"]
    human = bad[bad["judgment"] == "human"]
    by_cat = res.assign(cat=res["category"].map(CAT_KO)).pivot_table(
        index="cat", columns="status", values="id", aggfunc="count", fill_value=0)
    md = [f"# 로그 검증 리포트 ({dt.datetime.now():%Y-%m-%d %H:%M})", "",
          f"- 데이터 `{data}` · 기간 `{period}` · 검사 {len(res)}개 · {seconds:.1f}초",
          f"- 위반 **{int((res['status'] == 'fail').sum())}** · 실행 불가 {int((res['status'] == 'error').sum())} · "
          f"자동 판정 이슈 {len(auto)} · 사람 확인 필요 {len(human)}", "",
          "## 분류별", "", by_cat.reset_index().rename(columns={"cat": "분류"}).to_markdown(index=False), ""]
    if llm_notes:
        md += ["## 요약 (LLM)", "", llm_notes.get("summary", ""), ""]
    md += ["## 자동 판정 이슈", "", "설계서와 다르면 곧 문제인 항목 (타입·null·허용값·범위·참조·순서·중복).", ""]
    for _, r in auto.iterrows():
        md += _issue_block(r)
        if llm_notes and r["id"] in llm_notes.get("by_check", {}):
            md += ["> " + llm_notes["by_check"][r["id"]], ""]
    if auto.empty:
        md += ["없음", ""]
    md += ["## 사람 확인 필요", "", "점검·이벤트·패치일 수도 있어 해석이 필요한 항목 (볼륨·분포·설계서에 없는 컬럼).", ""]
    for _, r in human.iterrows():
        md += _issue_block(r)
    if human.empty:
        md += ["없음", ""]
    md += ["## 검증 체크리스트", "",
           "| 검사 | 분류 | 판정 | 상태 | 위반 |", "|---|---|---|---|---:|"]
    for _, r in res.iterrows():
        n = "" if r["n_bad"] is None or pd.isna(r["n_bad"]) else f"{int(r['n_bad']):,}"
        md.append(f"| `{r['id']}` | {CAT_KO.get(r['category'], r['category'])} | "
                  f"{'자동' if r['judgment'] == 'auto' else '사람'} | {STATUS_KO[r['status']]} | {n} |")
    path = os.path.join(out_dir, "report.md")
    open(path, "w", encoding="utf-8").write("\n".join(md) + "\n")
    return path
