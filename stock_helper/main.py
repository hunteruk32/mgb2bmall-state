"""나만의 한국 주식 단기투자 도우미 (CLI)

사용 예)
  python main.py analyze 005930            # 종목 분석 + 매수/매도 의견
  python main.py analyze 005930 --chart    # 차트 PNG 저장
  python main.py scan watchlist.txt        # 관심종목 일괄 점수 랭킹
  python main.py optimize universe.txt     # 과거 데이터로 승률 최적 설정 찾기 (100회+)
  python main.py backtest 005930,000660    # 저장된 설정으로 백테스트
  python main.py monitor watchlist.txt     # 장중 실시간 감시 + 모의매매
  python main.py paper                     # 모의매매 승률 (100회 목표)
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
import market  # noqa: E402
import realtime  # noqa: E402
from signals import score_at, score_series  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DISCLAIMER = ("※ 본 결과는 기술적 지표·수급 기반의 참고용 정보이며 투자 권유가 아닙니다. "
              "최종 판단과 책임은 본인에게 있습니다.")


def load(code: str, days: int, cache_hours: float = 0):
    if code.upper().startswith("DEMO"):
        seed = int(code[4:] or 7)
        return data.synthetic(days, seed=seed), f"가상종목{seed}"
    return data.load(code, days, cache_hours=cache_hours)


def market_flags(codes: list[str], days: int, index: str = "KOSPI"):
    """시장 필터(B)용 지수 플래그. 실패 시 None (필터 없이 진행)."""
    demo = all(c.upper().startswith("DEMO") for c in codes)
    try:
        idx = data.load_index(index, days + 30, cache_hours=1, demo=demo)
        return market.flags(idx, "코스피" if index == "KOSPI" else "코스닥")
    except Exception as e:  # noqa: BLE001
        print(f"[경고] {index} 지수 조회 실패 -> 시장 필터 없이 진행: {e}")
        return None


def fmt(v: float) -> str:
    return f"{v:,.0f}"


def cmd_analyze(a):
    raw, name = load(a.code, a.days)
    d = indicators.add_all(raw)
    s = score_at(d)
    r = d.iloc[-1]
    p = backtest.Params.load()
    mk = market_flags([a.code], a.days) if p.market_filter else None
    mkt_ok, mkt_msg = market.status(mk) if mk is not None else (True, "필터 꺼짐/정보 없음")
    bar = "=" * 64
    print(bar)
    print(f" {name} ({a.code})   기준일 {s.date.date()}   종가 {fmt(s.close)}원 "
          f"({r.ret1 * 100:+.2f}%)")
    print(bar)
    print(f" 종합 점수 : {s.score:+.1f} / 100      의견 : 【 {s.opinion} 】")
    print(" 세부 점수 : " + "  ".join(f"{k} {v:+g}" for k, v in s.parts.items()))
    print(f" 시장 필터 : {'✅ 매수 가능' if mkt_ok else '⛔ 신규 매수 금지'} ({mkt_msg})")
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
    print(f" [매매 가이드] (저장된 설정: 매수≥{p.buy_th:g}, 손절 {p.sl_atr:g}ATR, "
          f"익절 {p.tp_atr:g}/{p.tp2_atr:g}ATR, 최대 {p.max_hold}일)")
    stop = s.close - p.sl_atr * r.atr
    if s.score < p.buy_th:
        print(f"  점수 {s.score:+.0f} < 기준 {p.buy_th:g}: 신규 매수 안 함. "
              f"보유 중이라면 손절 기준 {fmt(stop)}원 ({(stop / s.close - 1) * 100:+.1f}%)")
    elif not mkt_ok:
        print(f"  점수는 매수 기준 이상이지만 시장 필터({mkt_msg})로 신규 매수 보류")
    else:
        print(f"  진입 참고가 : {fmt(s.close)}원 (다음날 시가 부근)")
        _plan(s.close, r.atr, p)
    print(" [최근 5일 점수 추이]")
    print("  " + "  ".join(f"{k.strftime('%m/%d')}:{v:+.0f}"
                           for k, v in score_series(d, len(d) - 5).items()))
    print(bar)
    print(DISCLAIMER)
    if a.chart:
        path = save_chart(d, name, a.code)
        print(f"차트 저장: {path}")


def _plan(close: float, atr: float, p):
    stop, t1, t2 = close - p.sl_atr * atr, close + p.tp_atr * atr, close + p.tp2_atr * atr
    pct = lambda v: f"{(v / close - 1) * 100:+.1f}%"  # noqa: E731
    print(f"  손절가      : {fmt(stop)}원 ({pct(stop)})")
    if p.split:
        print(f"  1차 익절    : {fmt(t1)}원 ({pct(t1)}) → 절반 매도 후 남은 절반 손절가를 "
              f"본전 {fmt(close * (1 + p.cost))}원으로 올림")
        print(f"  2차 익절    : {fmt(t2)}원 ({pct(t2)}) → 나머지 매도")
    else:
        print(f"  익절가      : {fmt(t1)}원 ({pct(t1)})")
    print(f"  그 외 청산  : 점수 ≤ {p.exit_th:g} 또는 {p.max_hold}일 경과 시 다음날 시가")


def cmd_scan(a):
    codes = read_codes(a.watchlist)
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


def read_codes(arg: str) -> list[str]:
    if os.path.exists(arg):
        with open(arg, encoding="utf-8") as f:
            codes = [ln.split("#")[0].strip() for ln in f]
    else:
        codes = arg.split(",")
    return [c for c in codes if c]


def _stat_line(st: dict) -> str:
    if not st["n"]:
        return "거래 없음"
    return (f"{st['n']:>4}회 | 승률 {st['win']:5.1f}% | 평균 {st['avg']:+.2f}% | "
            f"평균이익 {st['avg_win']:+.2f}% / 평균손실 {st['avg_loss']:+.2f}% | "
            f"PF {st['pf']:.2f} | 최악 {st['worst']:+.1f}% | 최대연속손실 {st['max_losing']}")


def cmd_backtest(a):
    p = backtest.Params.load()
    for k in ("buy_th", "exit_th", "tp_atr", "tp2_atr", "sl_atr", "max_hold"):
        if getattr(a, k) is not None:
            setattr(p, k, getattr(a, k))
    if a.no_market:
        p.market_filter = False
    if a.no_split:
        p.split = False
    codes = read_codes(a.codes)
    mk = market_flags(codes, a.days)
    trades = []
    for code in codes:
        raw, name = load(code, a.days, cache_hours=12)
        trades += backtest.simulate(backtest.prepare(raw, mk), p, code)
    print(f"백테스트 {len(codes)}종목 | 설정 {p}")
    t = pd.DataFrame(trades)
    if not t.empty and a.show:
        with pd.option_context("display.width", 200):
            print(t.assign(ret=t.ret.round(2)).to_string(index=False))
    print("  " + _stat_line(backtest.summarize(t)))


def cmd_optimize(a):
    codes = read_codes(a.codes)
    mk = market_flags(codes, a.days)
    if mk is not None:
        print(f"  시장 필터: 기간 중 {(~mk.mkt_ok).mean() * 100:.0f}%의 날이 신규 매수 금지")
    datasets = {}
    for n, code in enumerate(codes, 1):
        try:
            raw, name = load(code, a.days, cache_hours=12)
            datasets[code] = backtest.prepare(raw, mk)
            print(f"  [{n}/{len(codes)}] {name}({code}) {len(raw)}일 준비 완료")
        except Exception as e:  # noqa: BLE001
            print(f"  [{n}/{len(codes)}] {code} 실패: {e}")
    if not datasets:
        return
    best, rows, cut = backtest.optimize(datasets, target_win=a.target, min_train=a.min_train)
    print(f"\n조합 {len(rows)}개 시험 | 학습: ~{cut.date()} 이전 / 검증: {cut.date()} 이후")
    top = sorted(rows, key=lambda r: (r["train"]["win"] if r["train"]["n"] >= a.min_train
                                      and r["train"]["avg"] > 0 else -1), reverse=True)[:8]
    print("\n[참고] 학습 구간 승률 상위 조합 (기대값 > 0 만)")
    for r in top:
        p = r["params"]
        print(f"  매수≥{p.buy_th:<3} 익절 {p.tp_atr}/{p.tp2_atr}ATR 손절 {p.sl_atr}ATR "
              f"보유 {p.max_hold:>2}일"
              f" | 학습 {r['train']['win']:5.1f}% ({r['train']['n']}회, 평균 {r['train']['avg']:+.2f}%)"
              f" | 검증 {r['test']['win']:5.1f}% ({r['test']['n']}회, 평균 {r['test']['avg']:+.2f}%)")
    if best is None:
        print("\n❌ 기대수익이 플러스인 조합이 없습니다. 종목/기간을 늘리거나 점수 로직을 수정하세요.")
        return
    p, tr, te = best["params"], best["train"], best["test"]
    print("\n[선택된 설정]", p)
    print("  학습 " + _stat_line(tr))
    print("  검증 " + _stat_line(te))
    total = tr["n"] + te["n"]
    ok_n = total >= 100
    ok_win = te["win"] >= a.target and tr["win"] >= a.target
    print(f"\n  총 모의거래 {total}회 {'✅' if ok_n else '❌ (100회 미만: 종목이나 기간을 늘리세요)'}")
    if ok_win:
        print(f"  ✅ 학습·검증 모두 승률 {a.target:.0f}% 이상")
    else:
        print(f"  ⚠ 검증 승률 {te['win']:.1f}%: 목표 {a.target:.0f}% 미달. "
              f"실전 기대치는 검증 숫자에 가깝습니다.")
    if te["n"] and te["avg"] <= 0:
        print("  ⚠ 검증 구간 평균수익이 마이너스: 실전 사용 비추천")
    print("\n[B·C 효과 비교] 같은 설정에서 시장필터/분할익절을 켜고 끈 결과")
    for label, a_tr, a_te in backtest.ablation(datasets, p, cut):
        print(f"  {label:<12} 학습 {a_tr['win']:5.1f}% ({a_tr['n']}회, 평균 {a_tr['avg']:+.2f}%)"
              f" | 검증 {a_te['win']:5.1f}% ({a_te['n']}회, 평균 {a_te['avg']:+.2f}%,"
              f" 최악 {a_te['worst']:+.1f}%)")
    p.save(extra={"train": tr, "test": te, "split_date": str(cut.date()), "codes": codes})
    print(f"  설정 저장: {backtest.PARAMS_PATH} (monitor/backtest 가 자동 사용)")


def cmd_monitor(a):
    realtime.monitor(read_codes(a.codes), backtest.Params.load(), a.interval, a.once, a.days)


def cmd_paper(a):
    realtime.paper_report(a.target_n)


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
    p.add_argument("--days", type=int, default=500, help="조회 거래일 수 (기본 500 ≈ 2년)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("analyze", help="종목 분석")
    s1.add_argument("code", help="종목코드 6자리 (예: 005930) 또는 DEMO")
    s1.add_argument("--chart", action="store_true", help="차트 PNG 저장")
    s2 = sub.add_parser("scan", help="관심종목 랭킹")
    s2.add_argument("watchlist", help="종목코드 파일 경로 또는 쉼표 구분 코드")
    s3 = sub.add_parser("backtest", help="전략 백테스트 (best_params.json 사용)")
    s3.add_argument("codes", help="종목코드, 쉼표 구분 또는 파일 (예: universe.txt)")
    s3.add_argument("--buy", dest="buy_th", type=float)
    s3.add_argument("--exit", dest="exit_th", type=float)
    s3.add_argument("--tp", dest="tp_atr", type=float, help="1차 익절 ATR 배수")
    s3.add_argument("--tp2", dest="tp2_atr", type=float, help="2차 익절 ATR 배수")
    s3.add_argument("--no-market", action="store_true", help="시장 필터(B) 끄기")
    s3.add_argument("--no-split", action="store_true", help="분할 익절(C) 끄기")
    s3.add_argument("--sl", dest="sl_atr", type=float, help="손절 ATR 배수")
    s3.add_argument("--hold", dest="max_hold", type=int)
    s3.add_argument("--show", action="store_true", help="거래 내역 출력")
    s4 = sub.add_parser("optimize", help="과거 데이터로 승률 최적 설정 탐색")
    s4.add_argument("codes", nargs="?", default="universe.txt")
    s4.add_argument("--target", type=float, default=80, help="목표 승률 %% (기본 80)")
    s4.add_argument("--min-train", type=int, default=70, help="학습 구간 최소 거래수")
    s5 = sub.add_parser("monitor", help="장중 실시간 감시 + 모의매매 기록")
    s5.add_argument("codes", nargs="?", default="watchlist.txt")
    s5.add_argument("--interval", type=float, default=5, help="점검 간격(분)")
    s5.add_argument("--once", action="store_true", help="1회만 점검 (장외 시간에도)")
    s6 = sub.add_parser("paper", help="모의매매 성적 집계")
    s6.add_argument("--target-n", type=int, default=100)
    a = p.parse_args(argv)
    {"analyze": cmd_analyze, "scan": cmd_scan, "backtest": cmd_backtest,
     "optimize": cmd_optimize, "monitor": cmd_monitor, "paper": cmd_paper}[a.cmd](a)


if __name__ == "__main__":
    main()
