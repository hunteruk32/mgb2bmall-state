"""장중 실시간 감시 + 모의매매(페이퍼 트레이딩) 기록.

- interval 분마다 관심종목 시세를 새로 받아 점수를 다시 계산
- 보유 중 모의 포지션: 현재가가 손절가에 닿으면 즉시 청산
  분할 익절(C): 1차 익절가 도달 시 절반 매도 + 손절가를 본전으로 상향,
                2차 익절가 또는 본전 이탈 시 나머지 매도
- 신규 진입: 백테스트와 같은 조건(장 마감 점수)으로 맞추기 위해
  15:15 이후에만 '매수' 기록 (그 전에는 '매수 후보' 알림만)
  시장 필터(B): 코스피 약세 조건이면 신규 진입 금지
- 점수 하락/보유기간 만료 청산은 다음날 장 시작 후 첫 확인 때 현재가로 기록
- 모든 거래는 paper_trades.csv 에 저장 -> `python main.py paper` 로 승률 집계
"""
from __future__ import annotations

import os
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import data
import indicators
import market
from backtest import Params, latest, stop_distance, summarize
from signals import score_at

KST = ZoneInfo("Asia/Seoul")
LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paper_trades.csv")
COLS = ["code", "name", "entry_date", "entry", "stop", "target", "target2", "half_ret",
        "score", "status", "exit_date", "exit", "ret", "reason"]
OPEN_T, ENTRY_T, CLOSE_T = dtime(9, 0), dtime(15, 15), dtime(15, 30)


def now() -> datetime:
    return datetime.now(KST)


def market_open(t: datetime) -> bool:
    return t.weekday() < 5 and OPEN_T <= t.time() <= CLOSE_T


def read_ledger(path: str = LEDGER) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(path, dtype={"code": str}, encoding="utf-8-sig")
    for c in COLS:
        if c not in df:
            df[c] = np.nan
    return df


def write_ledger(df: pd.DataFrame, path: str = LEDGER):
    df[COLS].to_csv(path, index=False, encoding="utf-8-sig")


def _held_days(entry_date: str, today: datetime) -> int:
    return int(np.busday_count(pd.Timestamp(entry_date).date(), today.date())) + 1


def step(codes: list[str], p: Params, loader, t: datetime, ledger: pd.DataFrame,
         log=print, mkt: tuple[bool, str] = (True, "")) -> pd.DataFrame:
    """한 번의 점검. loader(code) -> (지표 계산 전 DataFrame, 종목명).
    mkt: (신규 매수 가능 여부, 사유) — 시장 필터 결과."""
    mkt_ok = mkt[0] or not p.market_filter
    if not mkt_ok:
        log(f"  ⛔ 시장 필터: 신규 매수 중단 ({mkt[1]})")
    stamp = t.strftime("%Y-%m-%d %H:%M")
    rows, cands = [], []
    for code in codes:
        try:
            raw, name = loader(code)
        except Exception as e:  # noqa: BLE001
            log(f"  [실패] {code}: {e}")
            continue
        d = indicators.add_all(raw)
        s = score_at(d)
        price, atr = float(d["close"].iloc[-1]), float(d["atr"].iloc[-1])
        rows.append((code, name, f"{price:,.0f}", s.score, s.opinion))
        is_open = (ledger["code"] == code) & (ledger["status"] == "open")

        if is_open.any():                                   # ---- 보유 포지션 관리
            k = ledger.index[is_open][0]
            pos = ledger.loc[k]
            half = None if pd.isna(pos.half_ret) else float(pos.half_ret)
            t2 = pos.target2 if not pd.isna(pos.target2) else np.inf
            why = None
            if price <= pos.stop:
                why = "손절" if half is None else "1차익절+본전"
            elif half is None and price >= pos.target:
                if p.split:
                    half = price / pos.entry - 1
                    be = round(pos.entry * (1 + p.cost))
                    ledger.loc[k, ["half_ret", "stop"]] = [round(half, 6), be]
                    log(f"  💰 [1차 익절] {name}({code}) {price:,.0f}원 절반 매도 "
                        f"({half * 100:+.2f}%), 남은 절반 손절가 → 본전 {be:,}원")
                    if price >= t2:
                        why = "2차익절"
                else:
                    why = "익절"
            elif half is not None and price >= t2:
                why = "2차익절"
            if not why and pd.Timestamp(pos.entry_date).date() < t.date():
                # 청산 신호는 '장 마감' 기준: 오늘 봉이 진행 중이면 어제 봉으로 판단
                last_closed = -2 if d.index[-1].date() == t.date() else -1
                if latest(d, p, last_closed)[1]:
                    why = "점수하락" if p.strategy == "score" else "RSI회복"
                elif _held_days(pos.entry_date, t) > p.max_hold:
                    why = "기간만료"
                if why and half is not None:
                    why = "1차익절+" + why
            if why:
                r2 = price / pos.entry - 1
                ret = ((r2 if half is None else 0.5 * half + 0.5 * r2) - p.cost) * 100
                ledger.loc[k, ["status", "exit_date", "exit", "ret", "reason"]] = \
                    ["closed", stamp, price, round(ret, 2), why]
                log(f"  🔔 [모의 청산] {name}({code}) {price:,.0f}원 {why} → 총 {ret:+.2f}%")
        elif latest(d, p)[0]:                               # ---- 신규 진입 후보
            r = d.iloc[-1]
            prio = -s.score if p.strategy == "score" else float(r.rsi)
            cands.append(dict(prio=prio, code=code, name=name, price=price, atr=atr,
                              score=s.score, rsi=float(r.rsi)))

    # ---- 신규 진입: 우선순위(반등/눌림목 = RSI 낮은 순, 점수 = 점수 높은 순)대로 빈 자리만큼
    n_open = int((ledger["status"] == "open").sum())
    slots = max(0, p.max_pos - n_open)
    can_enter = mkt_ok and t.time() >= ENTRY_T and market_open(t)
    for k, c in enumerate(sorted(cands, key=lambda x: x["prio"])):
        tag = f"{c['name']}({c['code']}) {c['price']:,.0f}원 RSI {c['rsi']:.0f} 점수 {c['score']:+.0f}"
        if not mkt_ok:
            log(f"  ✋ [매수 보류] {tag} — 시장 필터")
        elif k >= slots:
            log(f"  ⏸ [자리 없음] {tag} — 보유 {n_open}/{p.max_pos}종목")
        elif can_enter:
            price, atr = c["price"], c["atr"]
            new = dict(code=c["code"], name=c["name"], entry_date=stamp, entry=price,
                       stop=round(price - stop_distance(p, price, atr)),
                       target=round(price + p.tp_atr * atr),
                       target2=round(price + p.tp2_atr * atr) if p.split else np.nan,
                       half_ret=np.nan, score=c["score"], status="open", exit_date="",
                       exit=np.nan, ret=np.nan, reason="")
            ledger = ledger.reset_index(drop=True)
            ledger.loc[len(ledger)] = new
            tp = (f"1차 {new['target']:,}(절반) / 2차 {new['target2']:,}" if p.split
                  else f"익절 {new['target']:,}")
            log(f"  🟢 [모의 매수] {tag} 손절 {new['stop']:,} / {tp}")
        else:
            log(f"  👀 [매수 후보] {tag} (15:15 이후 유지되면 진입)")
    if rows and len(rows) <= 30:
        log(pd.DataFrame(rows, columns=["코드", "종목", "현재가", "점수", "의견"])
            .sort_values("점수", ascending=False).to_string(index=False))
    elif rows:
        log(f"  {len(rows)}종목 점검 완료 | 매수 후보 {len(cands)}개 | "
            f"보유 {int((ledger['status'] == 'open').sum())}/{p.max_pos}")
    return ledger


def monitor(codes: list[str], p: Params, interval_min: float = 5, once: bool = False,
            days: int = 250):
    """장 시간 동안 반복 점검. 수급(전일까지 확정)은 하루 1회 캐시, 시세는 매번 새로."""
    def loader(code):
        if code.upper().startswith("DEMO"):
            seed = int(code[4:] or 7)
            return data.synthetic(days, seed=seed), f"가상종목{seed}"
        base, name = data.load(code, days, cache_hours=12)
        return data.refresh_price(base, code), name

    demo = all(c.upper().startswith("DEMO") for c in codes)

    def market_state() -> tuple[bool, str]:
        if not p.market_filter:
            return True, "필터 꺼짐"
        try:
            idx = data.load_index("KOSPI", 60, demo=demo)
            if not demo:
                idx = data.refresh_price(idx, "KOSPI")
            return market.status(market.flags(idx))
        except Exception as e:  # noqa: BLE001
            return True, f"지수 조회 실패({e}) -> 필터 미적용"

    print(f"감시 시작: {len(codes)}종목, {interval_min}분 간격\n설정: {p.describe()}")
    while True:
        t = now()
        if not once and not market_open(t):
            print(f"[{t:%m-%d %H:%M}] 장 시간이 아닙니다 (평일 09:00~15:30). "
                  f"--once 로 1회 점검만 할 수 있습니다.")
            return
        print(f"\n[{t:%Y-%m-%d %H:%M:%S}] 점검")
        ledger = step(codes, p, loader, t, read_ledger(), mkt=market_state())
        write_ledger(ledger)
        if once:
            return
        time.sleep(interval_min * 60)


def paper_report(target_n: int = 100, path: str = LEDGER) -> dict:
    lg = read_ledger(path)
    closed = lg[lg["status"] == "closed"].copy()
    closed["exit_date"] = pd.to_datetime(closed["exit_date"])
    st = summarize(closed)
    print(f"모의매매 진행: {st['n']}/{target_n}회 완료, 보유 중 {int((lg['status'] == 'open').sum())}건")
    if st["n"]:
        print(f"  승률 {st['win']:.1f}% | 평균 {st['avg']:+.2f}% | 평균이익 {st['avg_win']:+.2f}% "
              f"| 평균손실 {st['avg_loss']:+.2f}% | PF {st['pf']:.2f} | 최대연속손실 {st['max_losing']}회")
        if st["n"] >= target_n:
            ok = st["avg"] > 0 and st["pf"] > 1.1
            print(f"  {'✅' if ok else '❌'} {target_n}회 완료: 거래당 평균 {st['avg']:+.2f}%, "
                  f"PF {st['pf']:.2f} → {'실전 소액 시작 검토 가능' if ok else '실전 사용 비추천'}")
    return st
