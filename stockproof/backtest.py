"""
Can the post-earnings drift be traded? An event-driven backtest with real-world frictions.

Rules (all decided with information available at the time):
  - Signal: SUE at the announcement. Long the stocks with SUE >= long_sue, (hypothetically)
    short those with SUE <= short_sue.
  - Entry: at the close of day 1 (the day after the announcement date), i.e. after the
    reaction window, so the backtest earns only the drift. If the stock can't be traded that day
    (suspended, or closed at the limit: limit-up blocks buying, limit-down blocks selling) the
    order waits up to `max_wait` days, then is dropped.
  - Exit: at the close `hold` trading days later; if the stock can't be sold then (suspended or
    limit-down for a long), it waits for the first day it can.
  - Portfolio: every open position has the same weight; days with no positions are in cash.
  - Costs, charged on the first and last day of each trade: commission on both sides, stamp duty
    on sales (China: 0.1%, 0.05% from 2023-08-28), and slippage on both sides.
  - Benchmark: the equal-weighted average of all stocks in the price file (same universe, so the
    survivorship of "today's index members" affects both sides alike).

Long-only excess return is the practical number for A-shares (shorting single stocks is limited and
expensive); the long-short result shows the size of the effect.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Costs:
    commission: float = 0.00025       # each side
    slippage: float = 0.001           # each side: spread + market impact for large caps
    stamp_duty: float = 0.001         # on sales; China halved it on 2023-08-28
    stamp_duty_cut: str | None = "2023-08-28"
    stamp_duty_after: float = 0.0005

    def buy(self, day) -> float:
        return self.commission + self.slippage

    def sell(self, day) -> float:
        duty = self.stamp_duty
        if self.stamp_duty_cut and pd.Timestamp(day) >= pd.Timestamp(self.stamp_duty_cut):
            duty = self.stamp_duty_after
        return self.commission + self.slippage + duty


COSTS = {"cn": Costs(),
         "us": Costs(commission=0.0, slippage=0.0005, stamp_duty=0.0, stamp_duty_cut=None,
                     stamp_duty_after=0.0)}


def price_limit(ticker: str, day) -> float | None:
    """Daily price limit for an A-share (None = no limit, e.g. US / HK)."""
    if not ticker.endswith((".SH", ".SZ", ".BJ")):
        return None
    code = ticker[:6]
    if ticker.endswith(".BJ"):
        return 0.30
    if code.startswith("688"):
        return 0.20                                   # STAR market, since its start in 2019
    if code.startswith(("300", "301")) and pd.Timestamp(day) >= pd.Timestamp("2020-08-24"):
        return 0.20                                   # ChiNext reform
    return 0.10


def tradable_masks(prices: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(can_buy, can_sell, returns) as T x N arrays. A day with no price is a suspension.
    A close within 0.3% of the limit is treated as locked at the limit (no fills on that side)."""
    ret = prices.pct_change(fill_method=None).to_numpy(dtype=float)
    has = prices.notna().to_numpy()
    up = np.zeros_like(has)
    down = np.zeros_like(has)
    days = prices.index
    for j, tk in enumerate(prices.columns):
        lim_old, lim_new = price_limit(tk, days[0]), price_limit(tk, days[-1])
        if lim_old is None:
            continue
        lim = np.array([price_limit(tk, d) for d in days]) if lim_old != lim_new else lim_old
        r = ret[:, j]
        up[:, j] = r >= lim - 0.003
        down[:, j] = r <= -(lim - 0.003)
    up &= ~np.isnan(ret)
    down &= ~np.isnan(ret)
    return has & ~up, has & ~down, ret


def make_trades(events: pd.DataFrame, prices: pd.DataFrame, long_sue: float, short_sue: float,
                hold: int, entry_lag: int = 1, max_wait: int = 5, max_exit_wait: int = 20) -> pd.DataFrame:
    """One row per trade: ticker, side (+1/-1), entry and exit positions in the price index."""
    days = prices.index
    col = {tk: j for j, tk in enumerate(prices.columns)}
    can_buy, can_sell, _ = tradable_masks(prices)
    rows = []
    ev = events.dropna(subset=["sue", "day0"])
    ev = ev[(ev["sue"] >= long_sue) | (ev["sue"] <= short_sue)]
    for _, e in ev.iterrows():
        j = col.get(e["ticker"])
        if j is None:
            continue
        side = 1 if e["sue"] >= long_sue else -1
        i0 = int(days.searchsorted(pd.Timestamp(e["day0"])))
        open_ok = can_buy if side == 1 else can_sell          # opening a short = selling
        close_ok = can_sell if side == 1 else can_buy
        entry = None
        for i in range(i0 + entry_lag, min(i0 + entry_lag + max_wait + 1, len(days))):
            if open_ok[i, j]:
                entry = i
                break
        if entry is None:
            continue
        exit_ = None
        for i in range(entry + hold, min(entry + hold + max_exit_wait + 1, len(days))):
            if close_ok[i, j]:
                exit_ = i
                break
        if exit_ is None:
            if entry + hold < len(days):
                continue                                       # stuck for weeks: leave it out
            exit_ = len(days) - 1                              # still open today: mark to market
        rows.append({"ticker": e["ticker"], "side": side, "sue": e["sue"], "day0": e["day0"],
                     "entry": entry, "exit": exit_, "entry_date": days[entry].date().isoformat(),
                     "exit_date": days[exit_].date().isoformat(), "open": entry + hold >= len(days)})
    return pd.DataFrame(rows)


def run(events: pd.DataFrame, prices: pd.DataFrame, market: str = "cn", long_sue: float = 2.0,
        short_sue: float = -2.0, hold: int = 60, costs: Costs | None = None, slots: int = 20,
        entry_lag: int = 1) -> dict:
    """Daily returns of the long book, short book, long-short and the benchmark, plus trades."""
    from stockproof.research import BENCHMARKS
    costs = costs or COSTS.get(market, Costs())
    stocks = prices.drop(columns=[c for c in BENCHMARKS if c in prices.columns])
    days = stocks.index
    _, _, ret = tradable_masks(stocks)
    ret0 = np.nan_to_num(ret)
    bench = pd.DataFrame(ret, index=days).mean(axis=1, skipna=True).fillna(0.0)
    trades = make_trades(events, stocks, long_sue, short_sue, hold, entry_lag=entry_lag)
    T = len(days)
    out = {"days": days, "trades": trades, "bench": bench}
    for side, name in ((1, "long"), (-1, "short")):
        s = np.zeros(T)
        n = np.zeros(T)
        net = []
        if len(trades):
            col = {tk: j for j, tk in enumerate(stocks.columns)}
            for _, t in trades[trades["side"] == side].iterrows():
                j, a, b = col[t["ticker"]], int(t["entry"]), int(t["exit"])
                if b <= a:
                    continue
                r = ret0[a + 1:b + 1, j].copy()
                r[0] -= costs.buy(days[a]) if side == 1 else costs.sell(days[a])
                if not t["open"]:
                    r[-1] -= costs.sell(days[b]) if side == 1 else costs.buy(days[b])
                s[a + 1:b + 1] += r
                n[a + 1:b + 1] += 1
                gross = float(np.prod(1 + ret0[a + 1:b + 1, j]) - 1)
                bench_ret = float(np.prod(1 + bench.to_numpy()[a + 1:b + 1]) - 1)
                cost = (costs.buy(days[a]) + costs.sell(days[b])) if not t["open"] else costs.buy(days[a])
                net.append(side * (gross - bench_ret) - cost)
        # Capital is split into `slots` equal parts; parts without a position hold the market
        # (an index fund). With more positions than slots, all positions share the capital equally.
        # Without this, a day with one open trade would put everything into one stock.
        k = np.maximum(n, slots)
        b = bench.to_numpy()
        book = pd.Series(np.where(n > 0, (s + (k - n) * b) / k, b), index=days)
        out[name] = book
        out[name + "_n"] = pd.Series(n, index=days)
        out[name + "_trade_excess"] = net
    # a short position earns the negative of the stock: long-short = long book minus short book
    out["long_excess"] = out["long"] - bench
    out["long_short"] = out["long"] - out["short"]          # the market parts cancel out
    out["slots"] = slots
    return out


def _drawdown(r: pd.Series) -> float:
    curve = (1 + r).cumprod()
    return float((curve / curve.cummax() - 1).min()) if len(curve) else float("nan")


def stats(r: pd.Series, active: pd.Series | None = None) -> dict:
    """Annualized figures over the days the strategy was invested (or all days)."""
    x = r[active > 0] if active is not None else r
    if len(x) < 20:
        return {"days": len(x)}
    ann = (1 + x).prod() ** (252 / len(x)) - 1
    vol = x.std(ddof=1) * math.sqrt(252)
    t = x.mean() / (x.std(ddof=1) / math.sqrt(len(x))) if x.std(ddof=1) > 0 else float("nan")
    return {"days": len(x), "ann_return": float(ann), "ann_vol": float(vol),
            "sharpe": float(x.mean() / x.std(ddof=1) * math.sqrt(252)) if x.std(ddof=1) > 0 else float("nan"),
            "t": float(t), "max_dd": _drawdown(x)}


def by_year(r: pd.Series, active: pd.Series | None = None) -> pd.DataFrame:
    x = r if active is None else r.where(active > 0, 0.0)
    g = (1 + x).groupby(x.index.year).prod() - 1
    return g.rename("return").to_frame()


def summarize(bt: dict) -> dict:
    """Numbers for the report."""
    tr = bt["trades"]
    out = {"n_trades": len(tr), "n_long": int((tr["side"] == 1).sum()) if len(tr) else 0,
           "n_short": int((tr["side"] == -1).sum()) if len(tr) else 0}
    if not len(tr):
        return out
    out["start"], out["end"] = tr["entry_date"].min(), tr["exit_date"].max()
    live = pd.Series(0, index=bt["long_n"].index)
    first = bt["long_n"].to_numpy().nonzero()[0]
    if len(first):
        live.iloc[first[0]:] = 1                              # from the first trade on
    out["long_excess"] = stats(bt["long_excess"], live)
    out["long"] = stats(bt["long"], live)
    out["bench"] = stats(bt["bench"], live)
    out["long_short"] = stats(bt["long_short"], live)
    out["avg_positions"] = float(bt["long_n"][live > 0].mean())
    out["slots"] = bt.get("slots")
    for side in ("long", "short"):
        net = pd.Series(bt[side + "_trade_excess"], dtype=float)
        if len(net):
            out[side + "_trade"] = {"n": len(net), "mean": float(net.mean()), "win": float((net > 0).mean()),
                                    "t": float(net.mean() / (net.std(ddof=1) / math.sqrt(len(net))))
                                    if len(net) > 1 and net.std(ddof=1) > 0 else float("nan")}
    yrs = pd.concat([by_year(bt["long_excess"], live).rename(columns={"return": "long_excess"}),
                     by_year(bt["long_short"], live).rename(columns={"return": "long_short"})], axis=1)
    yrs = yrs[yrs.index >= bt["long_n"].index[first[0]].year] if len(first) else yrs
    out["years"] = yrs
    curve = pd.DataFrame({"long_excess": (1 + bt["long_excess"]).cumprod(),
                          "long_short": (1 + bt["long_short"]).cumprod()})
    first = bt["long_n"].to_numpy().nonzero()[0]
    out["curve"] = curve.iloc[first[0]:] if len(first) else curve
    return out


def sweep(events: pd.DataFrame, prices: pd.DataFrame, market: str,
          thresholds=(0.5, 1.0, 2.0), holds=(20, 60)) -> pd.DataFrame:
    """Robustness: the same backtest with other SUE cut-offs and holding periods."""
    rows = []
    for th in thresholds:
        for h in holds:
            s = summarize(run(events, prices, market, th, -th, h))
            le, lt = s.get("long_excess", {}), s.get("long_trade", {})
            rows.append({"sue": th, "hold": h, "trades": s.get("n_long", 0),
                         "ann_excess": le.get("ann_return"), "t": le.get("t"),
                         "per_trade": lt.get("mean"), "win": lt.get("win"),
                         "ls_ann": s.get("long_short", {}).get("ann_return")})
    return pd.DataFrame(rows)


def to_json(s: dict, params: dict) -> dict:
    """A JSON-safe copy of summarize() for saving next to the research results."""
    out = {k: v for k, v in s.items() if k not in ("years", "curve")}
    out["params"] = params
    if "years" in s:
        y = s["years"]
        out["years"] = [{"year": int(i), **{c: (None if pd.isna(v) else float(v)) for c, v in r.items()}}
                        for i, r in y.iterrows()]
    if "curve" in s:
        c = s["curve"].groupby(pd.Grouper(freq="W")).tail(1)        # last real day of each week
        out["curve"] = {"dates": [d.date().isoformat() for d in c.index],
                        "long_excess": [round(float(v), 5) for v in c["long_excess"]],
                        "long_short": [round(float(v), 5) for v in c["long_short"]]}
    return out


def full(events: pd.DataFrame, prices: pd.DataFrame, market: str, long_sue: float = 2.0,
         hold: int = 60) -> dict:
    """Main backtest + robustness sweep, ready for the report (JSON-safe)."""
    s = summarize(run(events, prices, market, long_sue, -long_sue, hold))
    free = Costs(commission=0.0, slippage=0.0, stamp_duty=0.0, stamp_duty_cut=None, stamp_duty_after=0.0)
    g = summarize(run(events, prices, market, long_sue, -long_sue, hold, costs=free))
    s["long_excess_gross"] = g.get("long_excess", {})
    s["long_short_gross"] = g.get("long_short", {})
    out = to_json(s, {"long_sue": long_sue, "short_sue": -long_sue, "hold": hold, "market": market,
                      "costs": COSTS.get(market, Costs()).__dict__})
    sw = sweep(events, prices, market)
    out["sweep"] = [{k: (None if (isinstance(v, float) and math.isnan(v)) else v) for k, v in r.items()}
                    for r in sw.to_dict("records")]
    return out
