"""데이터 소스 진단: 각 소스의 실제 응답을 diag_report.txt 로 저장.

사용: python diag.py 005930
결과 파일(diag_report.txt)을 개발자에게 보내면 파싱 문제를 정확히 고칠 수 있습니다.
"""
from __future__ import annotations

import os
import sys
import traceback

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def probe(out, label, url, headers, parse):
    out.append(f"\n===== {label} =====\nURL: {url}")
    try:
        r = requests.get(url, headers=headers, timeout=10)
        body = data._decode(r)
        out.append(f"status={r.status_code} type={r.headers.get('Content-Type')} "
                   f"len={len(r.content)} final_url={r.url}")
        try:
            n = len(parse(r, body))
            out.append(f"파싱 결과: {n}행")
        except Exception as e:  # noqa: BLE001
            n = 0
            out.append(f"파싱 오류: {e!r}")
        # 수급 표 근처를 우선 발췌
        i = max(body.find("외국인"), 0)
        out.append("--- 응답 발췌 (앞 1500자) ---\n" + body[:1500])
        if i > 1500:
            out.append("--- '외국인' 주변 3000자 ---\n" + body[max(0, i - 500):i + 2500])
        return n
    except Exception:  # noqa: BLE001
        out.append("요청 실패:\n" + traceback.format_exc())
        return 0


def main(code: str = "005930"):
    out = [f"진단 대상: {code}"]
    res = {
        "시세(fchart)": probe(out, "시세 fchart",
                            f"https://fchart.stock.naver.com/sise.nhn?symbol={code}"
                            "&timeframe=day&count=5&requestType=0",
                            data.UA, lambda r, b: __import__("re").findall(r"<item data=", b)),
        "수급(PC 웹)": probe(out, "수급 finance.naver.com frgn",
                           f"https://finance.naver.com/item/frgn.naver?code={code}&page=1",
                           data.UA, lambda r, b: data.parse_frgn_html(b)),
        "수급(모바일)": probe(out, "수급 m.stock.naver.com trend",
                            f"https://m.stock.naver.com/api/stock/{code}/trend?pageSize=10",
                            data.MOBILE_UA, lambda r, b: data.parse_mobile_trend(r.json())),
    }
    try:
        f = data.fetch_flows_pykrx(code, days=20)
        res["수급(pykrx)"] = len(f)
        out.append(f"\n===== pykrx =====\n{len(f)}행\n{f.tail(3)}")
    except Exception as e:  # noqa: BLE001
        res["수급(pykrx)"] = 0
        out.append(f"\n===== pykrx =====\n실패: {e!r}")
    path = os.path.join(os.getcwd(), "diag_report.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("[진단 요약]")
    for k, v in res.items():
        print(f"  {k:<12} {'✅ ' + str(v) + '행' if v else '❌ 실패'}")
    print(f"\n상세 내용 저장: {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "005930")
