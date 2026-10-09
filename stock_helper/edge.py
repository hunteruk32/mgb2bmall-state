"""신호 자체에 예측력(edge)이 있는지 진단.

매매 규칙(익절/손절)과 무관하게, '신호가 나온 다음날 시가에 사서 N일 뒤 종가'의
평균 수익률을 점수 구간별 / 영역별로 비교한다.
점수가 높을수록 이후 수익률이 높아야 전략이 의미가 있다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest import PARTS

BUCKETS = [(-101, -25, "≤ -25"), (-25, 0, "-25~0"), (0, 25, "0~25"),
           (25, 45, "25~45"), (45, 55, "45~55"), (55, 101, "≥ 55")]


def forward_table(datasets: dict[str, pd.DataFrame], horizon: int = 5) -> pd.DataFrame:
    rows = []
    for code, d in datasets.items():
        o, c = d["open"].to_numpy(), d["close"].to_numpy()
        n = len(d)
        fwd = np.full(n, np.nan)
        if n > horizon + 1:
            entry = o[1: n - horizon]
            with np.errstate(divide="ignore", invalid="ignore"):
                fwd[: n - horizon - 1] = np.where(entry > 0, (c[horizon + 1:] / entry - 1) * 100,
                                                  np.nan)
        t = pd.DataFrame({"code": code, "date": d.index, "score": d["score"].to_numpy(),
                          "fwd": fwd, "mkt_ok": d.get("mkt_ok", True)})
        for k in PARTS:
            t[k] = d[f"part_{k}"].to_numpy()
        rows.append(t)
    return pd.concat(rows).dropna(subset=["score", "fwd"])


def _stats(x: pd.Series) -> str:
    if len(x) < 20:
        return f"{'(표본 부족)':>24}"
    return f"평균 {x.mean():+5.2f}% 상승확률 {(x > 0).mean() * 100:4.0f}% ({len(x):>5}건)"


def report(datasets: dict[str, pd.DataFrame], cut: pd.Timestamp, horizon: int = 5):
    t = forward_table(datasets, horizon)
    halves = (("학습", t[t.date < cut]), ("검증", t[t.date >= cut]))
    print(f"\n[1] 점수 구간별: 다음날 시가 매수 → {horizon}일 뒤 종가 수익률")
    print("    (점수가 높을수록 수익률이 높아야 정상. 모든 날 기준 = 비교용 바닥값)")
    for label, h in halves:
        print(f"  ── {label} ── 모든 날 기준: {_stats(h.fwd)}")
        for lo, hi, name in BUCKETS:
            print(f"    점수 {name:>7}: {_stats(h.fwd[(h.score > lo) & (h.score <= hi)])}")

    print(f"\n[2] 영역별: 각 영역 점수가 플러스인 날 vs 마이너스인 날 ({horizon}일 수익률)")
    print("    (플러스 쪽이 확실히 높아야 그 영역이 쓸모 있음)")
    for k in PARTS:
        for label, h in halves:
            pos, neg = h.fwd[h[k] > 0], h.fwd[h[k] < 0]
            diff = pos.mean() - neg.mean() if len(pos) and len(neg) else np.nan
            print(f"  {k:<4} {label}: + {_stats(pos)} | - {_stats(neg)} | 차이 {diff:+.2f}%p")

    print(f"\n[3] 시장 필터: 코스피 정상일 vs 약세일 ({horizon}일 수익률, 점수 ≥ 25 인 날만)")
    for label, h in halves:
        s = h[h.score >= 25]
        print(f"  {label}: 정상 {_stats(s.fwd[s.mkt_ok.astype(bool)])} | "
              f"약세 {_stats(s.fwd[~s.mkt_ok.astype(bool)])}")
    return t


def pullback_report(datasets: dict[str, pd.DataFrame], cut: pd.Timestamp, horizon: int = 5):
    """눌림목 신호가 난 날 vs 모든 날의 이후 수익률 (조건별)."""
    from backtest import Params, signals
    t = forward_table(datasets, horizon)
    print(f"\n[5] 눌림목 신호: 신호일 다음날 시가 매수 → {horizon}일 뒤 종가 (시장필터 없이)")
    for label, lo, hi in (("학습", None, cut), ("검증", cut, None)):
        base = t[(t.date >= lo if lo is not None else True) & (t.date < hi if hi is not None else True)]
        print(f"  ── {label} ── 모든 날 기준: {_stats(base.fwd)}")
        for ma in (60, 120):
            for th in (30, 35, 40):
                for confirm in (False, True):
                    p = Params(strategy="pullback", trend_ma=ma, rsi_th=th, rsi_confirm=confirm,
                               market_filter=False)
                    sel = []
                    for code, d in datasets.items():
                        ent, _, _ = signals(d, p)
                        sel.append(pd.DataFrame({"code": code, "date": d.index[ent].to_numpy()}))
                    s = base.reset_index(drop=True).merge(pd.concat(sel), on=["code", "date"])
                    print(f"    {ma:>3}일선 위·RSI≤{th}{'·반등' if confirm else '     '}: "
                          f"{_stats(s.fwd)}")
