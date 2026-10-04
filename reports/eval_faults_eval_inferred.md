# 결함 주입 평가 — eval 월드 · 설계서 `specs\inferred` (2026-10-05)

- 검사 182개 × (정상 1 + 결함 20) 실행, 7초
- **정상 데이터 오탐: 1건** (market_listings.price:max)
- **검출: 13/20**
- 위치까지 맞힘: 11/18 (기대 검사가 정해진 결함만)

| id   | 결함                                                | 검출    | 위치 맞힘   | 걸린 검사                                                                                                                     | 자동/사람   |
|:-----|:--------------------------------------------------|:------|:--------|:--------------------------------------------------------------------------------------------------------------------------|:--------|
| F01  | trades.gold 타입이 문자열로 바뀜                           | True  | True    | `trades.gold:type`, `trades.gold:min`, `trades.gold:max`                                                                  | 자동      |
| F02  | sessions.ip_hash 컬럼 누락                            | True  | True    | `sessions.ip_hash:exists`, `sessions.ip_hash:not_null`                                                                    | 자동      |
| F03  | payments.amount_krw 컬럼명이 amount 로 바뀜              | True  | True    | `payments.amount_krw:exists`, `payments.amount:unexpected`, `payments.amount_krw:not_null`, `payments.amount_krw:min` 외 1 | 사람/자동   |
| F04  | 특정일 actions.map_id 30% 누락                         | True  | True    | `actions.map_id:not_null`                                                                                                 | 자동      |
| F05  | trades.channel 에 신규 값 'auction' 5%                | True  | True    | `trades.channel:enum`                                                                                                     | 자동      |
| F06  | 특정일 action_type 대문자로 적재                           | True  | True    | `actions.action_type:enum`, `actions.action_type:drift`                                                                   | 사람/자동   |
| F07  | 특정일 세션 시각이 9시간 밀림 (UTC↔KST)                       | True  | False   | `sessions:volume`                                                                                                         | 사람      |
| F08  | 특정일 trades 를 두 번 적재                               | True  | True    | `trades.trade_id:unique`, `trades:volume`                                                                                 | 사람/자동   |
| F09  | 특정일 actions 전체 누락                                 | True  | True    | `actions:volume`                                                                                                          | 사람      |
| F10  | 특정일 currency_log 절반만 적재                           | False | False   |                                                                                                                           | -       |
| F11  | 잔액 계산 오류 (0.5% 행 +1,000)                          | False | False   |                                                                                                                           | -       |
| F12  | trades.buyer 1% 가 없는 계정                           | True  | False   | `trades.buyer:max`                                                                                                        | 자동      |
| F13  | trades.gold 부호 반전 (0.5%)                          | True  | True    | `trades.gold:min`                                                                                                         | 자동      |
| F14  | 특정일부터 결제 금액이 원 → 전 단위(×100)                       | True  | True    | `payments.amount_krw:max`                                                                                                 | 자동      |
| F15  | 자기 자신과의 거래 (0.5%)                                 | False | False   |                                                                                                                           | -       |
| F16  | 일부 행동 시각이 미래(+4년)                                 | False | False   |                                                                                                                           | -       |
| F17  | 특정일 행동 로그가 kill 만 수집됨 (필터 설정 오류)                  | True  | True    | `actions.action_type:drift`                                                                                               | 사람      |
| F18  | 재처리로 특정일 trades 가 새 trade_id 로 다시 적재 (골드 기록은 그대로) | False | False   |                                                                                                                           | -       |
| F19  | 특정일 trades.gold 가 절반으로 기록 (허용 범위 안의 단위 오류)        | False |         |                                                                                                                           | -       |
| F20  | 특정일 마지막 3시간 actions 늦게 도착해 누락 (약 12%)             | False |         |                                                                                                                           | -       |
