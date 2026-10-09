"""점수 전략 백테스트 + 파라미터 최적화.

매매 규칙 (실시간 모의매매와 동일)
  - 진입: 장 마감 점수 >= buy_th 이고 시장 필터 통과(B) -> 다음날 시가 매수
  - 손절: 진입가 - sl_atr * ATR  (장중 터치, 갭하락이면 시가)
  - 1차 익절(C): 진입가 + tp_atr * ATR 터치 -> 절반 매도, 남은 절반 손절가를 '본전'으로 상향
  - 2차 익절: 진입가 + tp2_atr * ATR 터치 -> 나머지 매도
  - 청산: 장 마감 점수 <= exit_th 또는 보유일 >= max_hold -> 다음날 시가 매도
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
                      if k in raw and isinstance(raw[k], (int, float, bool))})


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


def simulate(d: pd.DataFrame, p: Params, code: str = "") -> list[dict]:
    o, h, l, c = (d[k].to_numpy() for k in ("open", "high", "low", "close"))
    atr, sc, idx = d["atr"].to_numpy(), d["score"].to_numpy(), d.index
    n = len(d)
    mk = d["mkt_ok"].to_numpy(bool) if p.market_filter and "mkt_ok" in d else np.ones(n, bool)
    i, trades = 0, []
    while i < n - 1:
        if not (sc[i] >= p.buy_th) or np.isnan(atr[i]) or not mk[i]:
            i += 1
            continue
        j = i + 1                      # 진입일
        entry, a = o[j], atr[i]
        if not entry > 0:              # 데이터 이상(시가 0) -> 건너뜀
            i += 1
            continue
        stop, t1, t2 = entry - p.sl_atr * a, entry + p.tp_atr * a, entry + p.tp2_atr * a
        be = entry * (1 + p.cost)      # 본전 스탑
        half = None                    # 1차 익절한 절반의 수익률
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
            if exit_px is None and (sc[k] <= p.exit_th or k - j + 1 >= p.max_hold) and k + 1 < n:
                exit_px, ex = o[k + 1], k + 1
                why = ("1차익절+" if half is not None else "") + \
                      ("점수하락" if sc[k] <= p.exit_th else "기간만료")
            if exit_px is not None:
                break
            k += 1
        if exit_px is None:            # 데이터 끝까지 보유 중 -> 집계 제외
            break
        r2 = exit_px / entry - 1
        ret = (r2 if half is None else 0.5 * half + 0.5 * r2) - p.cost
        trades.append(dict(code=code, entry_date=idx[j], entry=entry, exit_date=idx[ex],
                           exit=exit_px, ret=ret * 100, reason=why, held=ex - j + 1,
                           score=sc[i]))
        i = ex                         # 청산일 종가부터 다시 신호 탐색
    return trades


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


GRID = dict(buy_th=[25, 35, 45, 55], tp_atr=[0.5, 1.0, 1.5, 2.0],
            tp2_atr=[2.0, 3.0, 4.0], sl_atr=[1.0, 1.5, 2.0, 3.0], max_hold=[3, 5, 10])


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


def optimize(datasets: dict[str, pd.DataFrame], target_win: float = 80, ratio: float = 0.7,
             min_train: int = 50, grid: dict | None = None, base: Params | None = None):
    """학습 구간에서 '기대값(평균수익) > 0, PF > 1' 조합 중
       승률 target_win 이상이면 그 중 평균수익 최대, 없으면 승률 최대를 선택."""
    grid, base = grid or GRID, base or Params()
    cut = split_date(datasets, ratio)
    rows = []
    for combo in itertools.product(*grid.values()):
        p = Params(**{**asdict(base), **dict(zip(grid.keys(), combo))})
        if p.split and p.tp2_atr <= p.tp_atr:
            continue
        tr, te = evaluate(datasets, p, cut)
        rows.append(dict(params=p, train=tr, test=te))
    ok = [r for r in rows if r["train"]["n"] >= min_train and r["train"]["avg"] > 0
          and r["train"]["pf"] > 1]
    hit = [r for r in ok if r["train"]["win"] >= target_win]
    if hit:
        best = max(hit, key=lambda r: r["train"]["avg"])
    elif ok:
        best = max(ok, key=lambda r: (r["train"]["win"], r["train"]["avg"]))
    else:
        best = None
    return best, rows, cut
