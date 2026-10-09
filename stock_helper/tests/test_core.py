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
    res = backtest.run(d)
    assert res.win_rate >= 0


def test_without_flows():
    raw = data.synthetic(200).drop(columns=["inst", "foreign"])
    s = score_at(indicators.add_all(raw))
    assert not s.has_flows and s.parts["수급"] == 0
