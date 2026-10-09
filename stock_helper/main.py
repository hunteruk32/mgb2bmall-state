"""나만의 한국 주식 단기투자 도우미 (CLI)

사용 예)
  python main.py analyze 005930            # 종목 분석 + 매수/매도 의견
  python main.py analyze 005930 --chart    # 차트 PNG 저장
  python main.py scan watchlist.txt        # 관심종목 일괄 점수 랭킹
  python main.py backtest 005930           # 점수 전략 과거 성과 검증
  python main.py analyze DEMO              # 네트워크 없이 가상 데이터로 시험
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backtest  # noqa: E402
import data  # noqa: E402
import indicators  # noqa: E402
from signals import score_at, score_series  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DISCLAIMER = ("※ 본 결과는 기술적 지표·수급 기반의 참고용 정보이며 투자 권유가 아닙니다. "
              "최종 판단과 책임은 본인에게 있습니다.")


def load(code: str, days: int):
    if code.upper().startswith("DEMO"):
        seed = int(code[4:] or 7)
        return data.synthetic(days, seed=seed), f"가상종목{seed}"
    return data.load(code, days)


def fmt(v: float) -> str:
    return f"{v:,.0f}"


def cmd_analyze(a):
    raw, name = load(a.code, a.days)
    d = indicators.add_all(raw)
    s = score_at(d)
    r = d.iloc[-1]
    bar = "=" * 64
    print(bar)
    print(f" {name} ({a.code})   기준일 {s.date.date()}   종가 {fmt(s.close)}원 "
          f"({r.ret1 * 100:+.2f}%)")
    print(bar)
    print(f" 종합 점수 : {s.score:+.1f} / 100      의견 : 【 {s.opinion} 】")
    print(" 세부 점수 : " + "  ".join(f"{k} {v:+g}" for k, v in s.parts.items()))
    print("-" * 64)
    print(f" RSI {r.rsi:.1f} | MACD hist {r.macd_hist:+.1f} | MFI {r.mfi:.0f} | "
          f"거래량비 {r.vol_ratio:.2f}배 | ATR {fmt(r.atr)}")
    print(f" MA5 {fmt(r.ma5)} | MA20 {fmt(r.ma20)} | MA60 {fmt(r.ma60)} | "
          f"BB {fmt(r.bb_dn)}~{fmt(r.bb_up)}")
    if s.has_flows:
        print(f" 외국인 5일 {r.foreign_5:+,.0f}주 / 20일 {r.foreign_20:+,.0f}주 "
              f"(연속 {int(r.foreign_streak):+d}일)")
        print(f" 기관   5일 {r.inst_5:+,.0f}주 / 20일 {r.inst_20:+,.0f}주 "
              f"(연속 {int(r.inst_streak):+d}일)")
    print("-" * 64)
    print(" [판단 근거]")
    for x in s.reasons:
        print("  " + x)
    if s.warnings:
        print(" [주의]")
        for x in s.warnings:
            print("  ⚠ " + x)
    if s.exit_alerts:
        print(" [보유자 매도 경고]")
        for x in s.exit_alerts:
            print("  ⛔ " + x)
    print("-" * 64)
    risk = s.close - s.stop
    print(" [매매 가이드] (ATR 기반)")
    if s.score < 25:
        print(f"  신규 매수 비추천. 보유 중이라면 손절 기준 {fmt(s.stop)}원 "
              f"({(s.stop / s.close - 1) * 100:+.1f}%) 이탈 시 정리")
    else:
        print(f"  진입 참고가 : {fmt(s.close)}원 (다음날 시가~종가 부근 분할)")
        _plan(s, risk)
    print(" [최근 5일 점수 추이]")
    print("  " + "  ".join(f"{k.strftime('%m/%d')}:{v:+.0f}"
                           for k, v in score_series(d, len(d) - 5).items()))
    print(bar)
    print(DISCLAIMER)
    if a.chart:
        path = save_chart(d, name, a.code)
        print(f"차트 저장: {path}")


def _plan(s, risk):
    print(f"  손절가      : {fmt(s.stop)}원 ({(s.stop / s.close - 1) * 100:+.1f}%)")
    print(f"  1차 목표가  : {fmt(s.target1)}원 ({(s.target1 / s.close - 1) * 100:+.1f}%) "
          f"→ 절반 익절")
    print(f"  2차 목표가  : {fmt(s.target2)}원 ({(s.target2 / s.close - 1) * 100:+.1f}%)")
    if risk > 0:
        print(f"  손익비      : 1 : {(s.target2 - s.close) / risk:.1f}")


def cmd_scan(a):
    if os.path.exists(a.watchlist):
        with open(a.watchlist, encoding="utf-8") as f:
            codes = [ln.split("#")[0].strip() for ln in f]
    else:
        codes = a.watchlist.split(",")
    codes = [c for c in codes if c]
    rows = []
    for code in codes:
        try:
            raw, name = load(code, a.days)
            d = indicators.add_all(raw)
            s = score_at(d)
            r = d.iloc[-1]
            rows.append(dict(코드=code, 종목=name, 종가=fmt(s.close),
                             등락=f"{r.ret1 * 100:+.1f}%", 점수=s.score, 의견=s.opinion,
                             추세=s.parts["추세"], 모멘텀=s.parts["모멘텀"],
                             거래량=s.parts["거래량"], 수급=s.parts["수급"],
                             RSI=round(r.rsi), 경고=len(s.exit_alerts) + len(s.warnings)))
        except Exception as e:  # noqa: BLE001
            print(f"[실패] {code}: {e}")
    if not rows:
        return
    df = pd.DataFrame(rows).sort_values("점수", ascending=False)
    with pd.option_context("display.unicode.east_asian_width", True,
                           "display.width", 200, "display.max_columns", 20):
        print(df.to_string(index=False))
    print(DISCLAIMER)


def cmd_backtest(a):
    raw, name = load(a.code, a.days)
    d = indicators.add_all(raw)
    res = backtest.run(d, buy_th=a.buy, exit_th=a.exit, max_hold=a.hold)
    print(f"{name} ({a.code}) 백테스트  {d.index[60].date()} ~ {d.index[-1].date()}")
    print(f"  조건: 점수 ≥ {a.buy} 매수 / 점수 ≤ {a.exit} 또는 {a.hold}일 경과 시 매도, "
          f"ATR 손절·목표가, 왕복비용 0.25%")
    if res.trades.empty:
        print("  거래 없음")
        return
    with pd.option_context("display.unicode.east_asian_width", True, "display.width", 200):
        print(res.trades.to_string(index=False))
    print(f"  거래 {len(res.trades)}회 | 승률 {res.win_rate:.0f}% | 평균 {res.avg_return:+.2f}% | "
          f"누적 {res.total_return:+.1f}% | MDD {res.mdd:.1f}% | 단순보유 {res.buy_hold:+.1f}%")


def save_chart(d: pd.DataFrame, name: str, code: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    have = {f.name for f in font_manager.fontManager.ttflist}
    for font in ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"):
        if font in have:
            plt.rcParams["font.family"] = font
            break
    plt.rcParams["axes.unicode_minus"] = False
    t = d.tail(120)
    sc = score_series(d, max(60, len(d) - 120))
    fig, ax = plt.subplots(4, 1, figsize=(12, 11), sharex=True,
                           gridspec_kw={"height_ratios": [3, 1, 1, 1]})
    ax[0].plot(t.index, t.close, label="종가", color="black", lw=1.2)
    for n, c in ((5, "tab:orange"), (20, "tab:blue"), (60, "tab:green")):
        ax[0].plot(t.index, t[f"ma{n}"], label=f"MA{n}", color=c, lw=0.9)
    ax[0].fill_between(t.index, t.bb_dn, t.bb_up, color="gray", alpha=0.12, label="볼린저")
    ax[0].set_title(f"{name} ({code})")
    ax[0].legend(loc="upper left", fontsize=8)
    ax[1].bar(t.index, t.foreign.fillna(0), color="tab:red", alpha=0.6, label="외국인")
    ax[1].bar(t.index, t.inst.fillna(0), color="tab:blue", alpha=0.6, label="기관")
    ax[1].axhline(0, color="gray", lw=0.6)
    ax[1].legend(loc="upper left", fontsize=8)
    ax[1].set_ylabel("순매수(주)")
    ax[2].plot(t.index, t.rsi, color="purple", lw=1)
    ax[2].axhline(70, ls="--", color="red", lw=0.6)
    ax[2].axhline(30, ls="--", color="blue", lw=0.6)
    ax[2].set_ylabel("RSI")
    s = sc.reindex(t.index)
    ax[3].bar(s.index, s.values, color=["tab:red" if v > 0 else "tab:blue" for v in s.fillna(0)])
    ax[3].axhline(25, ls="--", color="red", lw=0.6)
    ax[3].axhline(-25, ls="--", color="blue", lw=0.6)
    ax[3].set_ylabel("종합점수")
    fig.tight_layout()
    path = os.path.join(os.getcwd(), f"chart_{code}.png")
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def main(argv=None):
    p = argparse.ArgumentParser(description="한국 주식 단기투자 도우미")
    p.add_argument("--days", type=int, default=250, help="조회 거래일 수 (기본 250)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("analyze", help="종목 분석")
    s1.add_argument("code", help="종목코드 6자리 (예: 005930) 또는 DEMO")
    s1.add_argument("--chart", action="store_true", help="차트 PNG 저장")
    s2 = sub.add_parser("scan", help="관심종목 랭킹")
    s2.add_argument("watchlist", help="종목코드 파일 경로 또는 쉼표 구분 코드")
    s3 = sub.add_parser("backtest", help="점수 전략 백테스트")
    s3.add_argument("code")
    s3.add_argument("--buy", type=float, default=25, help="매수 점수 기준 (기본 25)")
    s3.add_argument("--exit", type=float, default=-10, help="청산 점수 기준 (기본 -10)")
    s3.add_argument("--hold", type=int, default=10, help="최대 보유일 (기본 10)")
    a = p.parse_args(argv)
    {"analyze": cmd_analyze, "scan": cmd_scan, "backtest": cmd_backtest}[a.cmd](a)


if __name__ == "__main__":
    main()
