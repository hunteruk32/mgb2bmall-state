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
    print(f" [매매 가이드] 저장된 설정: {p.describe()}")
    buy, _, why = backtest.latest(d, p)
    for w in why:
        print("  " + w)
    stop = s.close - backtest.stop_distance(p, s.close, r.atr)
    if not buy:
        print(f"  → 매수 신호 없음. 보유 중이라면 손절 기준 {fmt(stop)}원 "
              f"({(stop / s.close - 1) * 100:+.1f}%)")
    elif p.market_filter and not mkt_ok:
        print(f"  → 매수 신호지만 시장 필터({mkt_msg})로 신규 매수 보류")
    else:
        print(f"  → 매수 신호! 진입 참고가 {fmt(s.close)}원 (다음날 시가 부근)")
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
    stop = close - backtest.stop_distance(p, close, atr)
    t1, t2 = close + p.tp_atr * atr, close + p.tp2_atr * atr
    pct = lambda v: f"{(v / close - 1) * 100:+.1f}%"  # noqa: E731
    print(f"  손절가      : {fmt(stop)}원 ({pct(stop)})")
    if p.split:
        print(f"  1차 익절    : {fmt(t1)}원 ({pct(t1)}) → 절반 매도 후 남은 절반 손절가를 "
              f"본전 {fmt(close * (1 + p.cost))}원으로 올림")
        print(f"  2차 익절    : {fmt(t2)}원 ({pct(t2)}) → 나머지 매도")
    else:
        print(f"  익절가      : {fmt(t1)}원 ({pct(t1)})")
    cond = (f"RSI ≥ {p.rsi_exit:g}" if p.strategy == "pullback" else f"점수 ≤ {p.exit_th:g}")
    print(f"  그 외 청산  : {cond} 또는 {p.max_hold}일 경과 시 다음날 시가")


def cmd_scan(a):
    codes = read_codes(a.watchlist)
    p = backtest.Params.load()
    print(f"저장된 설정: {p.describe()}")
    rows = []
    for code in codes:
        try:
            raw, name = load(code, a.days)
            d = indicators.add_all(raw)
            s = score_at(d)
            r = d.iloc[-1]
            buy, sell, _ = backtest.latest(d, p)
            rows.append(dict(코드=code, 종목=name, 종가=fmt(s.close),
                             신호="매수" if buy else ("청산" if sell else "-"),
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
        with open(arg, encoding="utf-8-sig") as f:
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
    if a.strategy:
        p.strategy = a.strategy
    codes = read_codes(a.codes)
    datasets = prepare_all(codes, a.days, verbose=False)
    trades = [x for c, d in datasets.items() for x in backtest.simulate(d, p, c)]
    print(f"백테스트 {len(datasets)}종목 | {p.describe()}")
    t = pd.DataFrame(trades)
    if not t.empty and a.show:
        with pd.option_context("display.width", 200):
            print(t.assign(ret=t.ret.round(2)).to_string(index=False))
    print("  " + _stat_line(backtest.summarize(t)))


def prepare_all(codes: list[str], days: int, verbose: bool = True):
    """여러 종목 데이터 + 지표 + 점수 + 시장필터 준비 (캐시 24시간)."""
    mk = market_flags(codes, days)
    if mk is not None and verbose:
        print(f"  시장 필터: 기간 중 {(~mk.mkt_ok).mean() * 100:.0f}%의 날이 코스피 약세")
    datasets = {}
    for n, code in enumerate(codes, 1):
        try:
            raw, name = load(code, days, cache_hours=24)
            datasets[code] = backtest.prepare(raw, mk)
            if verbose:
                print(f"  [{n}/{len(codes)}] {name}({code}) {len(raw)}일 준비 완료")
        except Exception as e:  # noqa: BLE001
            print(f"  [{n}/{len(codes)}] {code} 실패: {e}")
    return datasets


STRATEGY_NAMES = {"score": "점수 전략 (기존)", "pullback": "눌림목 전략 (신규)"}


def _row(label: str, tr: dict, te: dict) -> str:
    return (f"  {label:<14} 학습 {tr['win']:5.1f}% ({tr['n']:>4}회, 평균 {tr['avg']:+.2f}%)"
            f" | 검증 {te['win']:5.1f}% ({te['n']:>4}회, 평균 {te['avg']:+.2f}%, 최악 {te['worst']:+.1f}%)")


def cmd_optimize(a):
    codes = read_codes(a.codes)
    datasets = prepare_all(codes, a.days)
    if not datasets:
        return
    strategies = ["score", "pullback"] if a.strategy == "both" else [a.strategy]
    results, cut = {}, None
    for st in strategies:
        print(f"\n{'=' * 78}\n {STRATEGY_NAMES[st]}\n{'=' * 78}")
        best, rows, cut = backtest.optimize(datasets, target_win=a.target, min_train=a.min_train,
                                            base=backtest.Params(strategy=st))
        print(f"  조합 {len(rows)}개 시험 | 학습: ~{cut.date()} 이전 / 검증: {cut.date()} 이후")
        ok = [r for r in rows if r["train"]["n"] >= a.min_train and r["train"]["avg"] > 0
              and r["train"]["pf"] > 1]
        print(f"  학습 구간 조건(거래 ≥ {a.min_train}회, 평균수익 > 0, PF > 1) 통과: {len(ok)}개")
        if ok:
            print("\n  [참고] 학습 구간 평균수익 상위 5개")
            for r in sorted(ok, key=lambda r: r["train"]["avg"], reverse=True)[:5]:
                print(f"   · {r['params'].describe()}")
                print("   " + _row("", r["train"], r["test"]).strip())
        if best is None:
            print("\n  ❌ 학습 구간에서 기대수익이 플러스인 조합이 없습니다.")
            results[st] = None
            continue
        p, tr, te = best["params"], best["train"], best["test"]
        print(f"\n  [선택된 설정] {p.describe()}")
        print("   학습 " + _stat_line(tr))
        print("   검증 " + _stat_line(te))
        print("\n  [구성요소 효과] 같은 설정에서 하나씩 끄고 켠 결과")
        for label, a_tr, a_te in backtest.ablation(datasets, p, cut):
            print(_row(label, a_tr, a_te))
        q = backtest.Params(**{**p.__dict__, "max_loss": 0})
        print(_row("손실상한 없음", *backtest.evaluate(datasets, q, cut)))
        results[st] = best

    valid = {k: v for k, v in results.items() if v}
    print(f"\n{'=' * 78}\n [최종 비교]\n{'=' * 78}")
    for st, r in results.items():
        if r:
            print(_row(STRATEGY_NAMES[st][:6], r["train"], r["test"]))
        else:
            print(f"  {STRATEGY_NAMES[st][:6]:<14} 쓸 만한 설정 없음")
    if not valid:
        print("\n❌ 두 전략 모두 기대수익이 플러스인 설정이 없습니다. 실전 사용 불가.")
        return
    # 전략 선택도 '학습' 성적으로만 한다 (검증 성적으로 고르면 검증의 의미가 사라짐)
    st = max(valid, key=lambda k: valid[k]["train"]["avg"])
    p, tr, te = valid[st]["params"], valid[st]["train"], valid[st]["test"]
    print(f"\n  선택: {STRATEGY_NAMES[st]} (학습 구간 평균수익 기준으로 선택)")
    print(f"  설정: {p.describe()}")
    total = tr["n"] + te["n"]
    print(f"  총 모의거래 {total}회 {'✅' if total >= 100 else '❌ (100회 미만)'}")
    if te["n"] == 0:
        print("  ⚠ 검증 구간 거래 없음: 판단 불가")
    elif te["avg"] <= 0:
        print("  ⚠ 검증 구간 평균수익이 마이너스: 실전 사용 비추천")
    elif te["win"] >= a.target:
        print(f"  ✅ 검증 구간도 평균수익 플러스, 승률 {te['win']:.1f}% (목표 {a.target:.0f}% 이상)")
    else:
        print(f"  △ 검증 구간 평균수익은 플러스, 승률 {te['win']:.1f}% (목표 {a.target:.0f}% 미만)")
    print(f"  ※ 시험한 조합이 많을수록 우연히 좋아 보일 위험이 큽니다. "
          f"실전 전 모의매매(monitor/paper)로 꼭 재확인하세요.")
    p.save(extra={"train": tr, "test": te, "split_date": str(cut.date()), "codes": codes})
    print(f"  설정 저장: {backtest.PARAMS_PATH} (analyze/scan/monitor/backtest 가 자동 사용)")


def cmd_monitor(a):
    realtime.monitor(read_codes(a.codes), backtest.Params.load(), a.interval, a.once, a.days)


def cmd_edge(a):
    import edge
    datasets = prepare_all(read_codes(a.codes), a.days, verbose=False)
    if not datasets:
        return
    cut = backtest.split_date(datasets, 0.7)
    print(f"신호 예측력 진단: {len(datasets)}종목 | 학습 ~{cut.date()} / 검증 {cut.date()}~")
    edge.report(datasets, cut, a.horizon)
    edge.pullback_report(datasets, cut, a.horizon)
    p = backtest.Params.load()
    t = pd.DataFrame([x for c, d in datasets.items() for x in backtest.simulate(d, p, c)])
    if not t.empty:
        print(f"\n[4] 저장된 설정의 최악 거래 5건 (데이터 오류인지 실제 급락인지 확인용)")
        w = t.nsmallest(5, "ret")
        for r in w.itertuples():
            print(f"  {r.code} {r.entry_date.date()} 매수 {r.entry:,.0f} → {r.exit_date.date()} "
                  f"{r.exit:,.0f} ({r.ret:+.1f}%, {r.reason}, {r.held}일)")


def default_universe() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    wide = os.path.join(here, "universe_wide.txt")
    return wide if os.path.exists(wide) else os.path.join(here, "universe.txt")


def cmd_universe(a):
    rows = []
    for market, n in (("KOSPI", a.kospi), ("KOSDAQ", a.kosdaq)):
        if n <= 0:
            continue
        try:
            got = data.fetch_universe(market, n)
            print(f"  {market}: {len(got)}종목")
            rows += [(c, nm, market) for c, nm in got]
        except Exception as e:  # noqa: BLE001
            print(f"  {market} 실패: {e}")
    if not rows:
        print("종목 목록을 받지 못했습니다. python diag.py 결과를 보내주세요.")
        return
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), a.out)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# 시가총액 상위 보통주 (코스피 {a.kospi} / 코스닥 {a.kosdaq}), 자동 생성\n")
        for c, nm, mk in rows:
            f.write(f"{c}  # {nm} ({mk})\n")
    print(f"저장: {path} ({len(rows)}종목)")


def cmd_research(a):
    import research
    codes = read_codes(a.codes or default_universe())
    days = a.years * 250
    print(f"신호 연구: {len(codes)}종목 × 약 {a.years}년 (처음엔 데이터 수집에 시간이 걸립니다)")
    datasets = prepare_all(codes, days, verbose=a.verbose)
    print(f"  준비 완료: {len(datasets)}종목")
    _flow_coverage(datasets)
    research.report(datasets, a.horizon)


def _flow_coverage(datasets):
    starts = [d["foreign"].first_valid_index() for d in datasets.values()
              if "foreign" in d and d["foreign"].notna().any()]
    if starts:
        s = pd.Series(pd.to_datetime(starts))
        print(f"  수급 데이터 시작일: 중간값 {s.median().date()} (가장 이른 {s.min().date()}) / "
              f"수급 있는 종목 {len(starts)}/{len(datasets)}")


def cmd_walkforward(a):
    codes = read_codes(a.codes or default_universe())
    days = a.years * 250
    datasets = prepare_all(codes, days, verbose=a.verbose)
    print(f"기간별 반복 검증: {len(datasets)}종목 × 약 {a.years}년, {a.folds}개 구간")
    print("  방식: 각 구간 '직전까지' 데이터로만 설정을 고르고, 그 구간에서 실제처럼 매매")
    _flow_coverage(datasets)
    strategies = ["score", "pullback"] if a.strategy == "both" else [a.strategy]
    finals = {}
    for st in strategies:
        folds, oos, final, ncombo, base = backtest.walk_forward(
            datasets, st, a.folds, target_win=a.target, min_train=a.min_train)
        print(f"\n{'=' * 78}\n {STRATEGY_NAMES[st]}  (조합 {ncombo}개)\n{'=' * 78}")
        for f in folds:
            end = f["end"].date() if f["end"] is not None else "현재"
            b = f["best"]
            if b is None:
                print(f"  {f['start'].date()} ~ {end}: 조건 맞는 설정 없음 → 매매 안 함")
                continue
            print(f"  {f['start'].date()} ~ {end}: {b['params'].describe()}")
            print(f"     직전까지(학습) {_stat_line(b['train'])}")
            print(f"     이 구간(실전)  {_stat_line(b['test'])}")
            if f["base"]:
                print(f"     비교: 아무날 매수 {_stat_line(f['base'])}")
        print(f"\n  ▶ 실전 가정 전체 성적 (모든 구간 합산): {_stat_line(oos)}")
        print(f"  ▷ 비교: 같은 규칙으로 아무 날이나 매수:  {_stat_line(base)}")
        finals[st] = (final, oos, base)
    print(f"\n{'=' * 78}\n [결론]\n{'=' * 78}")
    print("  (판정: 평균수익 플러스·PF > 1.1 이면서 '아무 날이나 매수'보다 거래당 0.2%p 이상 나아야 ✅)")

    def beats(oos, base):
        return (oos["n"] >= 30 and oos["avg"] > 0 and oos["pf"] > 1.1
                and oos["avg"] - base["avg"] >= 0.2)

    for st, (final, oos, base) in finals.items():
        edge_p = oos["avg"] - base["avg"] if oos["n"] and base["n"] else float("nan")
        verdict = ("거래 없음" if not oos["n"] else
                   "✅ 신호 효과 있음" if beats(oos, base) else
                   "△ 수익은 났지만 아무날 매수와 비슷 (신호 효과 불확실)" if oos["avg"] > 0 else
                   "❌ 마이너스")
        print(f"  {STRATEGY_NAMES[st]:<16} 실전 가정 {oos['n']}회, 승률 {oos['win']:.1f}%, "
              f"평균 {oos['avg']:+.2f}% (아무날 대비 {edge_p:+.2f}%p) → {verdict}")
    good = {k: v for k, v in finals.items() if beats(v[1], v[2]) and v[0] is not None}
    if not good:
        print("\n  어느 전략도 '아무 날이나 매수'보다 확실히 낫지 않습니다. 설정을 저장하지 않습니다.")
        return
    st = max(good, key=lambda k: good[k][1]["avg"])
    final = good[st][0]
    print(f"\n  저장: {STRATEGY_NAMES[st]} — 전체 기간으로 다시 고른 설정 {final['params'].describe()}")
    final["params"].save(extra={"walkforward_oos": good[st][1], "codes": codes})


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
    s3.add_argument("--strategy", choices=["score", "pullback"], help="전략 지정")
    s3.add_argument("--no-market", action="store_true", help="시장 필터(B) 끄기")
    s3.add_argument("--no-split", action="store_true", help="분할 익절(C) 끄기")
    s3.add_argument("--sl", dest="sl_atr", type=float, help="손절 ATR 배수")
    s3.add_argument("--hold", dest="max_hold", type=int)
    s3.add_argument("--show", action="store_true", help="거래 내역 출력")
    s4 = sub.add_parser("optimize", help="과거 데이터로 승률 최적 설정 탐색")
    s4.add_argument("codes", nargs="?", default="universe.txt")
    s4.add_argument("--strategy", choices=["both", "score", "pullback"], default="both",
                    help="시험할 전략 (기본 both: 둘 다 시험 후 비교)")
    s4.add_argument("--target", type=float, default=60,
                    help="목표 승률 %% (기본 60). 이 이상 중 평균수익 최대 설정 선택")
    s4.add_argument("--min-train", type=int, default=70, help="학습 구간 최소 거래수")
    s5 = sub.add_parser("monitor", help="장중 실시간 감시 + 모의매매 기록")
    s5.add_argument("codes", nargs="?", default="watchlist.txt")
    s5.add_argument("--interval", type=float, default=5, help="점검 간격(분)")
    s5.add_argument("--once", action="store_true", help="1회만 점검 (장외 시간에도)")
    s7 = sub.add_parser("edge", help="신호 예측력 진단 (점수/영역별 이후 수익률)")
    s7.add_argument("codes", nargs="?", default="universe.txt")
    s7.add_argument("--horizon", type=int, default=5, help="보유 가정 일수 (기본 5)")
    s8 = sub.add_parser("universe", help="시가총액 상위 종목 목록 생성 (universe_wide.txt)")
    s8.add_argument("--kospi", type=int, default=100)
    s8.add_argument("--kosdaq", type=int, default=50)
    s8.add_argument("--out", default="universe_wide.txt")
    for name, helptext in (("research", "신호별 연도별 초과수익 연구"),
                           ("walkforward", "기간을 바꿔가며 반복 검증")):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("codes", nargs="?", default=None,
                        help="종목 파일 (기본: universe_wide.txt, 없으면 universe.txt)")
        sp.add_argument("--years", type=int, default=5, help="기간(년), 기본 5")
        sp.add_argument("--verbose", action="store_true", help="종목별 진행 표시")
        if name == "research":
            sp.add_argument("--horizon", type=int, default=5, help="보유 가정 일수 (기본 5)")
        else:
            sp.add_argument("--strategy", choices=["both", "score", "pullback"], default="both")
            sp.add_argument("--folds", type=int, default=4, help="검증 구간 수 (기본 4)")
            sp.add_argument("--target", type=float, default=60)
            sp.add_argument("--min-train", type=int, default=50)
    s6 = sub.add_parser("paper", help="모의매매 성적 집계")
    s6.add_argument("--target-n", type=int, default=100)
    a = p.parse_args(argv)
    {"analyze": cmd_analyze, "scan": cmd_scan, "backtest": cmd_backtest,
     "optimize": cmd_optimize, "monitor": cmd_monitor, "paper": cmd_paper,
     "edge": cmd_edge, "universe": cmd_universe, "research": cmd_research,
     "walkforward": cmd_walkforward}[a.cmd](a)


if __name__ == "__main__":
    main()
