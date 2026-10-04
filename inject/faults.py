"""결함 주입: 정상 월드를 복사해 실제로 흔한 로그 결함 20종을 하나씩 넣는다.

결함 목록은 설계서가 무엇을 잡는지와 상관없이 '현장에서 흔한 로그 문제'로 골랐다.
그중 3종(F18~F20)은 설계서가 직접 겨냥하지 않는 사각지대다 — 도구의 한계를 재기 위해 넣었다.

결함마다
  expected  잡혀야 하는 검사 id (위치까지 맞혔는지 채점용)
  cause     원인 분류 (LLM 원인 추정 채점용), alt_causes 는 그렇게 볼 수도 있는 다른 분류

  python -m inject.faults --src data/eval --out data/faults_eval
"""
import argparse
import json
import os
import shutil

import numpy as np
import pandas as pd

DAY = pd.Timestamp("2026-09-08")      # 하루 단위 결함을 넣는 날
NEXT = DAY + pd.Timedelta(days=1)

CAUSES = ["스키마 변경", "수집·클라이언트 버그", "사양에 없는 신규 값", "타임존", "중복 적재",
          "적재 누락", "서버 로직 버그", "참조 데이터 불일치", "단위 변경", "클라이언트 시계", "수집 설정 변경"]


def on_day(s: pd.Series):
    return (s >= DAY) & (s < NEXT)


FAULTS = []


def fault(fid, name, table, expected, cause, alt=()):
    def deco(fn):
        FAULTS.append(dict(id=fid, name=name, table=table, expected=list(expected), cause=cause,
                           alt_causes=list(alt), fn=fn))
        return fn
    return deco


@fault("F01", "trades.gold 타입이 문자열로 바뀜", "trades", ["trades.gold:type"], "스키마 변경")
def f01(d, rng):
    d["trades"]["gold"] = d["trades"]["gold"].astype(str)


@fault("F02", "sessions.ip_hash 컬럼 누락", "sessions", ["sessions.ip_hash:exists"], "스키마 변경")
def f02(d, rng):
    d["sessions"] = d["sessions"].drop(columns="ip_hash")


@fault("F03", "payments.amount_krw 컬럼명이 amount 로 바뀜", "payments", ["payments.amount_krw:exists"], "스키마 변경")
def f03(d, rng):
    d["payments"] = d["payments"].rename(columns={"amount_krw": "amount"})


@fault("F04", "특정일 actions.map_id 30% 누락", "actions", ["actions.map_id:not_null"], "수집·클라이언트 버그")
def f04(d, rng):
    a = d["actions"]
    m = on_day(a["ts"]) & (rng.random(len(a)) < 0.3)
    a["map_id"] = a["map_id"].astype("Int16").mask(m)


@fault("F05", "trades.channel 에 신규 값 'auction' 5%", "trades", ["trades.channel:enum"], "사양에 없는 신규 값",
       alt=["스키마 변경"])
def f05(d, rng):
    t = d["trades"]
    t.loc[rng.random(len(t)) < 0.05, "channel"] = "auction"


@fault("F06", "특정일 action_type 대문자로 적재", "actions", ["actions.action_type:enum"], "수집·클라이언트 버그",
       alt=["스키마 변경", "사양에 없는 신규 값"])
def f06(d, rng):
    a = d["actions"]
    m = on_day(a["ts"])
    a.loc[m, "action_type"] = a.loc[m, "action_type"].str.upper()


@fault("F07", "특정일 세션 시각이 9시간 밀림 (UTC↔KST)", "sessions", ["actions:rule:action_within_session"], "타임존",
       alt=["클라이언트 시계"])
def f07(d, rng):
    s = d["sessions"]
    m = on_day(s["login_at"])
    s.loc[m, "login_at"] += pd.Timedelta(hours=9)
    s.loc[m, "logout_at"] += pd.Timedelta(hours=9)


@fault("F08", "특정일 trades 를 두 번 적재", "trades", ["trades.trade_id:unique"], "중복 적재")
def f08(d, rng):
    t = d["trades"]
    d["trades"] = pd.concat([t, t[on_day(t["ts"])]], ignore_index=True)


@fault("F09", "특정일 actions 전체 누락", "actions", ["actions:volume"], "적재 누락")
def f09(d, rng):
    a = d["actions"]
    d["actions"] = a[~on_day(a["ts"])]


@fault("F10", "특정일 currency_log 절반만 적재", "currency_log", ["currency_log:rule:balance_chain"], "적재 누락")
def f10(d, rng):
    c = d["currency_log"]
    d["currency_log"] = c[~(on_day(c["ts"]) & (rng.random(len(c)) < 0.5))]


@fault("F11", "잔액 계산 오류 (0.5% 행 +1,000)", "currency_log", ["currency_log:rule:balance_chain"], "서버 로직 버그")
def f11(d, rng):
    c = d["currency_log"]
    m = rng.random(len(c)) < 0.005
    c.loc[m, "balance_after"] += 1000


@fault("F12", "trades.buyer 1% 가 없는 계정", "trades", ["trades.buyer:fk"], "참조 데이터 불일치")
def f12(d, rng):
    t = d["trades"]
    m = rng.random(len(t)) < 0.01
    t.loc[m, "buyer"] = rng.integers(900_000, 999_999, m.sum())


@fault("F13", "trades.gold 부호 반전 (0.5%)", "trades", ["trades.gold:min"], "서버 로직 버그",
       alt=["수집·클라이언트 버그"])
def f13(d, rng):
    t = d["trades"]
    m = rng.random(len(t)) < 0.005
    t.loc[m, "gold"] = -t.loc[m, "gold"]


@fault("F14", "특정일부터 결제 금액이 원 → 전 단위(×100)", "payments", ["payments.amount_krw:max"], "단위 변경")
def f14(d, rng):
    p = d["payments"]
    m = p["ts"] >= DAY
    p.loc[m, "amount_krw"] *= 100


@fault("F15", "자기 자신과의 거래 (0.5%)", "trades", ["trades.buyer:not_equal"], "서버 로직 버그")
def f15(d, rng):
    t = d["trades"]
    m = rng.random(len(t)) < 0.005
    t.loc[m, "buyer"] = t.loc[m, "seller"]


@fault("F16", "일부 행동 시각이 미래(+4년)", "actions", ["actions.ts:period"], "클라이언트 시계")
def f16(d, rng):
    a = d["actions"]
    m = rng.random(len(a)) < 0.0002
    a.loc[m, "ts"] = a.loc[m, "ts"] + pd.DateOffset(years=4)


@fault("F17", "특정일 행동 로그가 kill 만 수집됨 (필터 설정 오류)", "actions", ["actions.action_type:drift"],
       "수집 설정 변경", alt=["수집·클라이언트 버그"])
def f17(d, rng):
    a = d["actions"]
    d["actions"] = a[~on_day(a["ts"]) | (a["action_type"] == "kill")]


# ── 설계서 사각지대 ──
@fault("F18", "재처리로 특정일 trades 가 새 trade_id 로 다시 적재 (골드 기록은 그대로)", "trades",
       ["currency_log:rule:trade_mirror"], "중복 적재")
def f18(d, rng):
    t = d["trades"]
    dup = t[on_day(t["ts"]) & (t["channel"] == "p2p")].copy()
    dup["trade_id"] = dup["trade_id"] + 50_000_000
    d["trades"] = pd.concat([t, dup], ignore_index=True)


@fault("F19", "특정일 trades.gold 가 절반으로 기록 (허용 범위 안의 단위 오류)", "trades", [], "단위 변경",
       alt=["서버 로직 버그"])
def f19(d, rng):
    t = d["trades"]
    m = on_day(t["ts"])
    t.loc[m, "gold"] = (t.loc[m, "gold"] // 2)


@fault("F20", "특정일 마지막 3시간 actions 늦게 도착해 누락 (약 12%)", "actions", [], "적재 누락")
def f20(d, rng):
    a = d["actions"]
    d["actions"] = a[~((a["ts"] >= DAY + pd.Timedelta(hours=21)) & (a["ts"] < NEXT))]


def apply(src: str, out_root: str, seed: int = 0) -> list[dict]:
    tables = {os.path.splitext(f)[0]: os.path.join(src, f) for f in os.listdir(src) if f.endswith(".parquet")}
    manifest = []
    for k, F in enumerate(FAULTS):
        rng = np.random.default_rng(seed + k)
        out = os.path.join(out_root, F["id"])
        os.makedirs(out, exist_ok=True)
        need = {F["table"]}
        d = {t: pd.read_parquet(tables[t]) for t in need}
        for df in d.values():   # Parquet 사전 인코딩 컬럼이 범주형으로 읽히면 새 값을 넣을 수 없다
            for c in df.select_dtypes("category").columns:
                df[c] = df[c].astype(str)
        F["fn"](d, rng)
        for t, p in tables.items():
            dst = os.path.join(out, f"{t}.parquet")
            if t in d:
                d[t].to_parquet(dst, index=False)
            else:
                shutil.copyfile(p, dst)
        manifest.append({k2: v for k2, v in F.items() if k2 != "fn"})
        print(F["id"], F["name"])
    json.dump(manifest, open(os.path.join(out_root, "manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/dev")
    ap.add_argument("--out", default="data/faults_dev")
    a = ap.parse_args()
    apply(a.src, a.out)
