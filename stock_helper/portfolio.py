"""계좌 단위 시뮬레이션: 동시 보유 종목 수와 자금 한도를 지키며 매매했을 때의 계좌 흐름.

규칙
  - 동시에 최대 max_pos 종목. 한 종목당 '그날 계좌 평가액 / max_pos' 만큼 매수 (현금 한도 내)
  - 같은 날 신호가 여러 개면 우선순위대로: 반등/눌림목 = RSI 낮은 순, 점수 = 점수 높은 순
  - 이미 보유 중인 종목은 추가 매수 안 함
  - 개별 매매의 진입/청산 규칙은 backtest 와 동일 (손절·분할익절·청산신호·보유기간)
  - 평가액은 매일 종가로 계산 (분할 익절로 절반 판 뒤에도 전량 보유로 근사)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest import Params, candidates


def priority(t: dict, p: Params) -> float:
    if p.strategy == "score":
        return -(t["score"] if not np.isnan(t["score"]) else -999)
    return t["rsi"] if not np.isnan(t["rsi"]) else 999


def run(datasets: dict[str, pd.DataFrame], plan: list[tuple[pd.Timestamp, pd.Timestamp | None, Params]],
        max_pos: int = 5, capital: float = 1.0) -> dict:
    """plan: [(시작일, 종료일 또는 None, 그 기간에 쓸 설정)] — walk-forward 구간별 설정."""
    cands = []
    for lo, hi, p in plan:
        for code, d in datasets.items():
            for t in candidates(d, p, code):
                if t["entry_date"] >= lo and (hi is None or t["entry_date"] < hi):
                    t["prio"] = priority(t, p)
                    cands.append(t)
    start = plan[0][0]
    closes = pd.DataFrame({c: d["close"] for c, d in datasets.items()}).sort_index()
    closes = closes[closes.index >= start].ffill()
    by_entry: dict[pd.Timestamp, list[dict]] = {}
    for t in cands:
        by_entry.setdefault(t["entry_date"], []).append(t)

    cash, equity, pos, taken, skipped = capital, capital, [], [], 0
    curve = []
    for day, row in closes.iterrows():
        # 1) 오늘 청산되는 포지션 정리
        keep = []
        for q in pos:
            if q["exit_date"] <= day:
                cash += q["alloc"] * (1 + q["ret"] / 100)
                taken.append(q)
            else:
                keep.append(q)
        pos = keep
        # 2) 오늘 시가 진입 후보 (우선순위 순)
        held = {q["code"] for q in pos}
        for t in sorted(by_entry.get(day, []), key=lambda x: x["prio"]):
            if t["code"] in held:
                continue
            if len(pos) >= max_pos:
                skipped += 1
                continue
            alloc = min(cash, equity / max_pos)
            if alloc <= equity * 0.01:
                skipped += 1
                continue
            cash -= alloc
            pos.append({**t, "alloc": alloc})
            held.add(t["code"])
        # 3) 종가 평가
        mtm = 0.0
        for q in pos:
            px = row.get(q["code"], np.nan)
            mtm += q["alloc"] * (px / q["entry"] if px == px and q["entry"] > 0 else 1.0)
        equity = cash + mtm
        curve.append((day, equity, len(pos)))
    # 시뮬레이션 끝에 남은 포지션은 평가액 그대로 둠
    eq = pd.DataFrame(curve, columns=["date", "equity", "npos"]).set_index("date")
    return dict(curve=eq, trades=pd.DataFrame(taken), skipped=skipped, n_cand=len(cands))


def stats(eq: pd.Series) -> dict:
    ret = eq.iloc[-1] / eq.iloc[0] - 1
    years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
    cagr = (1 + ret) ** (1 / years) - 1 if ret > -1 else -1.0
    dd = eq / eq.cummax() - 1
    # 연도별: 전년도 마지막 값 대비 (첫 해는 시작값 대비)
    prev = eq.groupby(eq.index.year).last().shift(1)
    prev.iloc[0] = eq.iloc[0]
    yr = (eq.groupby(eq.index.year).last() / prev - 1) * 100
    return dict(total=ret * 100, cagr=cagr * 100, mdd=float(dd.min() * 100),
                mdd_date=dd.idxmin(), yearly=yr, years=years)


def benchmark(idx: pd.DataFrame, start: pd.Timestamp) -> pd.Series:
    c = idx["close"]
    return c[c.index >= start]
