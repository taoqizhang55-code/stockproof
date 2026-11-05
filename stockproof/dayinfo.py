"""
One trading day of one stock, for "click a candle and see what happened that day":
the bar, the move against the market, volume against normal, where it stood against the zones and averages,
any signal that fired, the news / announcements / reports around it, research-team calls and paper fills
made that day, and (labelled as hindsight) what the price did in the following weeks.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from stockproof import explain, quotes, ta


def _f(x, nd=4):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), nd)


def day_info(store, data_dir: str, ticker: str, day: str, lang: str = "zh") -> dict:
    zh = lang == "zh"
    bars = quotes.load_bars(data_dir, ticker).dropna(subset=["close"])
    if bars.empty:
        return {"error": "no prices"}
    d = pd.Timestamp(day)
    if d not in bars.index:                                    # a non-trading day: the last one before it
        before = bars.index[bars.index <= d]
        if not len(before):
            return {"error": "before the price history"}
        d = before[-1]
    i = bars.index.get_loc(d)
    b = bars.iloc[i]
    prev = float(bars["close"].iloc[i - 1]) if i else None
    ind = ta.indicators(bars.iloc[: i + 1])
    last = ind.iloc[-1]
    mv = quotes.moves(data_dir, ticker)
    m = mv.loc[d] if d in mv.index else None
    vol = bars["volume"].iloc[max(0, i - 20):i]
    vol_ratio = float(b["volume"] / vol.mean()) if "volume" in bars and len(vol) >= 5 and vol.mean() > 0 and pd.notna(b["volume"]) else None
    out = {"ticker": ticker, "date": d.date().isoformat(),
           "open": _f(b.get("open")), "high": _f(b.get("high")), "low": _f(b.get("low")), "close": _f(b["close"]),
           "volume": _f(b.get("volume"), 0), "prev_close": _f(prev),
           "ret": _f(b["close"] / prev - 1) if prev else None,
           "range": _f((b["high"] - b["low"]) / prev) if prev and pd.notna(b.get("high")) and pd.notna(b.get("low")) else None,
           "market_ret": _f(m["market"]) if m is not None else None, "excess": _f(m["excess"]) if m is not None else None,
           "z": _f(m["z"], 1) if m is not None else None, "unusual": bool(m["unusual"]) if m is not None else False,
           "vol_ratio": _f(vol_ratio, 2),
           "ma20": _f(last.get("ma20")), "ma60": _f(last.get("ma60"))}
    facts = []
    if out["ret"] is not None:
        facts.append((f"当天 {100 * out['ret']:+.2f}%" if zh else f"{100 * out['ret']:+.2f}% on the day")
                     + ((f"，大盘 {100 * out['market_ret']:+.2f}%，相对大盘 {100 * out['excess']:+.2f}%" if zh else
                         f", market {100 * out['market_ret']:+.2f}%, {100 * out['excess']:+.2f}% vs the market")
                        if out["market_ret"] is not None else ""))
    if out["unusual"]:
        facts.append(f"这是一次异常波动（相对大盘的涨跌是平时的 {abs(out['z'] or 0):.1f} 倍标准差）" if zh else
                     f"An unusual move ({abs(out['z'] or 0):.1f} standard deviations vs the market)")
    if vol_ratio:
        facts.append((f"成交量是前 20 天平均的 {vol_ratio:.1f} 倍" if zh else f"Volume {vol_ratio:.1f}x the 20-day average")
                     + (("（放量）" if zh else " (heavy)") if vol_ratio >= 1.8 else ("（缩量）" if zh else " (light)") if vol_ratio <= 0.6 else ""))
    for k, nm in (("ma20", "MA20"), ("ma60", "MA60")):
        if out[k]:
            facts.append((f"收盘在 {nm} {'之上' if out['close'] >= out[k] else '之下'}（{out[k]:.2f}）" if zh else
                          f"Closed {'above' if out['close'] >= out[k] else 'below'} {nm} ({out[k]:.2f})"))
    if prev:                                                   # zones known up to the day before
        for z in ta.zones(bars.iloc[:i]):
            if prev <= z["high"] < out["close"]:
                facts.append(f"收盘升破 {z['low']:.2f}–{z['high']:.2f} 区间" if zh else f"Closed above the {z['low']:.2f}–{z['high']:.2f} zone")
            elif prev >= z["low"] > out["close"]:
                facts.append(f"收盘跌破 {z['low']:.2f}–{z['high']:.2f} 区间" if zh else f"Closed below the {z['low']:.2f}–{z['high']:.2f} zone")
            elif out["low"] is not None and out["low"] <= z["high"] and out["high"] >= z["low"]:
                facts.append(f"盘中触及 {z['low']:.2f}–{z['high']:.2f} 区间" if zh else f"Touched the {z['low']:.2f}–{z['high']:.2f} zone")
    rules = ta.RULES if zh else ta.RULES_EN
    out["signals"] = [dict(s, rule=rules[s["kind"]]) for s in ta.signals(bars.iloc[: i + 1], days=1) if s["date"] == out["date"]]
    out["facts"] = facts
    try:
        out["evidence"] = explain.evidence(store, ticker, out["date"], before=3, after=1, limit=10)
    except Exception:
        out["evidence"] = []
    try:
        out["team_calls"] = [{"id": r[0], "stance": r[1], "confidence": r[2]} for r in store.conn.execute(
            "SELECT id, stance, confidence FROM team_calls WHERE ticker=? AND day=?", (ticker, out["date"]))]
    except Exception:
        out["team_calls"] = []
    try:
        out["paper_fills"] = [{"side": r[0], "shares": r[1], "price": r[2], "account": r[3]} for r in store.conn.execute(
            "SELECT o.side, f.shares, f.price, a.name FROM paper_fills f JOIN paper_orders o ON o.id=f.order_id "
            "JOIN paper_accounts a ON a.id=o.account WHERE o.ticker=? AND f.day=? AND f.status='filled'", (ticker, out["date"]))]
    except Exception:
        out["paper_fills"] = []
    after = {}
    for n in (5, 20, 60):
        if i + n < len(bars):
            after[str(n)] = _f(bars["close"].iloc[i + n] / b["close"] - 1)
    out["after"] = after
    out["after_note"] = ("事后看的涨跌（当天不可能知道），用来复盘，不是预测。" if zh else
                         "Hindsight (unknowable on the day): for review, not a forecast.")
    return json.loads(json.dumps(out, default=str))
