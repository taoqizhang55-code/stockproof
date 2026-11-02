"""
Technical analysis on daily bars: moving averages, MACD, RSI, Bollinger bands, ATR, volume ratio,
support/resistance zones and chart signals (breakouts, breakdowns, pullbacks, crosses).

Everything is computed from prices only, with the rule written next to each signal, so the AI team
and the charts can cite exact numbers. Signals describe what the chart did; they are not forecasts.
The lab can test any of them on history (stockproof lab).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- indicators
def indicators(bars: pd.DataFrame) -> pd.DataFrame:
    """bars: columns close/open/high/low/volume (open/high/low/volume may be NaN)."""
    df = bars.copy()
    c = df["close"]
    hi = df["high"].fillna(c)
    lo = df["low"].fillna(c)
    for n in (5, 10, 20, 60):
        df[f"ma{n}"] = c.rolling(n).mean()
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    down = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    df["rsi"] = (100 - 100 / (1 + rs)).where(down > 0, np.where(up > 0, 100.0, 50.0))
    mid, sd = c.rolling(20).mean(), c.rolling(20).std()
    df["boll_mid"], df["boll_up"], df["boll_low"] = mid, mid + 2 * sd, mid - 2 * sd
    tr = pd.concat([hi - lo, (hi - c.shift()).abs(), (lo - c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    v = df["volume"]
    df["vol_ratio"] = v / v.rolling(20).mean().shift(1)
    return df


# ---------------------------------------------------------------- support / resistance
def pivots(bars: pd.DataFrame, k: int = 5) -> list[dict]:
    """Swing highs/lows: a bar whose high (low) is the highest (lowest) of the k bars on each side.
    A pivot is only known k bars later, so each carries its `confirmed` date. Abnormal bars (a range of
    more than 4 × ATR, e.g. a gap after a suspension or a limit-move day) are not used as pivots."""
    c = bars["close"]
    hi = bars["high"].fillna(c).to_numpy()
    lo = bars["low"].fillna(c).to_numpy()
    atr = indicators(bars)["atr"].to_numpy()
    out = []
    for i in range(k, len(bars) - k):
        if not np.isnan(atr[i - 1] if i else np.nan) and hi[i] - lo[i] > 4 * atr[i - 1]:
            continue
        conf = bars.index[i + k]
        if hi[i] == hi[i - k:i + k + 1].max():
            out.append({"i": i, "date": bars.index[i], "confirmed": conf, "price": float(hi[i]), "kind": "high"})
        if lo[i] == lo[i - k:i + k + 1].min():
            out.append({"i": i, "date": bars.index[i], "confirmed": conf, "price": float(lo[i]), "kind": "low"})
    return out


def zones(bars: pd.DataFrame, lookback: int = 250, k: int = 5, min_touches: int = 2,
          max_zones: int = 6) -> list[dict]:
    """Price zones where the stock turned at least `min_touches` times in the last `lookback` days.
    Swing points closer than 0.6 × ATR(14) (or 1.5% of price) are merged into one zone."""
    b = bars.iloc[-lookback:]
    if len(b) < 2 * k + 5:
        return []
    ind = indicators(b)
    last = float(b["close"].iloc[-1])
    atr = ind["atr"].iloc[-1]
    tol = 0.6 * float(atr) if pd.notna(atr) and atr > 0 else 0.015 * last
    pts = sorted(pivots(b, k), key=lambda p: p["price"])
    groups: list[list[dict]] = []
    for p in pts:
        if groups and p["price"] - groups[-1][-1]["price"] <= tol:
            groups[-1].append(p)
        else:
            groups.append([p])
    out = []
    for g in groups:
        if len(g) < min_touches:
            continue
        prices = [p["price"] for p in g]
        lo_, hi_ = min(prices), max(prices)
        if hi_ - lo_ < tol * 0.5:                                  # give thin zones some width
            mid = (hi_ + lo_) / 2
            lo_, hi_ = mid - tol * 0.25, mid + tol * 0.25
        dates = sorted(p["date"] for p in g)
        conf = sorted(p["confirmed"] for p in g)
        z = {"low": round(lo_, 4), "high": round(hi_, 4), "mid": round((lo_ + hi_) / 2, 4), "touches": len(g),
             "first": dates[0].date().isoformat(), "last": dates[-1].date().isoformat(),
             "since": conf[min_touches - 1].date().isoformat()}      # the day the zone became known
        z["kind"] = "support" if z["high"] < last else ("resistance" if z["low"] > last else "inside")
        z["distance"] = round(z["mid"] / last - 1, 4)
        out.append(z)
    out = [z for z in out if abs(z["distance"]) <= 0.35]
    out.sort(key=lambda z: (-z["touches"], abs(z["distance"])))
    return sorted(out[:max_zones], key=lambda z: z["mid"])


# ---------------------------------------------------------------- signals
RULES = {
    "breakout": "收盘价突破阻力区上沿，且成交量 ≥ 20 日均量的 1.5 倍",
    "breakdown": "收盘价跌破支撑区下沿",
    "pullback": "前 10 日内突破过某区域，现在回落到该区域内但收盘仍在区域下沿之上",
    "golden_cross": "5 日均线上穿 20 日均线",
    "death_cross": "5 日均线下穿 20 日均线",
    "macd_up": "MACD 线上穿信号线",
    "macd_down": "MACD 线下穿信号线",
    "rsi_high": "RSI(14) ≥ 70（短期涨得多）",
    "rsi_low": "RSI(14) ≤ 30（短期跌得多）",
    "boll_up": "收盘价高于布林带上轨",
    "boll_low": "收盘价低于布林带下轨",
    "volume_spike": "成交量 ≥ 20 日均量的 2 倍",
}
RULES_EN = {
    "breakout": "close above a resistance zone's top on volume ≥ 1.5× the 20-day average",
    "breakdown": "close below a support zone's bottom",
    "pullback": "broke above a zone within 10 days, now back inside it but closing above its bottom",
    "golden_cross": "5-day MA crosses above the 20-day MA", "death_cross": "5-day MA crosses below the 20-day MA",
    "macd_up": "MACD crosses above its signal line", "macd_down": "MACD crosses below its signal line",
    "rsi_high": "RSI(14) ≥ 70", "rsi_low": "RSI(14) ≤ 30", "boll_up": "close above the upper Bollinger band",
    "boll_low": "close below the lower Bollinger band", "volume_spike": "volume ≥ 2× the 20-day average",
}
CHART_KINDS = {"breakout", "breakdown", "pullback", "golden_cross", "death_cross"}   # drawn on the chart
BULLISH = {"breakout", "pullback", "golden_cross", "macd_up"}
BEARISH = {"breakdown", "death_cross", "macd_down"}
# rsi/bollinger extremes and volume spikes are neutral: they say the move was large, not which way comes next


def direction(kind: str) -> str:
    return "bullish" if kind in BULLISH else ("bearish" if kind in BEARISH else "neutral")


def _crossed(a: pd.Series, b: pd.Series, i: int, up: bool) -> bool:
    if i < 1 or any(pd.isna(x) for x in (a.iloc[i], b.iloc[i], a.iloc[i - 1], b.iloc[i - 1])):
        return False
    return (a.iloc[i - 1] <= b.iloc[i - 1] and a.iloc[i] > b.iloc[i]) if up else \
        (a.iloc[i - 1] >= b.iloc[i - 1] and a.iloc[i] < b.iloc[i])


def signals(bars: pd.DataFrame, days: int = 5, zs: list[dict] | None = None) -> list[dict]:
    """Signals on each of the last `days` bars, newest first."""
    if len(bars) < 30:
        return []
    ind = indicators(bars)
    zs = zones(bars.iloc[:-days]) if zs is None else zs             # zones known before the window: no peeking
    out = []
    n = len(ind)
    for i in range(max(1, n - days), n):
        row, prev = ind.iloc[i], ind.iloc[i - 1]
        day = ind.index[i].date().isoformat()
        c, pc = row["close"], prev["close"]

        def add(kind, **extra):
            out.append({"date": day, "kind": kind, "bullish": kind in BULLISH, "direction": direction(kind),
                        "close": round(float(c), 4), **extra})
        vr = row["vol_ratio"]
        for z in zs:
            if pc <= z["high"] < c and (pd.isna(vr) or vr >= 1.5):
                add("breakout", zone=[z["low"], z["high"]], vol_ratio=None if pd.isna(vr) else round(float(vr), 2))
            if pc >= z["low"] > c:
                add("breakdown", zone=[z["low"], z["high"]])
            recent = ind["close"].iloc[max(0, i - 10):i]
            atr = row["atr"]
            calm = pd.isna(atr) or abs(c - pc) <= 1.5 * float(atr)          # a retest, not a crash through
            if len(recent) and (recent > z["high"]).any() and z["low"] <= c <= z["high"] and pc > z["high"] and calm:
                add("pullback", zone=[z["low"], z["high"]])
        if _crossed(ind["ma5"], ind["ma20"], i, True):
            add("golden_cross")
        if _crossed(ind["ma5"], ind["ma20"], i, False):
            add("death_cross")
        if _crossed(ind["macd"], ind["macd_signal"], i, True):
            add("macd_up")
        if _crossed(ind["macd"], ind["macd_signal"], i, False):
            add("macd_down")
        if pd.notna(row["rsi"]) and row["rsi"] >= 70 and not (pd.notna(prev["rsi"]) and prev["rsi"] >= 70):
            add("rsi_high", rsi=round(float(row["rsi"]), 1))
        if pd.notna(row["rsi"]) and row["rsi"] <= 30 and not (pd.notna(prev["rsi"]) and prev["rsi"] <= 30):
            add("rsi_low", rsi=round(float(row["rsi"]), 1))
        if pd.notna(row["boll_up"]) and c > row["boll_up"]:
            add("boll_up")
        if pd.notna(row["boll_low"]) and c < row["boll_low"]:
            add("boll_low")
        if pd.notna(vr) and vr >= 2:
            add("volume_spike", vol_ratio=round(float(vr), 2))
    broke = {x["date"] for x in out if x["kind"] == "breakdown"}
    out = [x for x in out if not (x["kind"] == "pullback" and x["date"] in broke)]
    return sorted(out, key=lambda x: x["date"], reverse=True)


def trend(ind: pd.DataFrame) -> dict:
    """Plain trend facts: price vs moving averages and their direction."""
    r = ind.iloc[-1]

    def f(x):
        return None if pd.isna(x) else round(float(x), 4)

    def slope(col, n=10):
        s = ind[col].dropna()
        return None if len(s) <= n else round(float(s.iloc[-1] / s.iloc[-1 - n] - 1), 4)
    above = [n for n in (5, 10, 20, 60) if pd.notna(r[f"ma{n}"]) and r["close"] > r[f"ma{n}"]]
    ma_ok = [pd.notna(r[f"ma{n}"]) for n in (5, 10, 20, 60)]
    if all(ma_ok) and r["ma5"] > r["ma10"] > r["ma20"] > r["ma60"] and r["close"] > r["ma20"]:
        state = "up"                                                   # 多头排列
    elif all(ma_ok) and r["ma5"] < r["ma10"] < r["ma20"] < r["ma60"] and r["close"] < r["ma20"]:
        state = "down"                                                 # 空头排列
    else:
        state = "mixed"
    return {"state": state, "above_ma": above, "ma20_slope_10d": slope("ma20"), "ma60_slope_10d": slope("ma60"),
            "rsi": f(r["rsi"]), "macd_hist": f(r["macd_hist"]), "atr_pct": f(r["atr"] / r["close"]) if pd.notna(r["atr"]) else None}


def analyze(bars: pd.DataFrame, lang: str = "zh") -> dict:
    """Everything the chart and the technical analyst need, as numbers and short facts."""
    bars = bars.dropna(subset=["close"])
    if len(bars) < 30:
        return {"error": "not enough price history (need 30 trading days)"}
    ind = indicators(bars)
    zs = zones(bars)
    last = ind.iloc[-1]
    rules = RULES if lang == "zh" else RULES_EN
    sig = signals(bars, days=5)
    hi52 = bars["high"].fillna(bars["close"]).iloc[-250:].max()
    lo52 = bars["low"].fillna(bars["close"]).iloc[-250:].min()
    sup = [z for z in zs if z["kind"] == "support"]
    res = [z for z in zs if z["kind"] == "resistance"]
    return {
        "date": ind.index[-1].date().isoformat(), "close": round(float(last["close"]), 4),
        "has_ohlc": bool(bars["high"].notna().any()),
        "trend": trend(ind), "zones": zs,
        "nearest_support": max(sup, key=lambda z: z["mid"]) if sup else None,
        "nearest_resistance": min(res, key=lambda z: z["mid"]) if res else None,
        "high_52w": round(float(hi52), 4), "low_52w": round(float(lo52), 4),
        "from_high_52w": round(float(last["close"] / hi52 - 1), 4),
        "signals": [dict(s, rule=rules[s["kind"]]) for s in sig],
        "note": ("技术信号只描述价格走势，不是预测；可以在实验室里检验它们历史上是否有效。" if lang == "zh" else
                 "Technical signals describe what the price did; they are not forecasts. Test them in the lab."),
    }


def chart_data(bars: pd.DataFrame, days: int = 160) -> dict:
    """Compact series for the candlestick chart (dashboard and reports)."""
    bars = bars.dropna(subset=["close"])
    ind = indicators(bars).iloc[-days:]

    def col(name, nd=4):
        return [None if (x is None or (isinstance(x, float) and math.isnan(x))) else round(float(x), nd)
                for x in ind[name].tolist()]
    return {"dates": [d.date().isoformat() for d in ind.index], "open": col("open"), "high": col("high"),
            "low": col("low"), "close": col("close"), "volume": col("volume", 0),
            "ma5": col("ma5"), "ma20": col("ma20"), "ma60": col("ma60"),
            "zones": zones(bars),
            "signals": [x for x in signals(bars, days=min(days, 60)) if x["kind"] in CHART_KINDS]}
