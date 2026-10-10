"""신호 연구: 어떤 신호가 '매년 꾸준히' 시장 평균보다 나았는지 확인.

- 수익률: 신호일 다음날 시가 매수 → horizon 일 뒤 종가
- 초과수익: 같은 날 전체 종목 평균 수익률을 뺀 값 (시장 전체 상승/하락 효과 제거)
- 연도별로 따로 계산해서, 해마다 부호(+/-)가 유지되는 신호만 의미 있다고 본다.
"""
from __future__ import annotations

import unicodedata

import numpy as np
import pandas as pd


def pad(text: str, width: int) -> str:
    """한글(2칸) 폭을 고려해 오른쪽을 공백으로 채움."""
    w = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return text + " " * max(0, width - w)


def _signals(d: pd.DataFrame) -> dict[str, pd.Series]:
    c = d["close"]
    ret5 = c.pct_change(5) * 100
    up = (c > d["open"]) & (c > c.shift())
    f5, i5 = d["foreign_5"], d["inst_5"]
    sig = {
        "점수 ≥ 55": d["score"] >= 55,
        "점수 ≥ 25": d["score"] >= 25,
        "점수 ≤ -25": d["score"] <= -25,
        "추세 영역 +": d["part_추세"] > 0,
        "모멘텀 영역 +": d["part_모멘텀"] > 0,
        "거래량 영역 +": d["part_거래량"] > 0,
        "수급 영역 +": d["part_수급"] > 0,
        "외국인 5일 순매수": f5 > 0,
        "기관 5일 순매수": i5 > 0,
        "외인·기관 쌍끌이": (f5 > 0) & (i5 > 0),
        "외인·기관 동반매도": (f5 < 0) & (i5 < 0),
        "외인+기관 순매수 ≥ 거래량10%": d["smart_pct5"] >= 10,
        "외국인 3일+ 연속 순매수": d["foreign_streak"] >= 3,
        "기관 3일+ 연속 순매수": d["inst_streak"] >= 3,
        "20일 신고가 돌파": c > d["high20"].shift(),
        "거래량 2배 + 양봉": (d["vol_ratio"] >= 2) & up,
        "RSI ≤ 30": d["rsi"] <= 30,
        "RSI ≥ 70": d["rsi"] >= 70,
        "눌림목 120일선 위·RSI ≤ 40": (c > d["ma120"]) & (d["rsi"] <= 40),
        "눌림목 60일선 위·RSI ≤ 45": (c > d["ma60"]) & (d["rsi"] <= 45),
        "20일선 대비 -10% 이하": c / d["ma20"] <= 0.9,
        "5일간 -8% 이상 급락": ret5 <= -8,
        "5일간 +10% 이상 급등": ret5 >= 10,
    }
    return {k: v.fillna(False).astype(bool) for k, v in sig.items()}


def build(datasets: dict[str, pd.DataFrame], horizon: int = 5) -> tuple[pd.DataFrame, list[str]]:
    frames, names = [], []
    for code, d in datasets.items():
        o, c = d["open"].to_numpy(), d["close"].to_numpy()
        n = len(d)
        fwd = np.full(n, np.nan)
        if n > horizon + 1:
            entry = o[1: n - horizon]
            with np.errstate(divide="ignore", invalid="ignore"):
                fwd[: n - horizon - 1] = np.where(entry > 0, (c[horizon + 1:] / entry - 1) * 100,
                                                  np.nan)
        sig = _signals(d)
        names = list(sig)
        t = pd.DataFrame({"code": code, "date": d.index.to_numpy(), "fwd": fwd,
                          "mkt_ok": d["mkt_ok"].to_numpy(bool) if "mkt_ok" in d else True,
                          **{k: v.to_numpy() for k, v in sig.items()}})
        t = t[d["score"].notna().to_numpy()]
        frames.append(t)
    t = pd.concat(frames, ignore_index=True).dropna(subset=["fwd"])
    t["excess"] = t["fwd"] - t.groupby("date")["fwd"].transform("mean")
    t["year"] = pd.DatetimeIndex(t["date"]).year
    return t, names


def _cell(x: pd.Series, min_n: int = 30) -> str:
    return f"{x.mean():+5.2f}({len(x):>4})" if len(x) >= min_n else f"{'-':>11}"


def report(datasets: dict[str, pd.DataFrame], horizon: int = 5, min_n: int = 30) -> pd.DataFrame:
    t, names = build(datasets, horizon)
    years = sorted(t["year"].unique())
    head = pad("", 30) + "".join(f"{y:>12}" for y in years)
    print(f"\n[1] 연도별 시장 상황: 아무 날이나 샀을 때 {horizon}일 수익률 평균 (건수)")
    print(head)
    print(pad("전체 평균", 30) + "".join(f" {_cell(t.fwd[t.year == y], min_n)}" for y in years))

    print(f"\n[2] 신호별 초과수익: 같은 날 시장 평균 대비 {horizon}일 수익률 차이 %p (건수)")
    print("    '꾸준함' = 표본 충분한 해 중 초과수익 플러스인 해의 수. 매년 플러스여야 믿을 만함")
    print(head + f"{'꾸준함':>8}{'전체':>9}")
    rows = []
    for k in names:
        s = t[t[k]]
        cells, pos, valid = [], 0, 0
        for y in years:
            x = s.excess[s.year == y]
            cells.append(_cell(x, min_n))
            if len(x) >= min_n:
                valid += 1
                pos += int(x.mean() > 0)
        allm = s.excess.mean() if len(s) else np.nan
        rows.append(dict(signal=k, pos=pos, valid=valid, mean=allm, n=len(s)))
        print(pad(k, 30) + "".join(f" {c}" for c in cells) + f"{f'{pos}/{valid}':>8}{allm:+8.2f}")

    print(f"\n[3] 시장 필터: 코스피 약세일 vs 정상일 ({horizon}일 수익률, 초과수익 아님)")
    print(head)
    for label, m in (("코스피 정상일", t.mkt_ok), ("코스피 약세일", ~t.mkt_ok)):
        print(pad(label, 30) + "".join(f" {_cell(t.fwd[m & (t.year == y)], min_n)}" for y in years))

    r = pd.DataFrame(rows)
    good = r[(r.valid >= 3) & (r.pos == r.valid) & (r["mean"] > 0)]
    bad = r[(r.valid >= 3) & (r.pos == 0) & (r["mean"] < 0)]
    print("\n[요약]")
    print("  매년 시장보다 나았던 신호: " + (", ".join(good.signal) if len(good) else "없음"))
    print("  매년 시장보다 못했던 신호: " + (", ".join(bad.signal) if len(bad) else "없음")
          + "  (피해야 할 신호 후보)")
    print("  ※ 주의: 종목 목록이 '현재' 시가총액 상위라서, 과거에 폭락 후 회복 못 한 종목은 빠져 있음"
          "\n    (생존 편향). 특히 '급락 후 매수' 신호가 실제보다 좋게 나올 수 있음."
          "\n  ※ 초과수익은 수수료·세금(왕복 약 0.25%) 차감 전 숫자.")
    return r
