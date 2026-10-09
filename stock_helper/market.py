"""시장 필터 (B): 시장 전체가 약할 때는 신규 매수를 하지 않는다.

신규 매수 금지 조건 (하나라도 해당하면 금지)
  1. 지수 종가 < 지수 20일 이동평균      (하락 추세장)
  2. 지수 당일 등락률 <= -1.5%            (급락일)
  3. 지수 5일 등락률  <= -3.0%            (단기 급락 구간)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MA, DAY_DROP, WEEK_DROP = 20, -1.5, -3.0


def flags(idx: pd.DataFrame, name: str = "코스피") -> pd.DataFrame:
    c = idx["close"]
    ma = c.rolling(MA).mean()
    d1 = c.pct_change() * 100
    d5 = c.pct_change(5) * 100
    reasons = []
    for cv, mv, a, b in zip(c, ma, d1, d5):
        r = []
        if not np.isnan(mv) and cv < mv:
            r.append(f"{name} 20일선 아래")
        if not np.isnan(a) and a <= DAY_DROP:
            r.append(f"{name} 당일 {a:+.1f}%")
        if not np.isnan(b) and b <= WEEK_DROP:
            r.append(f"{name} 5일 {b:+.1f}%")
        reasons.append(", ".join(r))
    out = pd.DataFrame({"mkt_ok": [r == "" for r in reasons], "mkt_reason": reasons},
                       index=idx.index)
    return out


def attach(d: pd.DataFrame, mk: pd.DataFrame | None) -> pd.DataFrame:
    """종목 데이터에 날짜 기준으로 시장 필터 컬럼을 붙임. 시장 데이터 없으면 항상 허용."""
    d = d.copy()
    if mk is None or mk.empty:
        d["mkt_ok"], d["mkt_reason"] = True, ""
        return d
    m = mk.reindex(d.index, method="ffill")
    d["mkt_ok"] = m["mkt_ok"].fillna(True).astype(bool)
    d["mkt_reason"] = m["mkt_reason"].fillna("")
    return d


def status(mk: pd.DataFrame) -> tuple[bool, str]:
    r = mk.iloc[-1]
    return bool(r.mkt_ok), (r.mkt_reason or "정상")
