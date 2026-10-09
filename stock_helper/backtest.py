"""점수 전략 백테스트 + 파라미터 최적화.

매매 규칙 (실시간 모의매매와 동일)
  - 진입: 장 마감 점수 >= buy_th  ->  다음날 시가 매수
  - 손절: 진입가 - sl_atr * ATR  (장중 터치, 갭하락이면 시가)
  - 익절: 진입가 + tp_atr * ATR  (장중 터치, 갭상승이면 시가)
  - 청산: 장 마감 점수 <= exit_th 또는 보유일 >= max_hold -> 다음날 시가 매도
  - 비용: 왕복 cost (수수료 + 증권거래세, 기본 0.25%)
  같은 날 손절·익절 모두 닿으면 보수적으로 '손절' 처리.

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
from signals import score_at

PARAMS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "best_params.json")


@dataclass
class Params:
    buy_th: float = 25
    exit_th: float = -10
    tp_atr: float = 4.0
    sl_atr: float = 2.0
    max_hold: int = 10
    cost: float = 0.0025

    def save(self, path: str = PARAMS_PATH, extra: dict | None = None):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({**asdict(self), **(extra or {})}, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str = PARAMS_PATH) -> "Params":
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return cls(**{k: raw[k] for k in asdict(cls()) if k in raw})


def prepare(raw: pd.DataFrame, start: int = 60) -> pd.DataFrame:
    """지표 + 일별 점수(score) 컬럼을 미리 계산 (파라미터 탐색 시 재사용)."""
    d = indicators.add_all(raw)
    sc = np.full(len(d), np.nan)
    for i in range(start, len(d)):
        sc[i] = score_at(d, i).score
    d["score"] = sc
    return d


def simulate(d: pd.DataFrame, p: Params, code: str = "") -> list[dict]:
    o, h, l, c = (d[k].to_numpy() for k in ("open", "high", "low", "close"))
    atr, sc, idx = d["atr"].to_numpy(), d["score"].to_numpy(), d.index
    n, i, trades = len(d), 0, []
    while i < n - 1:
        if not (sc[i] >= p.buy_th) or np.isnan(atr[i]):
            i += 1
            continue
        j = i + 1                      # 진입일
        entry = o[j]
        stop, target = entry - p.sl_atr * atr[i], entry + p.tp_atr * atr[i]
        exit_px = why = None
        k = j
        while k < n:
            if l[k] <= stop:
                exit_px, why, ex = min(o[k], stop), "손절", k
            elif h[k] >= target:
                exit_px, why, ex = max(o[k], target), "익절", k
            elif sc[k] <= p.exit_th or k - j + 1 >= p.max_hold:
                if k + 1 < n:
                    exit_px, ex = o[k + 1], k + 1
                    why = "점수하락" if sc[k] <= p.exit_th else "기간만료"
            if exit_px is not None:
                break
            k += 1
        if exit_px is None:            # 데이터 끝까지 보유 중 -> 집계 제외
            break
        trades.append(dict(code=code, entry_date=idx[j], entry=entry, exit_date=idx[ex],
                           exit=exit_px, ret=(exit_px / entry - 1 - p.cost) * 100,
                           reason=why, held=ex - j + 1, score=sc[i]))
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


GRID = dict(buy_th=[25, 35, 45, 55], tp_atr=[0.5, 1.0, 1.5, 2.0, 3.0],
            sl_atr=[1.0, 1.5, 2.0, 3.0], max_hold=[3, 5, 10])


def split_date(datasets: dict[str, pd.DataFrame], ratio: float) -> pd.Timestamp:
    dates = sorted(set().union(*[set(d.index) for d in datasets.values()]))
    return dates[int(len(dates) * ratio)]


def optimize(datasets: dict[str, pd.DataFrame], target_win: float = 80, ratio: float = 0.7,
             min_train: int = 50, grid: dict | None = None, base: Params | None = None):
    """학습 구간에서 '기대값(평균수익) > 0, PF > 1' 조합 중
       승률 target_win 이상이면 그 중 평균수익 최대, 없으면 승률 최대를 선택."""
    grid, base = grid or GRID, base or Params()
    cut = split_date(datasets, ratio)
    rows = []
    for combo in itertools.product(*grid.values()):
        p = Params(**{**asdict(base), **dict(zip(grid.keys(), combo))})
        t = pd.DataFrame([x for code, d in datasets.items() for x in simulate(d, p, code)])
        tr = summarize(t[t.entry_date < cut]) if len(t) else summarize([])
        te = summarize(t[t.entry_date >= cut]) if len(t) else summarize([])
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
