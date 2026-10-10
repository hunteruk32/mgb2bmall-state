"""전략 백테스트 + 파라미터 최적화.

전략 (Params.strategy)
  - score   : 종합점수 >= buy_th 이면 매수, 점수 <= exit_th 이면 청산
  - pullback: 눌림목. 장기 상승 추세(종가 > trend_ma일선)인데 RSI <= rsi_th 로 과매도,
              (rsi_confirm 이면 RSI가 전일보다 반등) 이면 매수, RSI >= rsi_exit 이면 청산
  - reversal: 단기 반등. 단기 급락(rev_signal: rsi / drop5 / ma20gap, 기준 rev_th) 시 매수,
              RSI >= rsi_exit 이면 청산 (research 에서 매년 꾸준했던 신호)

매매 규칙 (실시간 모의매매와 동일)
  - 진입: 장 마감 기준 매수 신호 + 시장 필터 통과(B, 사용 시) -> 다음날 시가 매수
  - 손절: 진입가 - min(sl_atr * ATR, max_loss * 진입가)  (장중 터치, 갭하락이면 시가)
  - 1차 익절(C): 진입가 + tp_atr * ATR 터치 -> 절반 매도, 남은 절반 손절가를 '본전'으로 상향
  - 2차 익절: 진입가 + tp2_atr * ATR 터치 -> 나머지 매도
  - 청산: 장 마감 청산 신호 또는 보유일 >= max_hold -> 다음날 시가 매도
  - 비용: 왕복 cost (수수료 + 증권거래세, 기본 0.25%). 본전 = 진입가 x (1 + cost)
  같은 날 손절과 1차 익절가에 모두 닿으면 보수적으로 '손절' 처리.
  1차 익절 당일의 본전 이탈은 봉 모양으로 판단
  (양봉: 시가→저가→고가→종가 순, 음봉: 시가→고가→저가→종가 순으로 움직였다고 가정).

과최적화 방지
  - 기간을 앞(학습)/뒤(검증)로 나눠 학습 구간에서만 파라미터를 고르고
    검증 구간 성적을 별도로 보고한다. 실제 기대치는 '검증' 숫자를 보세요.
"""
from __future__ import annotations

import itertools
import json
import os
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

import indicators
import market
from signals import score_at

PARTS = ("추세", "모멘텀", "거래량", "수급")
PARAMS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "best_params.json")


@dataclass
class Params:
    buy_th: float = 25
    exit_th: float = -10
    tp_atr: float = 1.5           # 1차 익절 (분할 사용 시 절반), 미사용 시 전량 익절
    tp2_atr: float = 3.0          # 2차 익절 (분할 사용 시)
    sl_atr: float = 2.0
    max_hold: int = 10
    cost: float = 0.0025
    split: bool = True            # C: 분할 익절 + 본전 스탑
    market_filter: bool = True    # B: 시장 필터
    max_loss: float = 0.07        # 한 거래 최대 손실(손절폭 상한). 0 이면 제한 없음
    strategy: str = "score"       # "score" | "pullback"
    trend_ma: int = 120           # pullback: 장기 추세 기준 이동평균
    rsi_th: float = 35            # pullback: 과매도 기준
    rsi_confirm: bool = True      # pullback: RSI 반등 확인 후 매수
    rsi_exit: float = 60          # pullback/reversal: RSI 회복 시 청산
    rev_signal: str = "rsi"       # reversal: "rsi"(RSI ≤ th) | "drop5"(5일 −th% 이하) | "ma20gap"(20일선 −th% 이하)
    rev_th: float = 30            # reversal: 기준값
    max_pos: int = 5              # 모의매매/계좌: 동시 최대 보유 종목 수

    def save(self, path: str = PARAMS_PATH, extra: dict | None = None):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({**asdict(self), **(extra or {})}, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str = PARAMS_PATH) -> "Params":
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        fields = asdict(cls())
        return cls(**{k: type(fields[k])(raw[k]) for k in fields
                      if k in raw and isinstance(raw[k], (int, float, bool, str))})

    def describe(self) -> str:
        if self.strategy == "pullback":
            core = (f"눌림목: {self.trend_ma}일선 위 + RSI ≤ {self.rsi_th:g}"
                    f"{' + RSI 반등' if self.rsi_confirm else ''} → 매수, RSI ≥ {self.rsi_exit:g} 청산")
        else:
            core = f"점수: ≥ {self.buy_th:g} 매수, ≤ {self.exit_th:g} 청산"
        tp = (f"1차 {self.tp_atr:g}ATR 절반·2차 {self.tp2_atr:g}ATR" if self.split
              else f"익절 {self.tp_atr:g}ATR")
        if self.strategy == "reversal":
            core = f"반등: {REV_LABEL[self.rev_signal].format(th=self.rev_th)} → 매수, RSI ≥ {self.rsi_exit:g} 청산"
        cap = f", 최대 −{self.max_loss * 100:g}%" if self.max_loss > 0 else ""
        return (f"{core} | 손절 {self.sl_atr:g}ATR{cap} | {tp} | 최대 {self.max_hold}일 | "
                f"시장필터 {'ON' if self.market_filter else 'OFF'}")


REV_LABEL = {"rsi": "RSI ≤ {th:g}", "drop5": "5일간 −{th:g}% 이상 급락",
             "ma20gap": "20일선보다 −{th:g}% 이상 아래"}


def stop_distance(p: Params, entry: float, atr: float) -> float:
    """손절폭 = ATR 배수, 단 max_loss 비율을 넘지 않게."""
    dist = p.sl_atr * atr
    return min(dist, p.max_loss * entry) if p.max_loss > 0 else dist


def signals(d: pd.DataFrame, p: Params, use_market: bool = True):
    """(매수신호 bool 배열, 청산신호 bool 배열, 청산 사유 이름). 장 마감 기준."""
    if p.strategy == "pullback":
        rsi = d["rsi"]
        entry = (d["close"] > d[f"ma{p.trend_ma}"]) & (rsi <= p.rsi_th)
        if p.rsi_confirm:
            entry &= rsi > rsi.shift()
        exit_ = rsi >= p.rsi_exit
        label = "RSI회복"
    elif p.strategy == "reversal":
        if p.rev_signal == "rsi":
            entry = d["rsi"] <= p.rev_th
        elif p.rev_signal == "drop5":
            entry = d["ret5"] <= -p.rev_th
        elif p.rev_signal == "ma20gap":
            entry = d["close"] / d["ma20"] <= 1 - p.rev_th / 100
        else:
            raise ValueError(f"알 수 없는 반등 신호: {p.rev_signal}")
        exit_ = d["rsi"] >= p.rsi_exit
        label = "RSI회복"
    elif p.strategy == "always":  # 비교 기준선: 신호 없이 매일 매수 시도 (청산은 손익절/기간만)
        entry = pd.Series(True, index=d.index)
        exit_ = pd.Series(False, index=d.index)
        label = "기간만료"
    elif p.strategy == "score":
        sc = d["score"]
        entry, exit_, label = sc >= p.buy_th, sc <= p.exit_th, "점수하락"
    else:
        raise ValueError(f"알 수 없는 전략: {p.strategy}")
    entry &= d["atr"].notna()
    if use_market and p.market_filter and "mkt_ok" in d:
        entry &= d["mkt_ok"].astype(bool)
    return entry.fillna(False).to_numpy(bool), exit_.fillna(False).to_numpy(bool), label


def prepare(raw: pd.DataFrame, mk: pd.DataFrame | None = None, start: int = 60) -> pd.DataFrame:
    """지표 + 일별 점수(score) + 시장필터(mkt_ok) 컬럼을 미리 계산 (파라미터 탐색 시 재사용).
    mk: market.flags() 결과. None 이면 시장 필터 없이 항상 허용."""
    d = market.attach(indicators.add_all(raw), mk)
    sc = np.full(len(d), np.nan)
    parts = {k: np.full(len(d), np.nan) for k in PARTS}
    for i in range(start, len(d)):
        sig = score_at(d, i)
        sc[i] = sig.score
        for k in PARTS:
            parts[k][i] = sig.parts[k]
    d["score"] = sc
    for k in PARTS:
        d[f"part_{k}"] = parts[k]
    return d


def _arrays(d: pd.DataFrame, p: Params) -> dict:
    ent, exs, label = signals(d, p)
    return dict(o=d["open"].to_numpy(), h=d["high"].to_numpy(), l=d["low"].to_numpy(),
                c=d["close"].to_numpy(), atr=d["atr"].to_numpy(), idx=d.index,
                sc=d["score"].to_numpy() if "score" in d else np.full(len(d), np.nan),
                rsi=d["rsi"].to_numpy() if "rsi" in d else np.full(len(d), np.nan), ent=ent, exs=exs, label=label, n=len(d))


def _trade(A: dict, p: Params, i: int, code: str) -> tuple[dict | None, int | None]:
    """i일 장마감 신호 → i+1일 시가 진입 한 건을 끝까지 추적. (거래, 청산 인덱스).
    시가 이상이면 (None, None), 데이터 끝까지 보유 중이면 (None, -1)."""
    o, h, l, c, n = A["o"], A["h"], A["l"], A["c"], A["n"]
    j = i + 1                          # 진입일
    entry, a = o[j], A["atr"][i]
    if not entry > 0:                  # 데이터 이상(시가 0) -> 건너뜀
        return None, None
    stop = entry - stop_distance(p, entry, a)
    t1, t2 = entry + p.tp_atr * a, entry + p.tp2_atr * a
    be = entry * (1 + p.cost)          # 본전 스탑
    half = None                        # 1차 익절한 절반의 수익률
    exit_px = why = None
    k = j
    while k < n:
        if half is None:
            if l[k] <= stop:
                exit_px, why, ex = min(o[k], stop), "손절", k
            elif h[k] >= t1:
                px1 = max(o[k], t1)
                if not p.split:
                    exit_px, why, ex = px1, "익절", k
                else:
                    half, stop = px1 / entry - 1, be
                    if h[k] >= t2:
                        exit_px, why, ex = max(o[k], t2), "2차익절", k
                    elif (c[k] < o[k] and l[k] <= be) or (c[k] >= o[k] and c[k] <= be):
                        exit_px, why, ex = be, "1차익절+본전", k
        else:
            if l[k] <= stop:
                exit_px, why, ex = min(o[k], stop), "1차익절+본전", k
            elif h[k] >= t2:
                exit_px, why, ex = max(o[k], t2), "2차익절", k
        if exit_px is None and (A["exs"][k] or k - j + 1 >= p.max_hold) and k + 1 < n:
            exit_px, ex = o[k + 1], k + 1
            why = ("1차익절+" if half is not None else "") + \
                  (A["label"] if A["exs"][k] else "기간만료")
        if exit_px is not None:
            break
        k += 1
    if exit_px is None:                # 데이터 끝까지 보유 중 -> 집계 제외
        return None, -1
    r2 = exit_px / entry - 1
    ret = (r2 if half is None else 0.5 * half + 0.5 * r2) - p.cost
    idx = A["idx"]
    return dict(code=code, entry_date=idx[j], entry=entry, exit_date=idx[ex], exit=exit_px,
                ret=ret * 100, reason=why, held=ex - j + 1, score=A["sc"][i],
                rsi=A["rsi"][i]), ex


def simulate(d: pd.DataFrame, p: Params, code: str = "") -> list[dict]:
    """한 종목을 한 번에 한 포지션씩 순서대로 매매."""
    A = _arrays(d, p)
    i, trades = 0, []
    while i < A["n"] - 1:
        if not A["ent"][i]:
            i += 1
            continue
        t, ex = _trade(A, p, i, code)
        if ex is None:
            i += 1
            continue
        if ex == -1:
            break
        trades.append(t)
        i = ex                         # 청산일 종가부터 다시 신호 탐색
    return trades


def candidates(d: pd.DataFrame, p: Params, code: str = "") -> list[dict]:
    """신호가 난 '모든' 날에 대해 독립적으로 매매를 추적 (계좌 시뮬레이션용 후보)."""
    A = _arrays(d, p)
    out = []
    for i in np.flatnonzero(A["ent"][: A["n"] - 1]):
        t, ex = _trade(A, p, int(i), code)
        if t is not None:
            out.append(t)
    return out


def summarize(trades: list[dict] | pd.DataFrame) -> dict:
    t = pd.DataFrame(trades)
    if t.empty:
        return dict(n=0, win=0.0, avg=0.0, avg_win=0.0, avg_loss=0.0, pf=0.0,
                    worst=0.0, max_losing=0)
    r = t["ret"]
    wins, losses = r[r > 0], r[r <= 0]
    streak = mx = 0
    for v in t.sort_values("exit_date")["ret"]:
        streak = streak + 1 if v <= 0 else 0
        mx = max(mx, streak)
    return dict(n=len(t), win=float((r > 0).mean() * 100), avg=float(r.mean()),
                avg_win=float(wins.mean()) if len(wins) else 0.0,
                avg_loss=float(losses.mean()) if len(losses) else 0.0,
                pf=float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf"),
                worst=float(r.min()), max_losing=mx)


GRIDS = {
    "score": dict(buy_th=[25, 35, 45, 55], tp_atr=[0.5, 1.0, 1.5, 2.0],
                  tp2_atr=[2.0, 3.0, 4.0], sl_atr=[1.0, 1.5, 2.0, 3.0], max_hold=[3, 5, 10],
                  max_loss=[0.05, 0.07]),
    "pullback": dict(trend_ma=[60, 120], rsi_th=[30.0, 35.0, 40.0], rsi_confirm=[False, True],
                     rsi_exit=[50.0, 60.0], tp_atr=[1.0, 1.5, 2.0], tp2_atr=[3.0, 4.0],
                     sl_atr=[1.5, 2.5], max_loss=[0.05, 0.07], max_hold=[5, 10],
                     market_filter=[False, True]),
}
GRID = GRIDS["score"]


def split_date(datasets: dict[str, pd.DataFrame], ratio: float) -> pd.Timestamp:
    dates = sorted(set().union(*[set(d.index) for d in datasets.values()]))
    return dates[int(len(dates) * ratio)]


def evaluate(datasets: dict[str, pd.DataFrame], p: Params, cut: pd.Timestamp):
    t = pd.DataFrame([x for code, d in datasets.items() for x in simulate(d, p, code)])
    if t.empty:
        return summarize([]), summarize([])
    return summarize(t[t.entry_date < cut]), summarize(t[t.entry_date >= cut])


def ablation(datasets: dict[str, pd.DataFrame], p: Params, cut: pd.Timestamp) -> list[tuple]:
    """선택된 설정에서 B(시장필터)/C(분할익절)를 끄고 켰을 때 성적 비교."""
    out = []
    for label, mf, sp in (("B+C 모두 적용", True, True), ("B 시장필터만", True, False),
                          ("C 분할익절만", False, True), ("둘 다 없음", False, False)):
        q = Params(**{**asdict(p), "market_filter": mf, "split": sp})
        out.append((label, *evaluate(datasets, q, cut)))
    return out


def optimize(datasets: dict[str, pd.DataFrame], target_win: float = 60, ratio: float = 0.7,
             min_train: int = 50, grid: dict | None = None, base: Params | None = None):
    """학습 구간에서 '거래 >= min_train, 평균수익 > 0, PF > 1' 조합 중
       승률 target_win 이상이면 그 중 평균수익 최대, 없으면 전체 후보 중 평균수익 최대.
       (승률만 최대화하면 '익절 짧게·손절 넓게'인 손실 큰 설정이 골라지므로 기대수익 기준)"""
    base = base or Params()
    grid = grid or GRIDS[base.strategy]
    cut = split_date(datasets, ratio)
    rows = []
    for combo in itertools.product(*grid.values()):
        p = Params(**{**asdict(base), **dict(zip(grid.keys(), combo))})
        if p.split and p.tp2_atr <= p.tp_atr:
            continue
        tr, te = evaluate(datasets, p, cut)
        rows.append(dict(params=p, train=tr, test=te))
    return select(rows, target_win, min_train), rows, cut


def select(rows: list[dict], target_win: float, min_train: int, key: str = "train"):
    """후보: 거래 >= min_train, 평균수익 > 0, PF > 1.
       승률 >= target_win 인 후보가 있으면 그 중 평균수익 최대, 없으면 후보 중 평균수익 최대."""
    ok = [r for r in rows if r[key]["n"] >= min_train and r[key]["avg"] > 0 and r[key]["pf"] > 1]
    hit = [r for r in ok if r[key]["win"] >= target_win]
    pool = hit or ok
    return max(pool, key=lambda r: r[key]["avg"]) if pool else None


WF_GRIDS = {  # 기간별 반복 검증용 (조합 수를 줄여 과최적화·실행시간 억제)
    "score": dict(buy_th=[25, 40, 55], tp_atr=[1.0, 1.5, 2.0], tp2_atr=[3.0, 4.0],
                  sl_atr=[2.0, 3.0], max_hold=[5, 10], max_loss=[0.05, 0.07]),
    "pullback": dict(trend_ma=[60, 120], rsi_th=[35.0, 40.0, 45.0], rsi_confirm=[False, True],
                     rsi_exit=[55.0], tp_atr=[1.5, 2.0], tp2_atr=[4.0], sl_atr=[2.5],
                     max_loss=[0.05, 0.07], max_hold=[5, 10], market_filter=[False, True]),
}


def reversal_combos() -> list[Params]:
    out = []
    for sig, th in (("rsi", 25), ("rsi", 30), ("drop5", 8), ("drop5", 12),
                    ("ma20gap", 10), ("ma20gap", 15)):
        for rx, hold, ml, sp in itertools.product([50.0, 60.0], [3, 5, 10], [0.07, 0.10],
                                                  [False, True]):
            out.append(Params(strategy="reversal", rev_signal=sig, rev_th=float(th),
                              rsi_exit=rx, max_hold=hold, max_loss=ml, split=sp,
                              tp_atr=2.0, tp2_atr=4.0, sl_atr=3.0, market_filter=False))
    return out


def combos_for(strategy: str, grid: dict | None = None) -> list[Params]:
    if strategy == "reversal" and grid is None:
        return reversal_combos()
    grid = grid or WF_GRIDS[strategy]
    out = []
    for combo in itertools.product(*grid.values()):
        p = Params(**{**asdict(Params(strategy=strategy)), **dict(zip(grid.keys(), combo))})
        if not (p.split and p.tp2_atr <= p.tp_atr):
            out.append(p)
    return out


def walk_forward(datasets: dict[str, pd.DataFrame], strategy: str, n_folds: int = 4,
                 warm: float = 0.25, target_win: float = 60, min_train: int = 50,
                 grid: dict | None = None):
    """기간을 n_folds 개 구간으로 나눠, 각 구간 직전까지의 데이터로만 설정을 고르고
       그 구간에서 성적을 잰다 (확장형 walk-forward). 반환: (구간별 결과, 전체 실전가정 성적, 최종설정)."""
    dates = sorted(set().union(*[set(d.index) for d in datasets.values()]))
    edges = np.linspace(int(len(dates) * warm), len(dates), n_folds + 1).astype(int)
    bounds = [(dates[edges[f]], dates[edges[f + 1]] if edges[f + 1] < len(dates) else None)
              for f in range(n_folds)]
    sims = []
    for p in combos_for(strategy, grid):
        t = pd.DataFrame([x for code, d in datasets.items() for x in simulate(d, p, code)])
        sims.append((p, t))
    folds, oos, base_all = [], [], []
    for lo, hi in bounds:
        rows = []
        for p, t in sims:
            if t.empty:
                continue
            tr = t[t.entry_date < lo]
            te = t[(t.entry_date >= lo) & ((t.entry_date < hi) if hi is not None else True)]
            rows.append(dict(params=p, train=summarize(tr), test=summarize(te), te=te))
        best = select(rows, target_win, min_train)
        base = None
        if best is not None:
            oos.append(best["te"])
            # 같은 익절/손절/보유기간 규칙으로 '아무 날이나' 샀을 때 (시장 흐름만 탄 성적)
            q = Params(**{**asdict(best["params"]), "strategy": "always", "market_filter": False})
            bt = pd.DataFrame([x for code, d in datasets.items() for x in simulate(d, q, code)])
            if not bt.empty:
                bt = bt[(bt.entry_date >= lo) & ((bt.entry_date < hi) if hi is not None else True)]
                base = bt
                base_all.append(bt)
        folds.append(dict(start=lo, end=hi, best=best,
                          base=summarize(base) if base is not None else None))
    oos_t = pd.concat(oos) if oos else pd.DataFrame()
    base_t = pd.concat(base_all) if base_all else pd.DataFrame()
    final = select([dict(params=p, train=summarize(t)) for p, t in sims if not t.empty],
                   target_win, min_train)
    return folds, summarize(oos_t), final, len(sims), summarize(base_t)


def latest(d: pd.DataFrame, p: Params, i: int = -1) -> tuple[bool, bool, list[str]]:
    """i번째 날(기본 마지막) 장 마감 기준 (매수신호, 청산신호, 판단 근거). 시장필터 제외."""
    d = d.copy()
    if p.strategy == "score" and "score" not in d:
        d["score"] = np.nan
        for k in (len(d) + i - 1, len(d) + i):
            d.iloc[k, d.columns.get_loc("score")] = score_at(d, k).score
    ent, exs, _ = signals(d, p, use_market=False)
    r, prev = d.iloc[i], d.iloc[i - 1]
    if p.strategy == "pullback":
        ma = r[f"ma{p.trend_ma}"]
        why = [f"{'✅' if r.close > ma else '❌'} {p.trend_ma}일선 위 (종가 {r.close:,.0f} / "
               f"{p.trend_ma}일선 {ma:,.0f})",
               f"{'✅' if r.rsi <= p.rsi_th else '❌'} RSI {r.rsi:.1f} ≤ {p.rsi_th:g} (과매도)"]
        if p.rsi_confirm:
            why.append(f"{'✅' if r.rsi > prev.rsi else '❌'} RSI 반등 ({prev.rsi:.1f} → {r.rsi:.1f})")
        if exs[i]:
            why.append(f"⛔ RSI {r.rsi:.1f} ≥ {p.rsi_exit:g}: 보유 중이면 청산 신호")
    elif p.strategy == "reversal":
        cur = {"rsi": f"RSI {r.rsi:.1f}", "drop5": f"5일 수익률 {r.ret5:+.1f}%",
               "ma20gap": f"20일선 대비 {(r.close / r.ma20 - 1) * 100:+.1f}%"}[p.rev_signal]
        why = [f"{'✅' if ent[i] else '❌'} {REV_LABEL[p.rev_signal].format(th=p.rev_th)} (현재 {cur})"]
        if exs[i]:
            why.append(f"⛔ RSI {r.rsi:.1f} ≥ {p.rsi_exit:g}: 보유 중이면 청산 신호")
    else:
        why = [f"{'✅' if ent[i] else '❌'} 종합점수 {r.score:+.1f} ≥ {p.buy_th:g}"]
        if exs[i]:
            why.append(f"⛔ 점수 {r.score:+.1f} ≤ {p.exit_th:g}: 보유 중이면 청산 신호")
    return bool(ent[i]), bool(exs[i]), why
