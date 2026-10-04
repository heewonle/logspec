# LogSpec — 로그 설계서와 적재 데이터 자동 대조

YAML로 쓴 **로그 설계서**(테이블·필드·타입·허용값·범위·참조·순서 규칙·볼륨·분포)를 읽어 **검증 SQL을 자동 생성**하고, 적재된 데이터(Parquet)에 돌려 설계서와 다른 점을 찾는다. 이슈는 **자동 판정**(위반이면 곧 문제)과 **사람 확인 필요**(점검·이벤트일 수도 있는 볼륨·분포 변화)로 나눠 리포트하고, 전체 검사 목록을 **검증 체크리스트**로 남긴다.

데이터는 [GameGuard](https://github.com/heewonle/gameguard)의 합성 MMORPG 로그(14일, 행동 130만 행 등 9개 테이블)를 쓴다.

## 결과 — 결함 20종 주입 (평가 월드 seed 99, 설계서·임계값은 개발 월드 seed 7에서만 정함)

| 설계서 | 검사 | 정상 데이터 오탐 | 검출 | 위치까지 맞힘 | 시간 |
|---|---:|---:|---:|---:|---:|
| **사람이 쓴 설계서** (`specs/gameguard`) | 176 | **0** | **18/20** | 18/18 | 1회 0.6초 |
| 자동 추론 초안 (`specs/inferred`) | 182 | 1 | 13/20 | 11/18 | 1회 0.4초 |

- 결함 20종은 설계서가 무엇을 잡는지와 상관없이 **현장에서 흔한 로그 문제**로 골랐다 — 스키마 변경 3, 수집 버그 2, 신규 enum, 타임존 9시간, 중복·재처리 적재 2, 누락 3, 잔액 계산 오류, FK, 부호 반전, 단위 변경 2, 자기 거래, 미래 시각, 수집 필터 오류
- **설계서를 결함보다 먼저 썼다.** 설계서 커밋(`9e81573`) 뒤에 결함 코드(`14abd93`)를 썼다 — 설계서를 결함에 맞추지 않기 위해
- **놓친 2종은 고치지 않고 한계로 남겼다**: 허용 범위 안에서 금액이 절반이 된 날(F19), 하루 마지막 3시간이 늦게 도착해 12% 빠진 날(F20). 잡으려면 수치 분포 드리프트·시간대별 볼륨 검사가 필요하다 — 결함을 본 뒤 그 결함용 검사를 넣고 같은 결함으로 재면 점수가 부풀려지므로 넣지 않았다
- **자동 초안 vs 사람 설계서**: 초안은 타입·null·enum·범위 같은 필드 수준 결함은 잡지만, 잔액 누적·자기 거래·거래-원장 미러·세션 안 행동 같은 **의미를 알아야 쓰는 업무 규칙**이 없어 5종을 더 놓친다. 초안 → 사람이 업무 규칙 추가가 맞는 순서

상세: [사람 설계서](reports/eval_faults_eval_hand.md) · [자동 초안](reports/eval_faults_eval_inferred.md) · [리포트 예시](reports/sample_report_F07_timezone.md)

## 설계서 예시 (`specs/gameguard/trades.yaml`)

```yaml
table: trades
description: 1:1 거래와 거래소 체결. 골드는 buyer → seller, item_id=0 이면 아이템 없는 송금
key: [trade_id]
time_field: ts
fields:
  ts:       {type: timestamp, not_null: true, within_period: true}
  trade_id: {type: int, not_null: true, unique: true}
  seller:   {type: int, not_null: true, fk: accounts.account_id}
  buyer:    {type: int, not_null: true, fk: accounts.account_id, not_equal: seller}
  gold:     {type: int, not_null: true, min: 0}
  channel:  {type: enum, not_null: true, values: [p2p, market]}
rules:
  - name: item_zero_means_no_qty
    row: "(item_id = 0) = (qty = 0)"
  - name: market_trade_has_listing
    violations: |
      SELECT * FROM trades WHERE channel = 'market'
        AND trade_id NOT IN (SELECT trade_id FROM market_listings WHERE trade_id IS NOT NULL)
volume: {daily_ratio_vs_median7: [0.5, 2.0]}
drift: {fields: [channel], psi_max: 0.1}
```

## 검사 종류

| 분류 | 검사 | 판정 |
|---|---|---|
| 스키마 | 테이블·컬럼 존재, 타입, 설계서에 없는 컬럼 | 자동 (없는 컬럼은 사람) |
| 필드 값 | not_null, enum, min/max, 형식(정규식), FK | 자동 |
| 중복 | unique, 복합 키, 전체 컬럼이 같은 행 | 자동 |
| 순서·기간 | 적재 기간 밖 시각, 행 조건 / 위반 SQL 룰 (세션 안 행동, 로그아웃 ≥ 로그인, 세션 겹침) | 자동 |
| 업무 규칙 | 누적 잔액(running balance), 거래-원장 개수 미러, 환불 ≥ 결제 순서, 결제-지급 짝 | 자동 / 룰마다 지정 |
| 볼륨 | 일별 행 수가 기간 중앙값의 범위 밖 (빈 날 포함) | 사람 |
| 분포 | 일별 범주 분포의 PSI | 사람 |

설계서에 모르는 키가 있으면 바로 에러 — 오타 하나로 검사가 조용히 빠지지 않게.

## 설계서 보정 기록 (개발 월드 정상 데이터에서만)

| 처음 설계서 | 정상 데이터에서 나온 것 | 고친 것 |
|---|---|---|
| 행동 중복 키 = (세션, 시각, 행동 종류) | 같은 ms 에 다른 행동 388쌍 (좌표·맵이 다름) | 모든 컬럼이 같아야 중복 적재 |
| 음수 잔액은 환불 행만 | 차지백 환불 뒤 음수 잔액이 이어짐 (11행) | 계정의 *처음* 음수 잔액이 환불이어야 함 |
| 사유 분포 PSI 0.1 | 기간 밖 기초잔액 날짜가 하루로 잡힘(엔진 버그) + 드문 사유로 PSI 최대 0.26 | 분포 검사를 기간 안으로 한정, PSI 0.3 |

## 변경 기록

- 2026-10-05 **볼륨 검사 버그 수정**: 이름은 '직전 7일 중앙값'인데 실제로는 *기간 전체* 중앙값과 비교하고 있었다. 출시 직후 유입이 몰렸다 줄어드는 로그([retrieve-liveops](https://github.com/heewonle/retrieve-liveops))에 붙였을 때 정상 날짜 8일이 걸려서 발견. 직전 7일 중앙값(직전 3일 이상 있을 때)과 비교하고, 행이 0인 날은 항상 걸리게 고침. 수정 후 두 월드 결함 평가를 다시 돌렸고 결과는 같다 (18/20, 오탐 0)

## LLM 이슈 요약 — 해보고 내린 결론

걸린 검사들을 로컬 LLM(`qwen3-vl:8b-instruct`, Ollama, 비용 0원)에 주고 **원인 분류**와 요약(무엇이/얼마나/언제부터/확인할 것/담당)을 쓰게 했다. 원인은 11개 분류 중 하나.

| 방법 | 개발 월드 (18종) | 평가 월드 (18종) |
|---|---:|---:|
| LLM v1 (기본 프롬프트) | 50% | - |
| LLM v2 (날짜 집중도 힌트 + 원인별 단서) | 56% | **50%** |
| 규칙 후보 + LLM 확인 | 56% | - |
| **규칙 기준선** (걸린 검사 종류의 우선순위) | 67% | **72%** |

**8B 로컬 모델은 원인 분류에서 단순 규칙보다 낮았다.** 그래서 `--summarize` 는 원인을 규칙으로 정하고, LLM은 사람이 읽을 요약·확인할 것만 쓰며 자기 원인 의견은 참고로만 붙인다. 요약의 숫자·날짜가 입력과 정확히 일치하는 비율도 44%(만 단위 반올림도 불일치로 셈)라, 요약은 **실험적 기능**으로 둔다. 타임존 밀림(F07)은 규칙(적재 누락)과 LLM(서버 버그) 모두 틀렸다 — 세션과 행동 시각의 차이(9시간)를 직접 계산하는 검사가 있어야 한다.

## 실행

```bash
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
# 데이터: GameGuard 시뮬레이터로 14일 월드 생성
python -m sim.generate --config config/sim_small.yaml --out ../logspec/data/dev            # (gameguard 폴더에서)
python -m sim.generate --config config/sim_small.yaml --seed 99 --out ../logspec/data/eval

python -m logspec.runner --data data/dev --period 2026-09-01:2026-09-15 --out out/dev     # 검증 + 리포트
python -m logspec.runner --data data/faults_eval/F07 --period 2026-09-01:2026-09-15 --out out/f07 --summarize
python -m logspec.infer --data data/dev --out specs/inferred                                # 설계서 초안
python -m inject.faults --src data/eval --out data/faults_eval                             # 결함 20종
python -m eval.run_eval --world eval                                                       # 검출 평가
python -m eval.eval_llm --world eval                                                       # 원인 추정 평가
python -m pytest                                                                           # 검사별 결함 테스트 19개
```

## 구조
```
specs/gameguard/   사람이 쓴 설계서 9개 테이블      specs/inferred/  자동 추론 초안
logspec/  spec.py(읽기·형식 검사) checks.py(검사 SQL 생성) runner.py(실행) report.py infer.py llm.py
inject/faults.py   결함 20종                       eval/  run_eval.py eval_llm.py
tests/             검사마다 작은 결함을 넣어 그 검사가 걸리는지
```
