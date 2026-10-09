"""기술적 지표 + 수급 지표 계산 (pandas만 사용)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    diff = close.diff()
    up = diff.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-diff.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100)


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(),
                    (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def stochastic(df: pd.DataFrame, n=14, k=3, d=3):
    lo, hi = df["low"].rolling(n).min(), df["high"].rolling(n).max()
    fast_k = 100 * (df["close"] - lo) / (hi - lo).replace(0, np.nan)
    slow_k = fast_k.rolling(k).mean()
    return slow_k, slow_k.rolling(d).mean()


def mfi(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Money Flow Index: 거래대금 가중 RSI (자금 유입 강도)."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    mf = tp * df["volume"]
    pos = mf.where(tp > tp.shift(), 0).rolling(n).sum()
    neg = mf.where(tp < tp.shift(), 0).rolling(n).sum()
    return 100 - 100 / (1 + pos / neg.replace(0, np.nan))


def obv(df: pd.DataFrame) -> pd.Series:
    sign = np.sign(df["close"].diff()).fillna(0)
    return (sign * df["volume"]).cumsum()


def _streak(s: pd.Series) -> pd.Series:
    """연속 순매수(+)/순매도(-) 일수."""
    out, cur = [], 0
    for v in s.fillna(0):
        if v > 0:
            cur = cur + 1 if cur > 0 else 1
        elif v < 0:
            cur = cur - 1 if cur < 0 else -1
        else:
            cur = 0
        out.append(cur)
    return pd.Series(out, index=s.index)


def add_all(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c = d["close"]
    for n in (5, 20, 60, 120):
        d[f"ma{n}"] = c.rolling(n).mean()
    d["rsi"] = rsi(c)
    d["macd"], d["macd_sig"], d["macd_hist"] = macd(c)
    d["atr"] = atr(d)
    d["stoch_k"], d["stoch_d"] = stochastic(d)
    d["mfi"] = mfi(d)
    d["obv"] = obv(d)
    d["obv_ma20"] = d["obv"].rolling(20).mean()
    mid, std = c.rolling(20).mean(), c.rolling(20).std()
    d["bb_up"], d["bb_mid"], d["bb_dn"] = mid + 2 * std, mid, mid - 2 * std
    d["bb_width"] = (d["bb_up"] - d["bb_dn"]) / mid
    d["vol_ratio"] = d["volume"] / d["volume"].rolling(20).mean()
    d["high20"] = d["high"].rolling(20).max()
    d["ret1"] = c.pct_change()

    # ---- 수급 (단위: 주). 거래량 대비 비율로 정규화해 종목 간 비교 가능하게.
    for who in ("foreign", "inst"):
        if who not in d:
            d[who] = np.nan
        d[f"{who}_5"] = d[who].rolling(5, min_periods=3).sum()
        d[f"{who}_20"] = d[who].rolling(20, min_periods=10).sum()
        d[f"{who}_pct5"] = d[f"{who}_5"] / d["volume"].rolling(5).sum() * 100
        d[f"{who}_streak"] = _streak(d[who])
    d["smart_5"] = d["foreign_5"] + d["inst_5"]
    d["smart_pct5"] = d["smart_5"] / d["volume"].rolling(5).sum() * 100
    return d
