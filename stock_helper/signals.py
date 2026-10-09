"""지표 + 수급을 점수화하여 매수/매도 의견을 산출."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

BUY_STRONG, BUY, SELL, SELL_STRONG = 50, 25, -25, -50


@dataclass
class Signal:
    date: pd.Timestamp
    close: float
    score: float
    parts: dict[str, float]
    opinion: str
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    exit_alerts: list[str] = field(default_factory=list)
    stop: float = np.nan
    target1: float = np.nan
    target2: float = np.nan
    has_flows: bool = True


def _ok(*vals) -> bool:
    return all(v is not None and not pd.isna(v) for v in vals)


def _crossed_up(a: pd.Series, b: pd.Series, i: int, within: int = 3) -> bool:
    for k in range(max(1, i - within + 1), i + 1):
        if _ok(a.iloc[k - 1], b.iloc[k - 1], a.iloc[k], b.iloc[k]) and \
                a.iloc[k - 1] <= b.iloc[k - 1] and a.iloc[k] > b.iloc[k]:
            return True
    return False


def score_at(d: pd.DataFrame, i: int = -1) -> Signal:
    """d: indicators.add_all() 결과. i 번째 날(기본 마지막 날)의 신호."""
    if i < 0:
        i = len(d) + i
    r, p = d.iloc[i], d.iloc[i - 1]
    reasons, warns, alerts = [], [], []
    parts = {"추세": 0.0, "모멘텀": 0.0, "거래량": 0.0, "수급": 0.0}

    def add(part, pts, msg=None):
        parts[part] += pts
        if msg:
            reasons.append(f"{'▲' if pts > 0 else '▼'} [{part}] {msg} ({pts:+g})")

    # ------------------------------------------------ 추세 (최대 30)
    if _ok(r.ma20):
        add("추세", 8 if r.close > r.ma20 else -8,
            "종가가 20일선 위" if r.close > r.ma20 else "종가가 20일선 아래")
        add("추세", 7 if r.ma5 > r.ma20 else -7,
            "5일선 > 20일선 (단기 정배열)" if r.ma5 > r.ma20 else "5일선 < 20일선")
        ma20_prev = d["ma20"].iloc[i - 5]
        if _ok(ma20_prev):
            add("추세", 5 if r.ma20 > ma20_prev else -5,
                "20일선 우상향" if r.ma20 > ma20_prev else "20일선 하락 중")
    if _ok(r.ma20, r.ma60):
        add("추세", 5 if r.ma20 > r.ma60 else -5,
            "20일선 > 60일선 (중기 상승)" if r.ma20 > r.ma60 else "20일선 < 60일선 (중기 하락)")
    if _crossed_up(d["ma5"], d["ma20"], i):
        add("추세", 5, "최근 3일 내 5/20 골든크로스")
    elif _crossed_up(d["ma20"], d["ma5"], i):
        add("추세", -5, "최근 3일 내 5/20 데드크로스")
        alerts.append("5/20일선 데드크로스")

    # ------------------------------------------------ 모멘텀 (최대 25)
    h, hp = r.macd_hist, p.macd_hist
    if _ok(h, hp):
        if h > 0 and h > hp:
            add("모멘텀", 8, "MACD 히스토그램 양(+)이며 확대")
        elif h > 0:
            add("모멘텀", 3, "MACD 양(+)이나 둔화")
        elif h > hp:
            add("모멘텀", 2, "MACD 음(-)이나 개선 중")
        else:
            add("모멘텀", -8, "MACD 음(-)이며 악화")
    if _crossed_up(d["macd"], d["macd_sig"], i):
        add("모멘텀", 5, "최근 3일 내 MACD 시그널 상향 돌파")
    rsi_v, rsi_p = r.rsi, p.rsi
    if 50 <= rsi_v < 70:
        add("모멘텀", 6, f"RSI {rsi_v:.0f} (상승 구간)")
    elif 70 <= rsi_v < 80:
        warns.append(f"RSI {rsi_v:.0f}: 과열 근접, 추격 매수 자제")
    elif rsi_v >= 80:
        add("모멘텀", -8, f"RSI {rsi_v:.0f} 과열")
    elif rsi_v < 30:
        if rsi_v > rsi_p:
            add("모멘텀", 3, f"RSI {rsi_v:.0f} 과매도권에서 반등")
        else:
            add("모멘텀", -3, f"RSI {rsi_v:.0f} 과매도권 하락 지속")
    elif rsi_v > rsi_p:
        add("모멘텀", 2, f"RSI {rsi_v:.0f} 상승 전환")
    if rsi_p >= 75 and rsi_v < rsi_p - 3:
        alerts.append(f"RSI 과열권({rsi_p:.0f})에서 꺾임")
    if _ok(r.stoch_k, r.stoch_d) and _crossed_up(d["stoch_k"], d["stoch_d"], i, 2) and r.stoch_k < 35:
        add("모멘텀", 6, "스토캐스틱 침체권 골든크로스")

    # ------------------------------------------------ 거래량/자금흐름 (최대 ~18)
    up_day = r.close > r.open and r.close > p.close
    if _ok(r.vol_ratio) and r.vol_ratio >= 1.5:
        if up_day:
            add("거래량", 8, f"거래량 {r.vol_ratio:.1f}배 동반 양봉")
        elif r.close < p.close:
            add("거래량", -8, f"거래량 {r.vol_ratio:.1f}배 동반 하락")
            alerts.append("대량 거래 동반 하락")
    if _ok(r.obv, r.obv_ma20):
        add("거래량", 4 if r.obv > r.obv_ma20 else -4,
            "OBV 20일 평균 상회 (매집)" if r.obv > r.obv_ma20 else "OBV 20일 평균 하회 (분산)")
    if _ok(r.mfi):
        if r.mfi >= 80:
            add("거래량", -3, f"MFI {r.mfi:.0f} 자금 과열")
        elif r.mfi <= 20 and r.mfi > p.mfi:
            add("거래량", 3, f"MFI {r.mfi:.0f} 침체권 반등")
    if _ok(p.high20) and r.close > p.high20:
        add("거래량", 3, "20일 신고가 돌파")

    # ------------------------------------------------ 수급 (최대 30)
    has_flows = _ok(r.foreign_5, r.inst_5)
    if has_flows:
        f5, i5 = r.foreign_5, r.inst_5
        add("수급", 6 if f5 > 0 else -6, f"외국인 5일 {'순매수' if f5 > 0 else '순매도'} {f5:+,.0f}주")
        add("수급", 6 if i5 > 0 else -6, f"기관 5일 {'순매수' if i5 > 0 else '순매도'} {i5:+,.0f}주")
        if f5 > 0 and i5 > 0:
            add("수급", 6, "외국인·기관 쌍끌이 매수")
        elif f5 < 0 and i5 < 0:
            add("수급", -6, "외국인·기관 동반 매도")
        if _ok(r.smart_pct5):
            if r.smart_pct5 >= 10:
                add("수급", 6, f"5일 거래량 중 {r.smart_pct5:.0f}%를 외인+기관이 순매수")
            elif r.smart_pct5 <= -10:
                add("수급", -6, f"5일 거래량 중 {-r.smart_pct5:.0f}%를 외인+기관이 순매도")
        for who, label in (("foreign", "외국인"), ("inst", "기관")):
            s = r[f"{who}_streak"]
            if s >= 3:
                add("수급", 3, f"{label} {int(s)}일 연속 순매수")
            elif s <= -3:
                add("수급", -3, f"{label} {int(-s)}일 연속 순매도")
                alerts.append(f"{label} {int(-s)}일 연속 순매도")
    else:
        warns.append("수급 데이터 없음: 기술적 지표만으로 판단 (신뢰도 낮음)")

    # ------------------------------------------------ 종합
    max_pts = 103 if has_flows else 73
    score = float(np.clip(sum(parts.values()) / max_pts * 100, -100, 100))

    if score >= BUY_STRONG:
        opinion = "강력 매수"
    elif score >= BUY:
        opinion = "매수 관심 (분할 매수)"
    elif score > SELL:
        opinion = "관망"
    elif score > SELL_STRONG:
        opinion = "매도 / 비중 축소"
    else:
        opinion = "강력 매도"

    if _ok(r.bb_up) and r.close > r.bb_up:
        warns.append("볼린저 상단 돌파: 단기 이격 과대, 눌림목 대기 권장")
    if _ok(r.ma20) and r.close / r.ma20 > 1.15:
        warns.append(f"20일선 이격도 {r.close / r.ma20 * 100:.0f}%: 과열")
    if _ok(r.ma20) and r.close < r.ma20 and p.close >= p.ma20:
        alerts.append("20일선 하향 이탈")

    a = r.atr if _ok(r.atr) else r.close * 0.03
    stop = r.close - 2 * a
    if _ok(r.ma20) and r.ma20 < r.close:
        stop = max(stop, r.ma20 * 0.97)  # 20일선 3% 아래가 더 가까우면 그 값
    return Signal(date=d.index[i], close=float(r.close), score=round(score, 1), parts=parts,
                  opinion=opinion, reasons=reasons, warnings=warns, exit_alerts=alerts,
                  stop=float(stop), target1=float(r.close + 2 * a),
                  target2=float(r.close + 4 * a), has_flows=has_flows)


def score_series(d: pd.DataFrame, start: int = 60) -> pd.Series:
    return pd.Series({d.index[i]: score_at(d, i).score for i in range(start, len(d))})
