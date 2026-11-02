"""순수 계산 함수 모음 (네트워크 없음, 테스트 가능).

컬럼 규약 (pykrx 일봉과 동일): 시가, 고가, 저가, 종가, 거래대금
"""
from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# 기본 파라미터 (가이드 기준값)
# ---------------------------------------------------------------------------
MIN_VALUE_WON = 300_000_000_000  # 일 거래대금 3,000억 원
ENV_PERIOD = 20                  # Envelope 기간 (SMA 20)
ENV_PCT = 12.5                   # Envelope 폭 ±12.5%
OVERHEAT_PCT = 10.0              # 상단선 대비 10% 이상 이탈 = 과매수 경계
VALUE_DROP_RATIO = 0.5           # 3일차 거래대금이 직전 2일 평균의 50% 이하 = 급감
UPPER_WICK_RATIO = 0.5           # 윗꼬리가 당일 고저폭의 50% 이상 = 긴 윗꼬리
PULLBACK_BAND_PCT = 3.0          # 중심선 ±3% 이내 = 중심선 지지 테스트
PULLBACK_LOOKBACK = 10           # 최근 10일 내 상단 돌파 이력이 있어야 눌림목으로 인정


def is_bullish(row) -> bool:
    """진성 양봉: 종가 > 시가 (정규장 시가 기준)."""
    return float(row["종가"]) > float(row["시가"]) > 0


def passes_day(row, min_value: float = MIN_VALUE_WON) -> bool:
    return is_bullish(row) and float(row["거래대금"]) >= min_value


def screen_two_days(day1: pd.DataFrame, day2: pd.DataFrame,
                    min_value: float = MIN_VALUE_WON) -> list[str]:
    """전종목 일봉 2장(티커 index)을 받아 2일 연속 조건 충족 티커 반환."""
    common = day1.index.intersection(day2.index)
    d1, d2 = day1.loc[common], day2.loc[common]
    ok1 = (d1["종가"] > d1["시가"]) & (d1["시가"] > 0) & (d1["거래대금"] >= min_value)
    ok2 = (d2["종가"] > d2["시가"]) & (d2["시가"] > 0) & (d2["거래대금"] >= min_value)
    hits = d2[ok1 & ok2]
    return list(hits.sort_values("거래대금", ascending=False).index)


def envelope(close: pd.Series, period: int = ENV_PERIOD,
             pct: float = ENV_PCT) -> pd.DataFrame:
    mid = close.rolling(period).mean()
    return pd.DataFrame({
        "종가": close,
        "중심선": mid,
        "상단선": mid * (1 + pct / 100),
        "하단선": mid * (1 - pct / 100),
    })


def analyze_envelope(close: pd.Series, period: int = ENV_PERIOD,
                     pct: float = ENV_PCT) -> dict:
    """마지막 날 기준 Envelope 상태 판정."""
    env = envelope(close, period, pct).dropna()
    if env.empty:
        return {"상태": "데이터부족"}
    last = env.iloc[-1]
    c, mid, up, lo = last["종가"], last["중심선"], last["상단선"], last["하단선"]

    above = (env["종가"] > env["상단선"]).tolist()
    walk = 0
    for flag in reversed(above):
        if not flag:
            break
        walk += 1

    recent_break = bool(any(above[-PULLBACK_LOOKBACK:]))
    dist_mid = (c / mid - 1) * 100

    if c > up:
        state = f"상단 이탈 (밴드워킹 {walk}일)" if walk >= 2 else "상단 이탈 (첫 돌파)"
    elif c < lo:
        state = "하단 이탈 (과매도·반등 타점 점검)"
    elif abs(dist_mid) <= PULLBACK_BAND_PCT and recent_break:
        state = "중심선 눌림목 (지지 테스트)"
    elif c >= mid:
        state = "중심선 위"
    else:
        state = "중심선 아래"

    return {
        "상태": state,
        "중심선": round(mid),
        "상단선": round(up),
        "하단선": round(lo),
        "상단대비%": round((c / up - 1) * 100, 2),
        "중심선대비%": round(dist_mid, 2),
        "밴드워킹일수": walk,
    }


def upper_wick_ratio(row) -> float:
    hi, lo = float(row["고가"]), float(row["저가"])
    if hi <= lo:
        return 0.0
    body_top = max(float(row["시가"]), float(row["종가"]))
    return (hi - body_top) / (hi - lo)


def day3_risk(day1, day2, day3, upper_excess_day2: float | None) -> dict:
    """2일 연속 신호 이후 3일차 리스크 점검 (가이드 4번 체크리스트)."""
    avg_value = (float(day1["거래대금"]) + float(day2["거래대금"])) / 2
    v3 = float(day3["거래대금"])
    value_ratio = v3 / avg_value if avg_value else 0.0
    wick = upper_wick_ratio(day3)
    bearish = float(day3["종가"]) < float(day3["시가"])

    flags = []
    if upper_excess_day2 is not None and upper_excess_day2 >= OVERHEAT_PCT and bearish:
        flags.append("과매수 경계: 상단 10%↑ 이탈 후 음봉 → 단기 차익실현 경계")
    if value_ratio <= VALUE_DROP_RATIO and wick >= UPPER_WICK_RATIO:
        flags.append("거래대금 급감 + 윗꼬리 → 비중 조절 검토")
    elif value_ratio <= VALUE_DROP_RATIO:
        flags.append("거래대금 급감 (윗꼬리는 없음)")

    return {
        "3일차양봉": is_bullish(day3),
        "3일차거래대금비율": round(value_ratio, 2),
        "3일차윗꼬리비율": round(wick, 2),
        "경고": " / ".join(flags) if flags else "-",
    }


def summarize_flows(flow: pd.DataFrame, total_value: float) -> dict:
    """투자자별 순매수(상세) DataFrame → 요약. total_value = 기간 합산 거래대금."""
    s = flow.sum()
    g = lambda k: float(s.get(k, 0))  # noqa: E731
    inst_cols = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금"]
    inst = g("기관합계") if "기관합계" in s else sum(g(k) for k in inst_cols)
    frgn = g("외국인합계") if "외국인합계" in s else g("외국인") + g("기타외국인")

    if inst > 0 and frgn > 0:
        who = "쌍끌이 매수"
    elif frgn > 0:
        who = "외국인 주도"
    elif inst > 0:
        who = "기관 주도"
    else:
        who = "외인·기관 동반 매도"

    if inst > 0 and "투신" in s and "연기금" in s:
        lead_inst = "투신" if g("투신") >= g("연기금") else "연기금"
        who += f" (기관 내 {lead_inst} 우위)"

    pct = lambda x: round(x / total_value * 100, 1) if total_value else 0.0  # noqa: E731
    return {
        "수급": who,
        "외국인순매수(억)": round(frgn / 1e8),
        "기관순매수(억)": round(inst / 1e8),
        "투신(억)": round(g("투신") / 1e8),
        "연기금(억)": round(g("연기금") / 1e8),
        "개인(억)": round(g("개인") / 1e8),
        "외국인비중%": pct(frgn),
        "기관비중%": pct(inst),
    }
