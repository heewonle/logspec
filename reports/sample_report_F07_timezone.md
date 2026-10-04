# 로그 검증 리포트 (2026-10-05 02:43)

- 데이터 `data/faults_eval/F07` · 기간 `2026-09-01:2026-09-15` · 검사 176개 · 5.4초
- 위반 **3** · 실행 불가 0 · 자동 판정 이슈 2 · 사람 확인 필요 1

## 분류별

| 분류    |   fail |   pass |
|:------|-------:|-------:|
| 볼륨    |      1 |      3 |
| 분포    |      0 |      3 |
| 순서·기간 |      2 |      6 |
| 스키마   |      0 |     51 |
| 업무 규칙 |      0 |     12 |
| 중복    |      0 |      9 |
| 필드 값  |      0 |     89 |

## 요약 (LLM)

**추정 원인 (규칙): 적재 누락**

- 무엇이: 세션 데이터의 시간 범위와 계정 일치성 검사 실패
- 얼마나: 2026-09-08에 79,182건, 2026-09-09에 113건
- 언제부터: 2026-09-08~09
- 확인할 것: 세션 로그에서 login_at~logout_at 범위 외의 행동을 추적해보기 · 계정 ID와 세션 ID 매핑 테이블에서 일치 여부 확인 · 서버 로직에서 세션 유효성 검증 로직을 재검토
- 담당: 서버

> LLM 의견: 서버 로직 버그 — 세션 기간 내 행동이 아닌 행동이 발생하거나, 세션과 계정이 일치하지 않아 검사 실패. 특히 2026-09-08에 집중된 7만 건은 서버가 세션 유효성 검증을 제대로 하지 않아 발생. (원인 분류는 평가에서 규칙 기준선이 더 정확해 규칙을 따른다)

## 자동 판정 이슈

설계서와 다르면 곧 문제인 항목 (타입·null·허용값·범위·참조·순서·중복).

#### `actions:rule:action_within_session` — 행동은 자기 세션의 접속 구간 안에서 일어나고, 세션 주인과 계정이 같다
- 무엇이: 순서·기간 / rule_sql · 상태 **위반**
- 얼마나: 79,182행 (5.39%)
- 언제: 2026-09-08 ~ 2026-09-09 (2일)
- 예시: `{"ts": "2026-09-08T00:02:51.285", "account_id": 102035, "session_id": 5011004, "action_type": "kill", "map_id": 1, "skill_id": 12, "x": 288.8685302734, "y": 340.7061157227}`

#### `sessions:rule:no_overlap_per_account` — 같은 계정의 세션은 겹치지 않는다
- 무엇이: 순서·기간 / rule_sql · 상태 **위반**
- 얼마나: 113행 (0.61%)
- 언제: 2026-09-09
- 예시: `{"session_id": 5017640, "account_id": 100097, "login_at": "2026-09-09T05:48:40.000", "logout_at": "2026-09-09T06:29:18.000", "ip_hash": "6b54b9c08b", "device_id": "D854900883", "prev_logout": "2026-09-09T06:36:34.000"}`

## 사람 확인 필요

점검·이벤트·패치일 수도 있어 해석이 필요한 항목 (볼륨·분포·설계서에 없는 컬럼).

#### `sessions:volume` — 일별 행 수가 기간 중앙값의 0.6~1.7배 안 (빈 날 포함)
- 무엇이: 볼륨 / volume · 상태 **위반**
- 얼마나: 1행 (0.01%)
- 언제: 2026-09-08
- 예시: `{"login_at": "2026-09-08T00:00:00.000", "rows_on_day": 575, "median_rows": 1297.0, "ratio": 0.444}`

## 검증 체크리스트

| 검사 | 분류 | 판정 | 상태 | 위반 |
|---|---|---|---|---:|
| `accounts.account_id:type` | 스키마 | 자동 | 통과 | 0 |
| `accounts.created_at:type` | 스키마 | 자동 | 통과 | 0 |
| `accounts.country:type` | 스키마 | 자동 | 통과 | 0 |
| `accounts.device_id:type` | 스키마 | 자동 | 통과 | 0 |
| `accounts.ip_hash:type` | 스키마 | 자동 | 통과 | 0 |
| `accounts.guild_id:type` | 스키마 | 자동 | 통과 | 0 |
| `accounts.level:type` | 스키마 | 자동 | 통과 | 0 |
| `accounts.account_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `accounts.account_id:unique` | 중복 | 자동 | 통과 | 0 |
| `accounts.created_at:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `accounts.country:enum` | 필드 값 | 자동 | 통과 | 0 |
| `accounts.device_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `accounts.device_id:pattern` | 필드 값 | 자동 | 통과 | 0 |
| `accounts.ip_hash:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `accounts.ip_hash:pattern` | 필드 값 | 자동 | 통과 | 0 |
| `accounts.guild_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `accounts.guild_id:min` | 필드 값 | 자동 | 통과 | 0 |
| `accounts.level:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `accounts.level:min` | 필드 값 | 자동 | 통과 | 0 |
| `accounts.level:max` | 필드 값 | 자동 | 통과 | 0 |
| `actions.ts:type` | 스키마 | 자동 | 통과 | 0 |
| `actions.account_id:type` | 스키마 | 자동 | 통과 | 0 |
| `actions.session_id:type` | 스키마 | 자동 | 통과 | 0 |
| `actions.action_type:type` | 스키마 | 자동 | 통과 | 0 |
| `actions.map_id:type` | 스키마 | 자동 | 통과 | 0 |
| `actions.skill_id:type` | 스키마 | 자동 | 통과 | 0 |
| `actions.x:type` | 스키마 | 자동 | 통과 | 0 |
| `actions.y:type` | 스키마 | 자동 | 통과 | 0 |
| `actions.ts:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `actions.ts:period` | 순서·기간 | 자동 | 통과 | 0 |
| `actions.account_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `actions.account_id:fk` | 필드 값 | 자동 | 통과 | 0 |
| `actions.session_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `actions.session_id:fk` | 필드 값 | 자동 | 통과 | 0 |
| `actions.action_type:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `actions.action_type:enum` | 필드 값 | 자동 | 통과 | 0 |
| `actions.map_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `actions.map_id:fk` | 필드 값 | 자동 | 통과 | 0 |
| `actions.skill_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `actions.skill_id:min` | 필드 값 | 자동 | 통과 | 0 |
| `actions.skill_id:max` | 필드 값 | 자동 | 통과 | 0 |
| `actions.x:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `actions.x:min` | 필드 값 | 자동 | 통과 | 0 |
| `actions.x:max` | 필드 값 | 자동 | 통과 | 0 |
| `actions.y:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `actions.y:min` | 필드 값 | 자동 | 통과 | 0 |
| `actions.y:max` | 필드 값 | 자동 | 통과 | 0 |
| `actions:duplicate_rows` | 중복 | 자동 | 통과 | 0 |
| `actions:rule:action_within_session` | 순서·기간 | 자동 | 위반 | 79,182 |
| `actions:rule:skill_only_on_combat` | 업무 규칙 | 자동 | 통과 | 0 |
| `actions:volume` | 볼륨 | 사람 | 통과 | 0 |
| `actions.action_type:drift` | 분포 | 사람 | 통과 | 0 |
| `currency_log.log_id:type` | 스키마 | 자동 | 통과 | 0 |
| `currency_log.ts:type` | 스키마 | 자동 | 통과 | 0 |
| `currency_log.account_id:type` | 스키마 | 자동 | 통과 | 0 |
| `currency_log.delta:type` | 스키마 | 자동 | 통과 | 0 |
| `currency_log.balance_after:type` | 스키마 | 자동 | 통과 | 0 |
| `currency_log.reason:type` | 스키마 | 자동 | 통과 | 0 |
| `currency_log.log_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `currency_log.log_id:unique` | 중복 | 자동 | 통과 | 0 |
| `currency_log.ts:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `currency_log.account_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `currency_log.account_id:fk` | 필드 값 | 자동 | 통과 | 0 |
| `currency_log.delta:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `currency_log.balance_after:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `currency_log.reason:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `currency_log.reason:enum` | 필드 값 | 자동 | 통과 | 0 |
| `currency_log:rule:balance_chain` | 업무 규칙 | 자동 | 통과 | 0 |
| `currency_log:rule:sign_by_reason` | 업무 규칙 | 자동 | 통과 | 0 |
| `currency_log:rule:trade_mirror` | 업무 규칙 | 자동 | 통과 | 0 |
| `currency_log:rule:negative_balance_starts_with_refund` | 업무 규칙 | 사람 | 통과 | 0 |
| `currency_log:volume` | 볼륨 | 사람 | 통과 | 0 |
| `currency_log.reason:drift` | 분포 | 사람 | 통과 | 0 |
| `market_listings.ts:type` | 스키마 | 자동 | 통과 | 0 |
| `market_listings.listing_id:type` | 스키마 | 자동 | 통과 | 0 |
| `market_listings.seller:type` | 스키마 | 자동 | 통과 | 0 |
| `market_listings.item_id:type` | 스키마 | 자동 | 통과 | 0 |
| `market_listings.price:type` | 스키마 | 자동 | 통과 | 0 |
| `market_listings.status:type` | 스키마 | 자동 | 통과 | 0 |
| `market_listings.trade_id:type` | 스키마 | 자동 | 통과 | 0 |
| `market_listings.ts:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `market_listings.listing_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `market_listings.listing_id:unique` | 중복 | 자동 | 통과 | 0 |
| `market_listings.seller:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `market_listings.seller:fk` | 필드 값 | 자동 | 통과 | 0 |
| `market_listings.item_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `market_listings.item_id:fk` | 필드 값 | 자동 | 통과 | 0 |
| `market_listings.price:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `market_listings.price:min` | 필드 값 | 자동 | 통과 | 0 |
| `market_listings.status:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `market_listings.status:enum` | 필드 값 | 자동 | 통과 | 0 |
| `market_listings:rule:sold_has_trade` | 업무 규칙 | 자동 | 통과 | 0 |
| `payments.ts:type` | 스키마 | 자동 | 통과 | 0 |
| `payments.payment_id:type` | 스키마 | 자동 | 통과 | 0 |
| `payments.account_id:type` | 스키마 | 자동 | 통과 | 0 |
| `payments.amount_krw:type` | 스키마 | 자동 | 통과 | 0 |
| `payments.event:type` | 스키마 | 자동 | 통과 | 0 |
| `payments.ts:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `payments.ts:period` | 순서·기간 | 자동 | 통과 | 0 |
| `payments.payment_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `payments.account_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `payments.account_id:fk` | 필드 값 | 자동 | 통과 | 0 |
| `payments.amount_krw:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `payments.amount_krw:min` | 필드 값 | 자동 | 통과 | 0 |
| `payments.amount_krw:max` | 필드 값 | 자동 | 통과 | 0 |
| `payments.event:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `payments.event:enum` | 필드 값 | 자동 | 통과 | 0 |
| `payments:key` | 중복 | 자동 | 통과 | 0 |
| `payments:rule:refund_after_paid` | 순서·기간 | 자동 | 통과 | 0 |
| `payments:rule:purchase_credited` | 업무 규칙 | 자동 | 통과 | 0 |
| `items.item_id:type` | 스키마 | 자동 | 통과 | 0 |
| `items.grade:type` | 스키마 | 자동 | 통과 | 0 |
| `items.item_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `items.item_id:unique` | 중복 | 자동 | 통과 | 0 |
| `items.item_id:min` | 필드 값 | 자동 | 통과 | 0 |
| `items.grade:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `items.grade:min` | 필드 값 | 자동 | 통과 | 0 |
| `items.grade:max` | 필드 값 | 자동 | 통과 | 0 |
| `maps.map_id:type` | 스키마 | 자동 | 통과 | 0 |
| `maps.min_level:type` | 스키마 | 자동 | 통과 | 0 |
| `maps.map_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `maps.map_id:unique` | 중복 | 자동 | 통과 | 0 |
| `maps.map_id:min` | 필드 값 | 자동 | 통과 | 0 |
| `maps.min_level:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `maps.min_level:min` | 필드 값 | 자동 | 통과 | 0 |
| `sessions.session_id:type` | 스키마 | 자동 | 통과 | 0 |
| `sessions.account_id:type` | 스키마 | 자동 | 통과 | 0 |
| `sessions.login_at:type` | 스키마 | 자동 | 통과 | 0 |
| `sessions.logout_at:type` | 스키마 | 자동 | 통과 | 0 |
| `sessions.ip_hash:type` | 스키마 | 자동 | 통과 | 0 |
| `sessions.device_id:type` | 스키마 | 자동 | 통과 | 0 |
| `sessions.session_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `sessions.session_id:unique` | 중복 | 자동 | 통과 | 0 |
| `sessions.account_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `sessions.account_id:fk` | 필드 값 | 자동 | 통과 | 0 |
| `sessions.login_at:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `sessions.login_at:period` | 순서·기간 | 자동 | 통과 | 0 |
| `sessions.logout_at:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `sessions.ip_hash:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `sessions.ip_hash:pattern` | 필드 값 | 자동 | 통과 | 0 |
| `sessions.device_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `sessions.device_id:pattern` | 필드 값 | 자동 | 통과 | 0 |
| `sessions:rule:logout_after_login` | 순서·기간 | 자동 | 통과 | 0 |
| `sessions:rule:session_max_24h` | 업무 규칙 | 자동 | 통과 | 0 |
| `sessions:rule:no_overlap_per_account` | 순서·기간 | 자동 | 위반 | 113 |
| `sessions:volume` | 볼륨 | 사람 | 위반 | 1 |
| `trades.ts:type` | 스키마 | 자동 | 통과 | 0 |
| `trades.trade_id:type` | 스키마 | 자동 | 통과 | 0 |
| `trades.seller:type` | 스키마 | 자동 | 통과 | 0 |
| `trades.buyer:type` | 스키마 | 자동 | 통과 | 0 |
| `trades.item_id:type` | 스키마 | 자동 | 통과 | 0 |
| `trades.qty:type` | 스키마 | 자동 | 통과 | 0 |
| `trades.gold:type` | 스키마 | 자동 | 통과 | 0 |
| `trades.channel:type` | 스키마 | 자동 | 통과 | 0 |
| `trades.ts:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `trades.ts:period` | 순서·기간 | 자동 | 통과 | 0 |
| `trades.trade_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `trades.trade_id:unique` | 중복 | 자동 | 통과 | 0 |
| `trades.seller:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `trades.seller:fk` | 필드 값 | 자동 | 통과 | 0 |
| `trades.buyer:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `trades.buyer:fk` | 필드 값 | 자동 | 통과 | 0 |
| `trades.buyer:not_equal` | 업무 규칙 | 자동 | 통과 | 0 |
| `trades.item_id:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `trades.item_id:min` | 필드 값 | 자동 | 통과 | 0 |
| `trades.qty:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `trades.qty:min` | 필드 값 | 자동 | 통과 | 0 |
| `trades.gold:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `trades.gold:min` | 필드 값 | 자동 | 통과 | 0 |
| `trades.channel:not_null` | 필드 값 | 자동 | 통과 | 0 |
| `trades.channel:enum` | 필드 값 | 자동 | 통과 | 0 |
| `trades:rule:item_zero_means_no_qty` | 업무 규칙 | 자동 | 통과 | 0 |
| `trades:rule:item_exists` | 업무 규칙 | 자동 | 통과 | 0 |
| `trades:rule:market_trade_has_listing` | 업무 규칙 | 자동 | 통과 | 0 |
| `trades:volume` | 볼륨 | 사람 | 통과 | 0 |
| `trades.channel:drift` | 분포 | 사람 | 통과 | 0 |
