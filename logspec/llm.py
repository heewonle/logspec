"""LLM 이슈 요약: 한 번의 적재에서 걸린 검사들 → 추정 원인 · 무엇이/얼마나/언제부터 · 확인할 것 · 담당.

로컬 Ollama (기본 qwen3-vl:8b-instruct, 무료). 같은 입력에 대해 LLM 없이 검사 종류로 원인을 고르는 기준선도 둔다.
"""
import json
import os
import time

CAUSES = {
    "스키마 변경": "컬럼 추가·삭제·이름·타입이 설계서와 다름 (배포에서 로그 스키마가 바뀜)",
    "수집·클라이언트 버그": "클라이언트/수집기가 값을 빠뜨리거나 다른 형식(대소문자 등)으로 보냄",
    "사양에 없는 신규 값": "새 기능의 값이 설계서 허용값에 반영되지 않음",
    "타임존": "시각이 일정 시간(예: 9시간) 통째로 밀림",
    "중복 적재": "같은 데이터가 두 번 적재되거나 재처리로 다시 들어옴",
    "적재 누락": "기간·파티션의 데이터 일부 또는 전체가 들어오지 않음",
    "서버 로직 버그": "서버 계산·검증 로직 오류 (잔액 계산, 부호, 금지된 거래 허용 등)",
    "참조 데이터 불일치": "참조하는 마스터(계정·아이템·세션)에 없는 키",
    "단위 변경": "값의 단위·배율이 바뀜 (원→전, ×100, ÷2)",
    "클라이언트 시계": "개별 기기 시계가 틀려 일부 행만 비정상 시각",
    "수집 설정 변경": "수집 필터·샘플링 설정이 바뀌어 특정 종류만 들어오거나 빠짐",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "what": {"type": "string"},
        "how_much": {"type": "string"},
        "since_when": {"type": "string"},
        "cause": {"type": "string", "enum": list(CAUSES)},
        "cause_reason": {"type": "string"},
        "checks_to_do": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "owner": {"type": "string", "enum": ["클라이언트", "서버", "데이터 엔지니어링", "기획"]},
    },
    "required": ["what", "how_much", "since_when", "cause", "cause_reason", "checks_to_do", "owner"],
}

SYSTEM = """너는 게임 로그 데이터 QA 담당자다. 하루치 적재 데이터를 로그 설계서와 대조한 검증에서 새로 실패한 검사 목록을 받는다.
이 실패들이 함께 가리키는 **하나의 근본 원인**을 원인 목록에서 고르고, 검토자에게 넘길 이슈 요약을 쓴다.

원인 목록:
{causes}

판단 요령 (원인별 단서)
- 스키마 변경: missing_column / type / unexpected_column. 이게 있으면 같은 컬럼의 다른 검사 실패는 연쇄 효과다
- 사양에 없는 신규 값: 허용값(enum) 밖의 값이 정상 형식의 처음 보는 단어 (예: 'auction')
- 수집·클라이언트 버그: null 증가, 또는 허용값과 철자는 같고 형식만 다른 값 (대소문자 등)
- 타임존: 하루치 시각이 통째로 밀려 '세션 밖 행동'·'세션 겹침'이 같은 날에 몰리고, 볼륨이 이웃 날로 옮겨감
- 중복 적재: 키 중복, 또는 짝을 이루는 테이블과 개수가 안 맞으면서(미러 검사) 이쪽 행이 많음, 특정일에 몰림
- 적재 누락: 특정일 행 수 급감·0, 그날만 누적 잔액이 끊기거나 짝 기록(결제 지급 등)이 없음
- 서버 로직 버그: 계산·규칙 위반이 소수 비율로 **전 기간에 분산** (누적 잔액 오류, 부호 반전, 자기 거래)
- 참조 데이터 불일치: fk 위반 (참조 마스터에 없는 키)
- 단위 변경: 특정일부터 계속 상한·하한을 넘음 (배율처럼 일정하게 커지거나 작아짐)
- 클라이언트 시계: 극소수 행만 먼 미래·과거 시각, 여러 날에 흩어짐
- 수집 설정 변경: 특정일 분포가 한 값으로 쏠리고(drift) 그날 행 수가 줄어듦 (일부 종류만 수집)
- pattern(한 날에 집중/특정일부터 계속/전 기간에 분산)과 sample 의 실제 값을 함께 본다

규칙
- since_when 은 입력의 first_day·top_day·days 날짜로만 쓴다. 배포·작업 이력처럼 입력에 없는 사실을 지어내지 않는다
- 수치는 입력에 있는 값만 쓴다

출력: what(무엇이 설계서와 다른가), how_much(행 수·비율), since_when(날짜), cause, cause_reason(근거 한두 문장),
checks_to_do(담당자가 확인할 것 2~3개), owner. 모두 한국어로 짧게."""


def brief(failures: list[dict]) -> str:
    """검사별 요약 + 날짜 집중도 힌트 (v2: 하루 집중 vs 전 기간 분산이 원인 구분의 핵심 단서)."""
    keep = []
    for f in failures[:8]:
        d = {k: v for k, v in (f.get("days") or {}).items() if isinstance(v, (int, float))}
        top = max(d, key=d.get) if d else None
        conc = None
        if d and f["kind"] not in ("volume", "drift"):
            share = d[top] / max(sum(d.values()), 1)
            conc = "한 날에 집중" if share >= 0.8 else ("특정일부터 계속" if len(d) <= 8 and min(d) >= top else "전 기간에 분산")
        keep.append({k: v for k, v in {
            "check": f["id"], "kind": f["kind"], "category": f["category"], "rule": f.get("description"),
            "n_bad": f.get("n_bad"), "rate": round(f["rate"], 4) if isinstance(f.get("rate"), float) else None,
            "days": (f.get("days") if f["kind"] in ("volume", "drift") else None),
            "first_day": min(d) if d else None, "last_day": max(d) if d else None, "n_days": len(d) if d else None,
            "top_day": top, "pattern": conc,
            "detail": f.get("detail"), "sample": (f.get("sample") or [None])[0],
        }.items() if v is not None})
    return json.dumps(keep, ensure_ascii=False, default=str)


def summarize(failures: list[dict], model: str = None, hybrid: bool = False) -> dict:
    import ollama
    model = model or os.environ.get("LOGSPEC_LLM", "qwen3-vl:8b-instruct")
    sys = SYSTEM.format(causes="\n".join(f"- {k}: {v}" for k, v in CAUSES.items()))
    t0 = time.time()
    r = ollama.Client().chat(model=model, format=SCHEMA, options={"temperature": 0.1, "num_predict": 1024, "num_ctx": 8192},
                             messages=[{"role": "system", "content": sys},
                                       {"role": "user", "content": "새로 실패한 검사:\n" + brief(failures)}])
    try:
        out = json.loads(r.message.content)
    except json.JSONDecodeError:
        out = {"cause": None, "_raw": r.message.content[:300]}
    out.update(_model=model, _seconds=round(time.time() - t0, 1), _tokens_in=r.prompt_eval_count, _tokens_out=r.eval_count)
    return out


# LLM 없이: 가장 '원인 쪽'에 가까운 검사 종류로 고른다 (우선순위 순)
BASELINE = [("missing_column", "스키마 변경"), ("type", "스키마 변경"), ("unexpected_column", "스키마 변경"),
            ("enum", "사양에 없는 신규 값"), ("unique", "중복 적재"), ("duplicate", "중복 적재"),
            ("fk", "참조 데이터 불일치"), ("not_equal", "서버 로직 버그"), ("running_balance", "서버 로직 버그"),
            ("not_null", "수집·클라이언트 버그"), ("period", "클라이언트 시계"), ("range", "단위 변경"),
            ("volume", "적재 누락"), ("drift", "수집 설정 변경"), ("rule_sql", "서버 로직 버그"),
            ("rule_count", "중복 적재"), ("rule_row", "서버 로직 버그")]


def baseline(failures: list[dict]) -> str | None:
    kinds = {f["kind"] for f in failures}
    for k, c in BASELINE:
        if k in kinds:
            return c
    return None
