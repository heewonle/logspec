# LLM 원인 추정 평가 (LLM 단독) — eval 월드 (2026-10-05)

- 모델 `qwen3-vl:8b-instruct` (로컬 Ollama, 비용 0원) · 검출된 결함 18종 · 건당 중앙값 3.1초
- **LLM 원인 일치: 엄격 50% (9/18) · 관대 56%**
- 기준선(검사 종류 우선순위): 엄격 72% · 관대 78%
- 요약의 숫자·날짜가 입력에 있는 비율(지어내지 않음): 44%

| id   | 결함                                                | 정답 원인       | LLM         | 기준선         | LLM 엄격   | LLM 관대   | 기준선 엄격   | 기준선 관대   | 요약 근거   |   초 |
|:-----|:--------------------------------------------------|:------------|:------------|:------------|:---------|:---------|:---------|:---------|:--------|----:|
| F01  | trades.gold 타입이 문자열로 바뀜                           | 스키마 변경      | 스키마 변경      | 스키마 변경      | True     | True     | True     | True     | False   | 2.4 |
| F02  | sessions.ip_hash 컬럼 누락                            | 스키마 변경      | 스키마 변경      | 스키마 변경      | True     | True     | True     | True     | False   | 2.4 |
| F03  | payments.amount_krw 컬럼명이 amount 로 바뀜              | 스키마 변경      | 스키마 변경      | 스키마 변경      | True     | True     | True     | True     | False   | 3   |
| F04  | 특정일 actions.map_id 30% 누락                         | 수집·클라이언트 버그 | 사양에 없는 신규 값 | 수집·클라이언트 버그 | False    | False    | True     | True     | False   | 2.8 |
| F05  | trades.channel 에 신규 값 'auction' 5%                | 사양에 없는 신규 값 | 사양에 없는 신규 값 | 사양에 없는 신규 값 | True     | True     | True     | True     | True    | 2.9 |
| F06  | 특정일 action_type 대문자로 적재                           | 수집·클라이언트 버그 | 사양에 없는 신규 값 | 사양에 없는 신규 값 | False    | True     | False    | True     | True    | 3.5 |
| F07  | 특정일 세션 시각이 9시간 밀림 (UTC↔KST)                       | 타임존         | 서버 로직 버그    | 적재 누락       | False    | False    | False    | False    | True    | 3.5 |
| F08  | 특정일 trades 를 두 번 적재                               | 중복 적재       | 서버 로직 버그    | 중복 적재       | False    | False    | True     | True     | True    | 3.6 |
| F09  | 특정일 actions 전체 누락                                 | 적재 누락       | 적재 누락       | 적재 누락       | True     | True     | True     | True     | True    | 3.5 |
| F10  | 특정일 currency_log 절반만 적재                           | 적재 누락       | 서버 로직 버그    | 서버 로직 버그    | False    | False    | False    | False    | True    | 3.3 |
| F11  | 잔액 계산 오류 (0.5% 행 +1,000)                          | 서버 로직 버그    | 서버 로직 버그    | 서버 로직 버그    | True     | True     | True     | True     | False   | 3.1 |
| F12  | trades.buyer 1% 가 없는 계정                           | 참조 데이터 불일치  | 참조 데이터 불일치  | 참조 데이터 불일치  | True     | True     | True     | True     | False   | 3.1 |
| F13  | trades.gold 부호 반전 (0.5%)                          | 서버 로직 버그    | 서버 로직 버그    | 단위 변경       | True     | True     | False    | False    | False   | 3.5 |
| F14  | 특정일부터 결제 금액이 원 → 전 단위(×100)                       | 단위 변경       | 서버 로직 버그    | 단위 변경       | False    | False    | True     | True     | False   | 3.6 |
| F15  | 자기 자신과의 거래 (0.5%)                                 | 서버 로직 버그    | 서버 로직 버그    | 서버 로직 버그    | True     | True     | True     | True     | True    | 2.7 |
| F16  | 일부 행동 시각이 미래(+4년)                                 | 클라이언트 시계    | 타임존         | 클라이언트 시계    | False    | False    | True     | True     | True    | 3.6 |
| F17  | 특정일 행동 로그가 kill 만 수집됨 (필터 설정 오류)                  | 수집 설정 변경    | 사양에 없는 신규 값 | 적재 누락       | False    | False    | False    | False    | False   | 2.7 |
| F18  | 재처리로 특정일 trades 가 새 trade_id 로 다시 적재 (골드 기록은 그대로) | 중복 적재       | 서버 로직 버그    | 중복 적재       | False    | False    | True     | True     | False   | 2.8 |

## 요약 예시

**F01** — trades.gold:type 컬럼 타입이 int에서 VARCHAR로 변경됨 / 1행 / 2025-04-01
- 원인: 스키마 변경 — 설계서 int 타입이 실제 VARCHAR로 변경되어 타입 비교 오류 발생
- 확인할 것: 설계서와 실제 스키마 차이점 점검 · 배포 이력에서 해당 컬럼 변경 사유 확인 · 수집 쿼리에서 CAST 적용 여부 확인 (담당 데이터 엔지니어링)

**F02** — sessions 테이블에 ip_hash 컬럼이 없음 / 1 행 (100%) / 하루치 데이터
- 원인: 스키마 변경 — 설계서에 있는 컬럼이 로그에 없어 검사가 실패함
- 확인할 것: 설계서와 실제 스키마 차이점 점검 · 배포 로그 스키마 변경 이력 확인 · 수집 쿼리에서 ip_hash 컬럼 포함 여부 확인 (담당 데이터 엔지니어링)

**F03** — payments 테이블에 amount_krw 컬럼이 없어 설계서와 스키마 불일치 / 100% (1.0) / 하루치 데이터
- 원인: 스키마 변경 — 설계서에 정의된 amount_krw 컬럼이 실제 데이터에 없어, 모든 관련 검사가 실행 불가 상태로 실패함
- 확인할 것: 설계서와 배포 스키마 차이점 확인 · 수집 쿼리/ETL 로직에서 amount_krw 컬럼이 제거된 이유 파악 · DB 스키마 변경 이력 및 배포 로그 검토 (담당 데이터 엔지니어링)
