"""
Server-side candlestick chart as a standalone SVG: candles, MA20 / MA60, support / resistance zones,
volume, the last close. Used where the browser's own chart can't run: chat answers in DeepSeek
Harness (as an image URL served by the local dashboard), reports and shareable cards.
"""

from __future__ import annotations

import html
import math

import pandas as pd

from stockproof import ta

W, H = 1040, 520
PAD_L, PAD_R, PAD_T = 56, 250, 56
PRICE_H, VOL_H, GAP = 330, 70, 18


def _fmt(x: float) -> str:
    return f"{x:.2f}" if x >= 1 else f"{x:.3f}"


def render(bars: pd.DataFrame, ticker: str, name: str = "", lang: str = "zh", days: int = 120) -> str:
    zh = lang == "zh"
    b = bars.dropna(subset=["close"])
    if len(b) < 20:
        return _empty(ticker, "价格数据不足" if zh else "not enough price history")
    ind = ta.indicators(b).iloc[-days:]
    zs_all = ta.zones(b)
    last = float(ind["close"].iloc[-1])
    zs = [z for z in zs_all if abs(z["mid"] / last - 1) <= 0.25]
    o = ind["open"].fillna(ind["close"])
    h = ind["high"].fillna(ind["close"])
    lo = ind["low"].fillna(ind["close"])
    c = ind["close"]
    top = max(float(h.max()), *[z["high"] for z in zs]) if zs else float(h.max())
    bot = min(float(lo.min()), *[z["low"] for z in zs]) if zs else float(lo.min())
    span = (top - bot) or top * 0.01
    top, bot = top + span * 0.04, bot - span * 0.04
    n = len(ind)
    pw = W - PAD_L - PAD_R
    step = pw / n
    bw = max(1.0, step * 0.62)
    y = lambda p: PAD_T + (top - p) / (top - bot) * PRICE_H
    x = lambda i: PAD_L + (i + 0.5) * step
    up_col, down_col = ("#d9363e", "#1f9d55") if zh else ("#1f9d55", "#d9363e")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'font-family="-apple-system,BlinkMacSystemFont,PingFang SC,Microsoft YaHei,sans-serif">',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>']
    title = f"{name} ({ticker})" if name and name != ticker else ticker
    chg = c.iloc[-1] / c.iloc[-2] - 1 if n > 1 else 0.0
    out.append(f'<text x="{PAD_L}" y="30" font-size="20" font-weight="600" fill="#1d1d1f">{html.escape(title)}</text>')
    out.append(f'<text x="{PAD_L}" y="48" font-size="13" fill="#6e6e73">'
               f'{ind.index[0].date()} – {ind.index[-1].date()} · {"收盘" if zh else "close"} {_fmt(last)} '
               f'({chg:+.2%})</text>')
    # grid + price axis
    for k in range(5):
        p = bot + (top - bot) * k / 4
        yy = y(p)
        out.append(f'<line x1="{PAD_L}" x2="{PAD_L + pw}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="#ececec"/>')
        out.append(f'<text x="{PAD_L - 6}" y="{yy + 4:.1f}" font-size="11" fill="#8e8e93" text-anchor="end">{_fmt(p)}</text>')
    # zones: shaded bands from the day each was confirmed, labelled on the right
    labels = []
    for z in zs:
        since = pd.Timestamp(z.get("since") or ind.index[0])
        i0 = int(ind.index.searchsorted(since))
        x0 = PAD_L + i0 * step
        col = "#d9363e" if z["kind"] == "resistance" else ("#1f9d55" if z["kind"] == "support" else "#8e8e93")
        y1, y2 = y(z["high"]), y(z["low"])
        out.append(f'<rect x="{x0:.1f}" y="{y1:.1f}" width="{PAD_L + pw - x0:.1f}" height="{max(2.0, y2 - y1):.1f}" '
                   f'fill="{col}" fill-opacity="0.12" stroke="{col}" stroke-opacity="0.45" stroke-dasharray="4 3"/>')
        kind = {"support": "支撑" if zh else "Support", "resistance": "阻力" if zh else "Resistance",
                "inside": "当前区间" if zh else "Inside"}[z["kind"]]
        touches = f" · {z['touches']}{'次' if zh else 'x'}"
        labels.append(((y1 + y2) / 2, f"{kind} {_fmt(z['low'])}–{_fmt(z['high'])}{touches}", col))
    # candles
    for i in range(n):
        oi, ci, hi, li = float(o.iloc[i]), float(c.iloc[i]), float(h.iloc[i]), float(lo.iloc[i])
        if any(math.isnan(v) for v in (oi, ci, hi, li)):
            continue
        col = up_col if ci >= oi else down_col
        xx = x(i)
        out.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{y(hi):.1f}" y2="{y(li):.1f}" stroke="{col}" stroke-width="1"/>')
        yt, yb = y(max(oi, ci)), y(min(oi, ci))
        out.append(f'<rect x="{xx - bw / 2:.1f}" y="{yt:.1f}" width="{bw:.1f}" height="{max(1.0, yb - yt):.1f}" fill="{col}"/>')
    # moving averages
    for col_name, colr, label in (("ma20", "#f5a623", "MA20"), ("ma60", "#4a6cf7", "MA60")):
        pts = [f"{x(i):.1f},{y(float(v)):.1f}" for i, v in enumerate(ind[col_name]) if pd.notna(v)]
        if len(pts) > 1:
            out.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{colr}" stroke-width="1.4"/>')
    out.append(f'<text x="{PAD_L + pw - 4}" y="{PAD_T - 6}" font-size="11" text-anchor="end">'
               f'<tspan fill="#f5a623">— MA20</tspan>  <tspan fill="#4a6cf7">— MA60</tspan></text>')
    # last close marker
    yl = y(last)
    out.append(f'<line x1="{PAD_L}" x2="{PAD_L + pw}" y1="{yl:.1f}" y2="{yl:.1f}" stroke="#1d1d1f" stroke-opacity="0.35" stroke-dasharray="2 3"/>')
    out.append(f'<rect x="{PAD_L + pw + 4}" y="{yl - 10:.1f}" width="62" height="20" rx="4" fill="#1d1d1f"/>')
    out.append(f'<text x="{PAD_L + pw + 35}" y="{yl + 4:.1f}" font-size="12" fill="#fff" text-anchor="middle">{_fmt(last)}</text>')
    # zone labels, pushed apart so they don't overlap each other or the last-close tag
    taken = [yl]
    for yy, text, col in sorted(labels):
        while any(abs(yy - t) < 16 for t in taken):
            yy += 16
        taken.append(yy)
        out.append(f'<text x="{PAD_L + pw + 72}" y="{yy + 4:.1f}" font-size="12" fill="{col}">{html.escape(text)}</text>')
    # volume
    v0 = PAD_T + PRICE_H + GAP
    vmax = float(ind["volume"].quantile(0.98)) if ind["volume"].notna().any() else 0   # one spike can't flatten the rest
    if vmax > 0:
        for i in range(n):
            v = ind["volume"].iloc[i]
            if pd.isna(v):
                continue
            hh = min(float(v) / vmax, 1.0) * VOL_H
            col = up_col if float(c.iloc[i]) >= float(o.iloc[i]) else down_col
            out.append(f'<rect x="{x(i) - bw / 2:.1f}" y="{v0 + VOL_H - hh:.1f}" width="{bw:.1f}" height="{hh:.1f}" '
                       f'fill="{col}" fill-opacity="0.55"/>')
        out.append(f'<text x="{PAD_L - 6}" y="{v0 + 10}" font-size="11" fill="#8e8e93" text-anchor="end">'
                   f'{"成交量" if zh else "Vol"}</text>')
    # dates
    for i in (0, n // 2, n - 1):
        anchor = "start" if i == 0 else ("end" if i == n - 1 else "middle")
        out.append(f'<text x="{x(i):.1f}" y="{v0 + VOL_H + 16}" font-size="11" fill="#8e8e93" '
                   f'text-anchor="{anchor}">{ind.index[i].date()}</text>')
    note = ("支撑/阻力：历史上多次转折的价位，从确认日起画出；只描述走势，不是预测或买卖建议。 · stockproof"
            if zh else "Zones: prices where it turned several times, drawn from the day confirmed. Not a forecast. · stockproof")
    out.append(f'<text x="{PAD_L}" y="{H - 10}" font-size="11" fill="#8e8e93">{html.escape(note)}</text>')
    out.append("</svg>")
    return "\n".join(out)


def _empty(ticker: str, msg: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} 120" width="{W}" height="120">'
            f'<rect width="{W}" height="120" fill="#fff"/><text x="24" y="64" font-size="16" fill="#6e6e73" '
            f'font-family="sans-serif">{html.escape(ticker)}: {html.escape(msg)}</text></svg>')
