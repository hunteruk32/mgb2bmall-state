"""2일 연속 대량거래 양봉 스크리너 (KRX 정규장 기준, 1단계).

사용법:
    export KRX_ID=아이디 KRX_PW=비밀번호   # data.krx.co.kr 무료 회원
    python screener.py                    # 가장 최근 완료된 거래일 기준
    python screener.py --date 20261030    # 특정일 기준
    python screener.py --min-value 2000   # 거래대금 기준(억 원) 변경

NXT 데이터는 아직 포함하지 않습니다 (2단계에서 증권사 API로 추가 예정).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

import indicators as ind

KST = timezone(timedelta(hours=9))
SLEEP = 0.3  # KRX 서버 부하 방지


def _stock():
    # pykrx는 import 시점에 KRX_ID/KRX_PW 환경변수로 로그인하므로 지연 import
    if not (os.getenv("KRX_ID") and os.getenv("KRX_PW")):
        sys.exit("KRX_ID, KRX_PW 환경변수를 먼저 설정하세요 (data.krx.co.kr 회원 계정).")
    from pykrx import stock
    return stock


def recent_business_days(stock, base: str, n: int) -> list[str]:
    """base 이하 최근 n개 영업일(YYYYMMDD, 오래된 순)."""
    start = (datetime.strptime(base, "%Y%m%d") - timedelta(days=n * 3 + 10)).strftime("%Y%m%d")
    try:
        days = [d.strftime("%Y%m%d") for d in stock.get_previous_business_days(fromdate=start, todate=base)]
    except Exception:
        days = []
    if len(days) < n:  # 대체: 하루씩 거슬러 올라가며 실제 시세 확인
        days, d = [], datetime.strptime(base, "%Y%m%d")
        while len(days) < n:
            ds = d.strftime("%Y%m%d")
            df = stock.get_market_ohlcv_by_ticker(ds, market="ALL")
            if not df.empty and (df["시가"] > 0).any():
                days.insert(0, ds)
            d -= timedelta(days=1)
            time.sleep(SLEEP)
    return days[-n:]


def default_base_date() -> str:
    now = datetime.now(KST)
    # 정규장 데이터 확정 전(16시 이전)이면 전일 기준
    if now.hour < 16:
        now -= timedelta(days=1)
    return now.strftime("%Y%m%d")


def history_close(stock, ticker: str, end: str, days: int = 90) -> pd.DataFrame:
    start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=days)).strftime("%Y%m%d")
    return stock.get_market_ohlcv_by_date(start, end, ticker)  # 수정주가


def run(base: str, min_value_eok: float, outdir: str) -> pd.DataFrame:
    stock = _stock()
    min_value = min_value_eok * 1e8

    d0, d1, d2 = recent_business_days(stock, base, 3)  # d2 = 기준일
    print(f"기준일 {d2} / 신호구간 {d1}~{d2} / 3일차 점검구간 {d0}~{d1}→{d2}")

    daily = {}
    for d in (d0, d1, d2):
        daily[d] = stock.get_market_ohlcv_by_ticker(d, market="ALL")
        time.sleep(SLEEP)

    new_hits = ind.screen_two_days(daily[d1], daily[d2], min_value)
    prev_hits = ind.screen_two_days(daily[d0], daily[d1], min_value)

    rows = []
    for ticker in dict.fromkeys(new_hits + prev_hits):
        name = stock.get_market_ticker_name(ticker)
        hist = history_close(stock, ticker, d2)
        time.sleep(SLEEP)
        env = ind.analyze_envelope(hist["종가"])

        if ticker in new_hits and ticker in prev_hits:
            kind = "신규 신호 (3일 연속)"
        elif ticker in new_hits:
            kind = "신규 신호"
        else:
            kind = "3일차 점검"
        row = {"구분": kind,
               "티커": ticker, "종목명": name,
               "종가": int(daily[d2].loc[ticker, "종가"]),
               "등락률%": round(float(daily[d2].loc[ticker, "등락률"]), 2),
               f"거래대금{d1[4:]}(억)": round(daily[d1].loc[ticker, "거래대금"] / 1e8),
               f"거래대금{d2[4:]}(억)": round(daily[d2].loc[ticker, "거래대금"] / 1e8)}
        row.update({f"ENV_{k}": v for k, v in env.items()})

        if ticker in new_hits:
            flow = stock.get_market_trading_value_by_date(d1, d2, ticker, detail=True)
            total = daily[d1].loc[ticker, "거래대금"] + daily[d2].loc[ticker, "거래대금"]
            row.update(ind.summarize_flows(flow, total))
            time.sleep(SLEEP)

        if ticker in prev_hits:
            # 신호 2일차(d1) 기준 상단선 대비 이탈률
            env_d1 = ind.analyze_envelope(hist["종가"].loc[:pd.Timestamp(d1)])
            row.update(ind.day3_risk(daily[d0].loc[ticker], daily[d1].loc[ticker],
                                     daily[d2].loc[ticker], env_d1.get("상단대비%")))
        rows.append(row)

    result = pd.DataFrame(rows)
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"screen_{d2}.csv")
    result.to_csv(path, index=False, encoding="utf-8-sig")  # 엑셀 한글 깨짐 방지

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(result.to_string(index=False) if not result.empty else "조건 충족 종목 없음")
    print(f"\n저장: {path}")
    print("※ 거래대금은 KRX 정규장 기준이며 NXT 거래분은 포함되지 않았습니다.")
    return result


def main():
    p = argparse.ArgumentParser(description="2일 연속 대량거래 양봉 스크리너 (KRX)")
    p.add_argument("--date", default=default_base_date(), help="기준일 YYYYMMDD")
    p.add_argument("--min-value", type=float, default=3000, help="일 거래대금 기준 (억 원)")
    p.add_argument("--out", default="output", help="CSV 저장 폴더")
    a = p.parse_args()
    run(a.date, a.min_value, a.out)


if __name__ == "__main__":
    main()
