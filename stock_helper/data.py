"""시세(OHLCV) 및 투자자별 수급 데이터 수집.

기본 소스: 네이버 금융 (로그인 불필요)
  - 일봉:   fchart.stock.naver.com (XML)
  - 수급:   finance.naver.com/item/frgn.naver (기관/외국인 일별 순매매량)
보조 소스: pykrx (설치되어 있고 KRX 접속이 가능한 경우, 개인 순매수까지 제공)
"""
from __future__ import annotations

import os
import re
import time

import numpy as np
import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Referer": "https://finance.naver.com/"}
TIMEOUT = 10


class DataError(RuntimeError):
    pass


# ---------------------------------------------------------------- 시세(일봉)
def fetch_ohlcv(code: str, count: int = 300) -> tuple[pd.DataFrame, str]:
    """일봉 OHLCV와 종목명을 반환. index=날짜, columns=open/high/low/close/volume"""
    url = ("https://fchart.stock.naver.com/sise.nhn"
           f"?symbol={code}&timeframe=day&count={count}&requestType=0")
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        text = r.content.decode("euc-kr", errors="replace")
        rows = re.findall(r'<item data="([^"]+)"', text)
        if not rows:
            raise DataError("네이버 일봉 응답이 비어 있습니다")
        m = re.search(r'name="([^"]*)"', text)
        name = m.group(1) if m else code
        recs = []
        for row in rows:
            d, o, h, l, c, v = row.split("|")[:6]
            recs.append((pd.Timestamp(d), float(o), float(h), float(l), float(c), float(v)))
        df = pd.DataFrame(recs, columns=["date", "open", "high", "low", "close", "volume"])
        df = df.set_index("date").sort_index()
        df = df[df["close"] > 0]
        return df, name
    except (requests.RequestException, DataError) as e:
        naver_err = e

    # 보조: pykrx
    try:
        from pykrx import stock
        end = pd.Timestamp.today()
        start = end - pd.Timedelta(days=int(count * 1.6))
        df = stock.get_market_ohlcv(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), code)
        df = df.rename(columns={"시가": "open", "고가": "high", "저가": "low",
                                "종가": "close", "거래량": "volume"})
        df = df[["open", "high", "low", "close", "volume"]].astype(float)
        df.index.name = "date"
        name = stock.get_market_ticker_name(code)
        return df.tail(count), name
    except Exception as e:  # noqa: BLE001
        raise DataError(f"시세 조회 실패 ({code}): naver={naver_err!r}, pykrx={e!r}") from e


# ---------------------------------------------------------------- 수급
def _clean(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _num(s: str) -> float:
    m = re.search(r"[-+]?[\d,]+(?:\.\d+)?", s)
    return float(m.group(0).replace(",", "")) if m else np.nan


def _decode(r: requests.Response) -> str:
    """응답 인코딩 자동 판별 (네이버는 페이지에 따라 euc-kr / utf-8 혼재)."""
    ctype = r.headers.get("Content-Type", "").lower()
    head = r.content[:2000].lower()
    if "utf-8" in ctype or b'charset="utf-8"' in head or b"charset=utf-8" in head:
        return r.content.decode("utf-8", errors="replace")
    return r.content.decode("euc-kr", errors="replace")


def parse_frgn_html(html: str) -> list[dict]:
    """finance.naver.com/item/frgn.naver 표 파싱.
    행 구성: 날짜, 종가, 전일비, 등락률, 거래량, 기관, 외국인, 보유주수, 보유율"""
    recs = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 7:
            continue
        date_txt = _clean(tds[0])
        if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", date_txt):
            continue
        recs.append({
            "date": pd.Timestamp(date_txt.replace(".", "-")),
            "inst": _num(_clean(tds[5])),
            "foreign": _num(_clean(tds[6])),
            "foreign_ratio": _num(_clean(tds[8])) if len(tds) > 8 else np.nan,
        })
    return recs


def fetch_flows_naver(code: str, pages: int = 8) -> pd.DataFrame:
    """기관/외국인 일별 순매매량(주), 외국인 보유율(%). 한 페이지 = 약 20거래일."""
    recs = []
    for page in range(1, pages + 1):
        url = f"https://finance.naver.com/item/frgn.naver?code={code}&page={page}"
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        found = parse_frgn_html(_decode(r))
        if not found:
            break
        recs += found
        time.sleep(0.15)
    if not recs:
        raise DataError("네이버 수급 데이터가 비어 있습니다")
    df = pd.DataFrame(recs).drop_duplicates("date").set_index("date").sort_index()
    return df


MOBILE_UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                           "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
             "Referer": "https://m.stock.naver.com/"}


def _find_key(row: dict, *must: str) -> str | None:
    for k in row:
        kl = k.lower()
        if all(m in kl for m in must):
            return k
    return None


def parse_mobile_trend(js) -> list[dict]:
    """m.stock.naver.com /api/stock/{code}/trend JSON 파싱 (키 이름을 유연하게 탐색)."""
    rows = js if isinstance(js, list) else next(
        (v for v in (js or {}).values() if isinstance(v, list)), [])
    recs = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        kd = _find_key(row, "bizdate") or _find_key(row, "date")
        kf = _find_key(row, "foreign", "pure") or _find_key(row, "foreign", "net")
        ki = _find_key(row, "organ", "pure") or _find_key(row, "institution", "net")
        kp = _find_key(row, "individual", "pure") or _find_key(row, "individual", "net")
        kr = _find_key(row, "foreign", "ratio")
        if not (kd and kf and ki):
            continue
        d = re.sub(r"\D", "", str(row[kd]))[:8]
        if len(d) != 8:
            continue
        rec = {"date": pd.Timestamp(d), "inst": _num(str(row[ki])),
               "foreign": _num(str(row[kf]))}
        if kp:
            rec["retail"] = _num(str(row[kp]))
        if kr:
            rec["foreign_ratio"] = _num(str(row[kr]))
        recs.append(rec)
    return recs


def fetch_flows_naver_mobile(code: str, days: int = 160) -> pd.DataFrame:
    """네이버 모바일 증권 투자자별 매매동향 (외국인/기관/개인 순매수 수량)."""
    recs, bizdate = [], None
    for _ in range(max(1, int(np.ceil(days / 60)))):
        url = f"https://m.stock.naver.com/api/stock/{code}/trend?pageSize=60"
        if bizdate:
            url += f"&bizdate={bizdate}"
        r = requests.get(url, headers=MOBILE_UA, timeout=TIMEOUT)
        r.raise_for_status()
        found = parse_mobile_trend(r.json())
        new = [x for x in found if not recs or x["date"] < min(y["date"] for y in recs)]
        if not new:
            break
        recs += new
        bizdate = (min(x["date"] for x in new) - pd.Timedelta(days=1)).strftime("%Y%m%d")
        time.sleep(0.15)
    if not recs:
        raise DataError("네이버 모바일 수급 데이터가 비어 있습니다")
    return pd.DataFrame(recs).drop_duplicates("date").set_index("date").sort_index()


def fetch_flows_pykrx(code: str, days: int = 160) -> pd.DataFrame:
    """pykrx 투자자별 순매수 '거래량'(주). 개인 포함."""
    from pykrx import stock
    end = pd.Timestamp.today()
    start = end - pd.Timedelta(days=int(days * 1.6))
    df = stock.get_market_trading_volume_by_date(
        start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), code)
    out = pd.DataFrame(index=df.index)
    out["inst"] = df["기관합계"]
    out["foreign"] = df["외국인합계"]
    out["retail"] = df["개인"]
    out.index.name = "date"
    return out.astype(float)


def fetch_flows(code: str, days: int = 160) -> pd.DataFrame:
    pages = max(1, int(np.ceil(days / 20)))
    errors = []
    for label, fn in (("naver", lambda: fetch_flows_naver(code, pages=pages)),
                      ("naver_mobile", lambda: fetch_flows_naver_mobile(code, days=days)),
                      ("pykrx", lambda: fetch_flows_pykrx(code, days=days))):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            errors.append(f"{label}={e!r}")
    raise DataError(f"수급 조회 실패 ({code}): " + ", ".join(errors))


CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")


def load(code: str, days: int = 250, cache_hours: float = 0) -> tuple[pd.DataFrame, str]:
    """시세 + 수급을 합친 DataFrame. 수급 조회 실패 시 시세만 반환(수급 컬럼 NaN).
    cache_hours > 0 이면 cache/ 폴더의 CSV를 해당 시간 동안 재사용."""
    path = os.path.join(CACHE_DIR, f"{code}_{days}.csv")
    if cache_hours > 0 and os.path.exists(path) and \
            time.time() - os.path.getmtime(path) < cache_hours * 3600:
        df = pd.read_csv(path, index_col="date", parse_dates=["date"])
        name = str(df.pop("name").iloc[-1])
        return df, name
    df, name = _load(code, days)
    if cache_hours > 0:
        os.makedirs(CACHE_DIR, exist_ok=True)
        df.assign(name=name).to_csv(path)
    return df, name


def refresh_price(df: pd.DataFrame, code: str) -> pd.DataFrame:
    """캐시된 데이터에 최근 시세(장중이면 오늘 진행 중인 봉 포함)를 덮어씀."""
    recent, _ = fetch_ohlcv(code, count=5)
    out = df.copy()
    for col in recent.columns:
        out.loc[recent.index, col] = recent[col]  # 새 날짜는 행이 추가됨
    return out.sort_index()


def _load(code: str, days: int) -> tuple[pd.DataFrame, str]:
    price, name = fetch_ohlcv(code, count=days)
    try:
        flows = fetch_flows(code, days=days)
        df = price.join(flows, how="left")
    except DataError as e:
        print(f"[경고] {e} -> 수급 점수는 제외하고 분석합니다.")
        df = price.copy()
        df["inst"] = np.nan
        df["foreign"] = np.nan
    return df, name


# ---------------------------------------------------------------- 오프라인 데모
def synthetic(days: int = 250, seed: int = 7, trend: float = 0.0008) -> pd.DataFrame:
    """네트워크 없이 기능을 시험해 볼 수 있는 가상 데이터."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    ret = rng.normal(trend, 0.02, days)
    close = 50000 * np.exp(np.cumsum(ret))
    open_ = close * (1 + rng.normal(0, 0.006, days))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.008, days)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.008, days)))
    vol = rng.lognormal(13, 0.4, days) * (1 + 8 * np.abs(ret))
    # 수급이 가격을 약간 선행하도록 생성
    lead = np.roll(ret, -1)
    foreign = (lead * 4e6 + rng.normal(0, 3e4, days)).round()
    inst = (lead * 3e6 + rng.normal(0, 3e4, days)).round()
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": vol.round(), "inst": inst, "foreign": foreign},
                        index=pd.DatetimeIndex(idx, name="date"))


# ---------------------------------------------------------------- 지수 (시장 필터용)
INDEX_PYKRX = {"KOSPI": "1001", "KOSDAQ": "2001"}


def fetch_index(name: str = "KOSPI", count: int = 300) -> pd.DataFrame:
    """코스피/코스닥 지수 일봉 (close 포함). 네이버 -> pykrx 순."""
    try:
        df, _ = fetch_ohlcv(name, count=count)
        return df
    except DataError:
        pass
    from pykrx import stock
    end = pd.Timestamp.today()
    start = end - pd.Timedelta(days=int(count * 1.6))
    df = stock.get_index_ohlcv(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"),
                               INDEX_PYKRX[name])
    df = df.rename(columns={"시가": "open", "고가": "high", "저가": "low",
                            "종가": "close", "거래량": "volume"})
    df.index.name = "date"
    return df[["open", "high", "low", "close", "volume"]].astype(float).tail(count)


def load_index(name: str = "KOSPI", count: int = 500, cache_hours: float = 0,
               demo: bool = False) -> pd.DataFrame:
    if demo:  # 길이와 무관하게 같은 가상 지수가 나오도록 고정 길이로 만든 뒤 자름
        return synthetic(max(count, 1000), seed=999, trend=0.0003).tail(count)
    path = os.path.join(CACHE_DIR, f"INDEX_{name}_{count}.csv")
    if cache_hours > 0 and os.path.exists(path) and \
            time.time() - os.path.getmtime(path) < cache_hours * 3600:
        return pd.read_csv(path, index_col="date", parse_dates=["date"])
    df = fetch_index(name, count)
    if cache_hours > 0:
        os.makedirs(CACHE_DIR, exist_ok=True)
        df.to_csv(path)
    return df
