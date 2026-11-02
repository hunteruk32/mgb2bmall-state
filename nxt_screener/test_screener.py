"""오프라인 테스트: 가짜 pykrx 모듈로 전체 흐름 검증."""
import sys
import types

import numpy as np
import pandas as pd

import indicators as ind

DAYS = ["20261028", "20261029", "20261030"]
EOK = 1e8


def _daily(rows):
    df = pd.DataFrame(rows, columns=["티커", "시가", "고가", "저가", "종가", "거래량", "거래대금", "등락률"])
    return df.set_index("티커")


DAILY = {
    # A: 3일 연속 대량 양봉 / B: 신규 2일(28일은 소량) / C: 28~29 신호 후 30일 급감+윗꼬리 음봉 / D: 음봉 / E: 거래대금 부족
    "20261028": _daily([("A", 100, 110, 99, 108, 0, 4000*EOK, 1), ("B", 50, 52, 49, 51, 0, 100*EOK, 1),
                        ("C", 200, 230, 199, 225, 0, 5000*EOK, 1), ("D", 10, 11, 9, 10.5, 0, 3500*EOK, 1),
                        ("E", 10, 11, 9, 10.5, 0, 1000*EOK, 1)]),
    "20261029": _daily([("A", 108, 118, 107, 116, 0, 3500*EOK, 1), ("B", 51, 56, 50, 55, 0, 3200*EOK, 1),
                        ("C", 225, 260, 224, 258, 0, 6000*EOK, 1), ("D", 11, 11, 9, 9.5, 0, 3500*EOK, 1),
                        ("E", 10.5, 12, 10, 11.5, 0, 1000*EOK, 1)]),
    "20261030": _daily([("A", 116, 125, 115, 123, 0, 3100*EOK, 1), ("B", 55, 60, 54, 59, 0, 3300*EOK, 1),
                        ("C", 258, 290, 240, 245, 0, 2000*EOK, -5), ("D", 9.5, 10, 9, 9.8, 0, 3500*EOK, 1),
                        ("E", 11.5, 13, 11, 12.5, 0, 1000*EOK, 1)]),
}


def _hist(ticker, end):
    idx = pd.bdate_range(end="2026-10-30", periods=60)
    if ticker == "C":  # 급등주: 20일선 대비 크게 상단 이탈
        close = np.r_[np.full(57, 150.0), [225, 258, 245]]
    else:
        close = np.linspace(80, 120, 60)
    return pd.DataFrame({"시가": close, "고가": close, "저가": close, "종가": close, "거래량": 0}, index=idx)


def _flow(f, t, ticker, detail=True):
    cols = ["금융투자", "보험", "투신", "사모", "은행", "기타금융", "연기금", "기타법인", "개인", "외국인", "기타외국인", "전체"]
    return pd.DataFrame([[10*EOK, 0, 30*EOK, 0, 0, 0, 5*EOK, 0, -100*EOK, 50*EOK, 5*EOK, 0]] * 2, columns=cols)


fake = types.SimpleNamespace(
    get_previous_business_days=lambda fromdate, todate: [pd.Timestamp(d) for d in DAYS],
    get_market_ohlcv_by_ticker=lambda d, market="ALL": DAILY[d],
    get_market_ticker_name=lambda t: f"종목{t}",
    get_market_ohlcv_by_date=lambda s, e, t: _hist(t, e),
    get_market_trading_value_by_date=_flow,
)


def test_screen_two_days():
    assert ind.screen_two_days(DAILY["20261029"], DAILY["20261030"]) == ["B", "A"]
    assert set(ind.screen_two_days(DAILY["20261028"], DAILY["20261029"])) == {"A", "C"}


def test_envelope_states():
    up = pd.Series(np.r_[np.full(57, 150.0), [225, 258, 245]])
    r = ind.analyze_envelope(up)
    assert r["상태"].startswith("상단 이탈 (밴드워킹 3일)")
    down = pd.Series(np.r_[np.full(30, 100.0), [80]])
    assert ind.analyze_envelope(down)["상태"].startswith("하단 이탈")
    pull = pd.Series(np.r_[np.full(25, 100.0), [130, 104, 102]])
    assert ind.analyze_envelope(pull)["상태"].startswith("중심선 눌림목")


def test_full_run(tmp_path, monkeypatch):
    import screener
    monkeypatch.setattr(screener, "_stock", lambda: fake)
    monkeypatch.setattr(screener, "SLEEP", 0)
    df = screener.run("20261030", 3000, str(tmp_path)).set_index("티커")
    assert df.loc["A", "구분"] == "신규 신호 (3일 연속)"
    assert df.loc["B", "구분"] == "신규 신호"
    assert df.loc["C", "구분"] == "3일차 점검"
    assert "D" not in df.index and "E" not in df.index
    assert "비중 조절" in df.loc["C", "경고"] and "과매수 경계" in df.loc["C", "경고"]
    assert df.loc["B", "수급"].startswith("쌍끌이 매수 (기관 내 투신")
    assert (tmp_path / "screen_20261030.csv").exists()
