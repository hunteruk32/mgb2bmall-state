import os
import sys
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backtest  # noqa: E402
import data  # noqa: E402
import indicators  # noqa: E402
from signals import score_at  # noqa: E402

FRGN_HTML = """<table class="type2"><tr>
<td class="tc"><span class="tah p10 gray03">2026.10.08</span></td>
<td class="num"><span class="tah p11">71,000</span></td>
<td class="num"><em class="bu_p bu_pup"><span class="blind">상승</span></em><span class="tah p11 red02">1,200</span></td>
<td class="num"><span class="tah p11 red01">+1.72%</span></td>
<td class="num"><span class="tah p11">12,345,678</span></td>
<td class="num"><span class="tah p11 red01">+512,300</span></td>
<td class="num"><span class="tah p11 nv01">-1,024,500</span></td>
<td class="num"><span class="tah p11">3,000,000,000</span></td>
<td class="num"><span class="tah p11">50.12%</span></td>
</tr></table>"""

SISE_XML = """<?xml version="1.0" encoding="EUC-KR" ?><protocol><chartdata symbol="005930" name="삼성전자">
<item data="20261007|69000|70500|68800|69800|10000000" />
<item data="20261008|70000|71500|69900|71000|12345678" /></chartdata></protocol>"""


def _resp(text):
    r = mock.Mock()
    r.content = text.encode("euc-kr")
    r.raise_for_status = lambda: None
    r.headers = {}
    return r


def test_naver_parsers():
    with mock.patch("data.requests.get", return_value=_resp(SISE_XML)):
        df, name = data.fetch_ohlcv("005930")
    assert name == "삼성전자" and len(df) == 2 and df["close"].iloc[-1] == 71000
    with mock.patch("data.requests.get", side_effect=[_resp(FRGN_HTML), _resp("")]), \
            mock.patch("data.time.sleep"):
        f = data.fetch_flows_naver("005930", pages=2)
    row = f.loc[pd.Timestamp("2026-10-08")]
    assert row.inst == 512300 and row.foreign == -1024500 and row.foreign_ratio == 50.12


def test_signal_and_backtest():
    d = indicators.add_all(data.synthetic(250, seed=3))
    s = score_at(d)
    assert -100 <= s.score <= 100 and s.has_flows and s.reasons
    assert s.stop < s.close < s.target1 < s.target2
    d = backtest.prepare(data.synthetic(250, seed=3))
    trades = backtest.simulate(d, backtest.Params(), "X")
    assert trades and all(t["entry_date"] < t["exit_date"] or t["held"] == 1 for t in trades)
    st = backtest.summarize(trades)
    assert st["n"] == len(trades) and 0 <= st["win"] <= 100


def _bars(highs, lows, opens=None, closes=None, score0=50):
    n = len(highs)
    idx = pd.bdate_range("2026-01-01", periods=n)
    return pd.DataFrame({"open": opens or [100] * n, "high": highs, "low": lows,
                         "close": closes or [100] * n, "atr": [5.0] * n,
                         "score": [score0] + [0] * (n - 1), "mkt_ok": [True] * n}, index=idx)


def test_simulate_stop_and_target_no_split():
    p = backtest.Params(tp_atr=2, sl_atr=2, cost=0, split=False, max_loss=0)
    t = backtest.simulate(_bars([101, 101, 111, 101, 101], [99] * 5), p, "X")
    assert t[0]["reason"] == "익절" and t[0]["exit"] == 110
    t = backtest.simulate(_bars([101] * 5, [99, 85, 99, 99, 99]), p, "X")
    assert t[0]["reason"] == "손절" and t[0]["exit"] == 90


def test_split_take_profit_then_breakeven():
    # 1차 익절(105) 후 본전(100) 이탈 -> 절반 +5%, 절반 0% -> 총 +2.5%
    p = backtest.Params(tp_atr=1, tp2_atr=3, sl_atr=2, cost=0, split=True)
    d = _bars([101, 101, 106, 101, 101], [99, 99, 101, 98, 99],
              closes=[100, 100, 105, 99, 100])
    t = backtest.simulate(d, p, "X")
    assert t[0]["reason"] == "1차익절+본전" and abs(t[0]["ret"] - 2.5) < 1e-9
    # 1차 익절 후 2차 익절(115) -> (5 + 15) / 2 = +10%
    d = _bars([101, 101, 106, 116, 101], [99, 99, 101, 104, 99],
              closes=[100, 100, 105, 110, 100])
    t = backtest.simulate(d, p, "X")
    assert t[0]["reason"] == "2차익절" and abs(t[0]["ret"] - 10) < 1e-9


def test_market_filter_blocks_entry():
    d = _bars([101] * 5, [99] * 5)
    d["mkt_ok"] = False
    assert backtest.simulate(d, backtest.Params(market_filter=True, max_hold=2), "X") == []
    assert backtest.simulate(d, backtest.Params(market_filter=False, max_hold=2), "X")


def test_market_flags():
    import market
    idx = pd.DataFrame({"close": [100.0] * 25 + [97.0]},
                       index=pd.bdate_range("2026-01-01", periods=26))
    f = market.flags(idx)
    assert f["mkt_ok"].iloc[-2] and not f["mkt_ok"].iloc[-1]
    assert "당일" in f["mkt_reason"].iloc[-1] and "20일선" in f["mkt_reason"].iloc[-1]


def test_optimize_picks_profitable():
    ds = {f"D{i}": backtest.prepare(data.synthetic(200, seed=i)) for i in range(3)}
    grid = dict(buy_th=[25], tp_atr=[1.0, 3.0], tp2_atr=[2.0], sl_atr=[2.0], max_hold=[5])
    best, rows, _ = backtest.optimize(ds, min_train=5, grid=grid)
    assert len(rows) == 1  # tp2 <= tp 조합은 제외
    assert best is None or best["train"]["avg"] > 0


def test_without_flows():
    raw = data.synthetic(200).drop(columns=["inst", "foreign"])
    s = score_at(indicators.add_all(raw))
    assert not s.has_flows and s.parts["수급"] == 0


def test_realtime_split_and_market_filter():
    from datetime import datetime
    import realtime
    p = backtest.Params(buy_th=-100, tp_atr=1, tp2_atr=3, sl_atr=2, cost=0)
    base = data.synthetic(150, seed=3)
    px = {"v": float(base["close"].iloc[-1])}

    def loader(code):
        df = base.copy()
        df.iloc[-1, df.columns.get_loc("close")] = px["v"]
        return df, "T"

    t_entry = datetime(2026, 10, 8, 15, 20, tzinfo=realtime.KST)
    quiet = dict(log=lambda *a: None)
    empty = realtime.read_ledger("/nonexistent")
    # 시장 필터에 걸리면 진입 안 함
    lg = realtime.step(["X"], p, loader, t_entry, empty, mkt=(False, "약세"), **quiet)
    assert lg.empty
    lg = realtime.step(["X"], p, loader, t_entry, empty, mkt=(True, ""), **quiet)
    pos = lg.iloc[0]
    # 1차 익절가 도달 -> 절반 익절, 손절가 본전으로
    px["v"] = float(pos.target) + 1
    lg = realtime.step(["X"], p, loader, t_entry, lg, **quiet)
    assert lg.iloc[0].status == "open" and lg.iloc[0].stop == round(pos.entry)
    # 본전 이탈 -> 나머지 청산, 총 수익 플러스
    px["v"] = float(pos.entry) - 1
    lg = realtime.step(["X"], p, loader, t_entry, lg, **quiet)
    assert lg.iloc[0].status == "closed" and lg.iloc[0].reason == "1차익절+본전"
    assert lg.iloc[0].ret > 0


def test_params_roundtrip(tmp_path):
    path = str(tmp_path / "p.json")
    backtest.Params(tp_atr=0.7, split=False).save(path, extra={"split_date": "2026-03-16"})
    q = backtest.Params.load(path)
    assert q.tp_atr == 0.7 and q.split is False and q.market_filter is True


def test_parse_mobile_trend_flexible_keys():
    js = [{"bizdate": "20261008", "foreignerPureBuyQuant": "-1,024,500",
           "organPureBuyQuant": "+512,300", "individualPureBuyQuant": "+512,200",
           "foreignerHoldRatio": "50.12%", "closePrice": "263,000"}]
    r = data.parse_mobile_trend(js)
    assert r[0]["date"] == pd.Timestamp("2026-10-08")
    assert r[0]["foreign"] == -1024500 and r[0]["inst"] == 512300 and r[0]["retail"] == 512200
    assert data.parse_mobile_trend({"result": js})[0]["foreign_ratio"] == 50.12


def test_flows_fallback_chain():
    with mock.patch("data.fetch_flows_naver", side_effect=data.DataError("x")), \
            mock.patch("data.fetch_flows_naver_mobile",
                       return_value=pd.DataFrame({"inst": [1.0]})) as m:
        assert len(data.fetch_flows("005930")) == 1 and m.called


def test_clean_ohlcv_zero_open():
    df = pd.DataFrame({"open": [0.0, 100], "high": [0.0, 105], "low": [0.0, 95],
                       "close": [101.0, 102], "volume": [0.0, 10]},
                      index=pd.bdate_range("2026-01-01", periods=2))
    c = data.clean_ohlcv(df)
    assert (c.iloc[0][["open", "high", "low"]] == 101).all()
    assert c.iloc[1].open == 100


def test_max_loss_caps_stop():
    # ATR 5, 손절 2ATR = -10% 이지만 최대손실 5% 로 제한 -> 95 에서 손절
    p = backtest.Params(tp_atr=2, sl_atr=2, cost=0, split=False, max_loss=0.05)
    t = backtest.simulate(_bars([101] * 5, [99, 85, 99, 99, 99]), p, "X")
    assert t[0]["reason"] == "손절" and t[0]["exit"] == 95


def test_pullback_signal():
    n = 130
    idx = pd.bdate_range("2026-01-01", periods=n)
    d = pd.DataFrame({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
                      "atr": 2.0, "ma120": 90.0, "ma60": 95.0, "rsi": 50.0,
                      "mkt_ok": True}, index=idx)
    d.loc[idx[-3], "rsi"] = 30.0   # 과매도
    d.loc[idx[-2], "rsi"] = 33.0   # 반등
    p = backtest.Params(strategy="pullback", trend_ma=120, rsi_th=35, rsi_confirm=True)
    ent, exs, label = backtest.signals(d, p)
    assert not ent[-3] and ent[-2] and not ent[-1]   # 반등 확인된 날만
    p.rsi_confirm = False
    ent, _, _ = backtest.signals(d, p)
    assert ent[-3] and ent[-2]
    d["ma120"] = 110.0                                # 장기 추세 아래면 매수 안 함
    assert not backtest.signals(d, p)[0].any()
    assert label == "RSI회복" and not exs[0]          # RSI 50 < 청산선 60


def test_universe_filters_and_parses():
    assert data._keep("005930", "삼성전자")
    assert not data._keep("005935", "삼성전자우")          # 우선주
    assert not data._keep("123450", "하나스팩10호")        # 스팩
    js = {"stocks": [{"itemCode": "005930", "stockName": "삼성전자", "stockEndType": "stock"},
                     {"itemCode": "069500", "stockName": "KODEX 200", "stockEndType": "etf"},
                     {"itemCode": "000660", "stockName": "SK하이닉스", "stockEndType": "stock"}]}
    r = mock.Mock()
    r.json = lambda: js
    r.raise_for_status = lambda: None
    with mock.patch("data.requests.get", side_effect=[r] + [mock.Mock(json=lambda: {"stocks": []},
                    raise_for_status=lambda: None)] * 5), mock.patch("data.time.sleep"):
        got = data.fetch_universe("KOSPI", 2)
    assert got == [("005930", "삼성전자"), ("000660", "SK하이닉스")]


def test_walk_forward_runs_and_has_baseline():
    ds = {f"D{i}": backtest.prepare(data.synthetic(400, seed=i)) for i in range(4)}
    grid = dict(buy_th=[25], tp_atr=[1.5], tp2_atr=[3.0], sl_atr=[2.0], max_hold=[5],
                max_loss=[0.07])
    folds, oos, final, n, base = backtest.walk_forward(ds, "score", n_folds=2, min_train=5,
                                                       grid=grid)
    assert n == 1 and len(folds) == 2
    assert base["n"] >= oos["n"]   # 아무날 매수가 거래 수는 더 많아야 함


def test_research_report_runs(capsys):
    import research
    ds = {f"D{i}": backtest.prepare(data.synthetic(300, seed=i)) for i in range(3)}
    r = research.report(ds, horizon=5, min_n=5)
    assert len(r) > 10 and "꾸준함" in capsys.readouterr().out
