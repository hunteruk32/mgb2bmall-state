"""점수 전략의 과거 성과 검증 (단순 백테스트).

규칙
  - 진입: 장 마감 점수 >= buy_th  ->  다음날 시가 매수
  - 청산: (1) 장중 손절가 터치  (2) 장중 2차 목표가 터치
          (3) 장 마감 점수 <= exit_th 또는 보유일 >= max_hold -> 다음날 시가 매도
  - 비용: 왕복 cost (수수료+세금, 기본 0.25%)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from signals import score_at


@dataclass
class Result:
    trades: pd.DataFrame
    total_return: float
    buy_hold: float
    win_rate: float
    avg_return: float
    mdd: float


def run(d: pd.DataFrame, buy_th: float = 25, exit_th: float = -10,
        max_hold: int = 10, cost: float = 0.0025, start: int = 60) -> Result:
    trades, pos = [], None
    for i in range(start, len(d) - 1):
        sig = score_at(d, i)
        nxt = d.iloc[i + 1]
        if pos is None:
            if sig.score >= buy_th:
                pos = dict(entry_date=d.index[i + 1], entry=nxt.open, stop=sig.stop,
                           target=sig.target2, held=0, entry_score=sig.score)
            continue
        # 보유 중: 당일(i, 진입일 포함) 장중 손절/익절 확인. 둘 다 닿으면 보수적으로 손절 처리
        row = d.iloc[i]
        exit_px, why = None, None
        if row.low <= pos["stop"]:
            exit_px, why = min(row.open, pos["stop"]), "손절"
        elif row.high >= pos["target"]:
            exit_px, why = max(row.open, pos["target"]), "목표가"
        pos["held"] += 1
        if exit_px is None and (sig.score <= exit_th or pos["held"] >= max_hold):
            exit_px, why = nxt.open, ("점수하락" if sig.score <= exit_th else "기간만료")
            exit_date = d.index[i + 1]
        else:
            exit_date = d.index[i]
        if exit_px is not None:
            ret = exit_px / pos["entry"] - 1 - cost
            trades.append(dict(진입일=pos["entry_date"].date(), 진입가=round(pos["entry"]),
                               청산일=exit_date.date(), 청산가=round(exit_px),
                               수익률=round(ret * 100, 2), 사유=why, 보유일=pos["held"]))
            pos = None
    t = pd.DataFrame(trades)
    if t.empty:
        return Result(t, 0.0, _bh(d, start), 0.0, 0.0, 0.0)
    equity = (1 + t["수익률"] / 100).cumprod()
    mdd = float((equity / equity.cummax() - 1).min() * 100)
    return Result(t, float((equity.iloc[-1] - 1) * 100), _bh(d, start),
                  float((t["수익률"] > 0).mean() * 100), float(t["수익률"].mean()), mdd)


def _bh(d, start):
    return float((d["close"].iloc[-1] / d["close"].iloc[start] - 1) * 100)
