"""The quant lab's report: one self-contained HTML page with inline SVG charts (light / dark, phone-friendly)."""

from __future__ import annotations

import datetime as dt
import html
import math

import numpy as np
import pandas as pd

from stockproof.report import CSS

T = {
    "en": {"title": "Quant lab", "explore": "Exploration (holdout locked)", "confirm": "Holdout check (one shot)",
           "verdict": "Verdict", "strategy": "Strategy", "data": "Data", "period": "Period", "universe": "Universe",
           "events": "Signals", "trades": "Trades", "positions": "Avg. positions", "ann": "Excess return / yr",
           "t": "t-statistic", "sharpe": "Sharpe (excess)", "dd": "Max drawdown (excess)", "win": "Trades beating the market",
           "per_trade": "Average trade vs market", "curve": "Growth of 1 in excess of the market",
           "dd_title": "Drawdown of the excess return", "years": "Excess return by year", "dist": "Trades: return vs market",
           "best": "Best trades", "worst": "Worst trades", "tries": "Variants tried for this question",
           "need": "t needed after that many tries", "padj": "p-value corrected for tries",
           "how": "How this was tested",
           "how_text": ("Point-in-time: signals use only what was public on the day; entry after the news; costs "
                        "(commission, slippage, stamp duty) and A-share price limits applied; returns are measured "
                        "against the equal-weighted average of the same universe. The last {y} years are locked while "
                        "you explore, and every variant you try raises the bar."),
           "caveat": "Large caps only, today's members (survivorship). Research, not investment advice.",
           "generated": "Generated {time}",
           "robust": "Robustness checks", "stress": "Costs x{m}", "stress_ann": "Excess / yr at x{m} costs",
           "wf": "Walk-forward (out-of-sample years)", "wf_year": "Year", "wf_pick": "Variant picked with data before that year",
           "wf_ex": "Excess that year", "wf_mean": "Walk-forward excess / yr", "wf_ins": "Hindsight-best variant, same years"},
    "zh": {"title": "量化实验室", "explore": "样本内研究（近期数据已锁定）", "confirm": "样本外检验（只有一次机会）",
           "verdict": "结论", "strategy": "策略", "data": "数据", "period": "区间", "universe": "股票池",
           "events": "信号数", "trades": "交易数", "positions": "平均持仓数", "ann": "每年超额收益",
           "t": "t 值", "sharpe": "夏普比率（超额）", "dd": "最大回撤（超额）", "win": "跑赢市场的交易占比",
           "per_trade": "平均每笔相对市场", "curve": "相对市场的净值（起点 1）", "dd_title": "超额收益的回撤",
           "years": "每年超额收益", "dist": "每笔交易相对市场的收益分布", "best": "最好的交易", "worst": "最差的交易",
           "tries": "这个问题已尝试的版本数", "need": "按尝试次数修正后需要的 t 值", "padj": "按次数修正后的 p 值",
           "how": "怎么检验的",
           "how_text": ("不偷看未来：信号只用当天已公开的信息，消息出来之后才买入；扣除佣金、滑点和印花税，遵守 A 股涨跌停；"
                        "收益相对同一股票池的等权平均来算。研究时最近 {y} 年的数据是锁住的，而且每多试一个版本，"
                        "通过的门槛就更高。"),
           "caveat": "只覆盖大盘股、且是今天的成分股（有幸存者偏差）。仅供研究，不构成投资建议。",
           "generated": "生成于 {time}",
           "robust": "稳健性检验", "stress": "成本×{m}", "stress_ann": "成本×{m} 后每年超额",
           "wf": "滚动向前验证（样本外年份）", "wf_year": "年份", "wf_pick": "只用之前数据挑出的版本",
           "wf_ex": "当年超额", "wf_mean": "滚动向前每年超额", "wf_ins": "事后最好的版本（同期）"},
}

EXTRA = """
.big { font-size:15px; }
.verdict { border-left:4px solid var(--accent); padding:10px 14px; background:var(--bg); border-radius:8px; font-size:15px; }
.verdict.no_edge, .verdict.failed, .verdict.luck_risk, .verdict.negative { border-left-color:var(--neg); }
.verdict.passes, .verdict.confirmed { border-left-color:var(--pos); }
.kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:10px; margin-top:12px; }
.kpi { border:1px solid var(--line); border-radius:10px; padding:10px 12px; }
.kpi b { display:block; font-size:22px; font-variant-numeric:tabular-nums; }
.kpi span { color:var(--muted); font-size:12px; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
@media (max-width:720px) { .grid2 { grid-template-columns:1fr; } }
.note { color:var(--muted); font-size:13px; }
svg text { font-family:inherit; }
"""


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _pct(v, d=1) -> str:
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{100 * v:+.{d}f}%"


def _num(v, d=2) -> str:
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{d}f}"


def line_chart(dates, ys, color="var(--accent)", base=1.0, fmt="{:.2f}", fill=False, H=220) -> str:
    if len(ys) < 2:
        return ""
    W, L, R, Tp, B = 720, 48, 10, 10, 26
    vals = [v for v in ys if v is not None and v == v]
    lo, hi = min(vals + [base]), max(vals + [base])
    pad = (hi - lo) * 0.06 or 0.05
    lo, hi = lo - pad, hi + pad
    x = lambda i: L + (W - L - R) * i / (len(ys) - 1)
    y = lambda v: Tp + (H - Tp - B) * (hi - v) / (hi - lo)
    out = [f"<svg viewBox='0 0 {W} {H}' role='img' style='width:100%;height:auto'>"]
    for v in sorted({base, lo + pad, hi - pad}):
        dash = " stroke-dasharray='3 3'" if v == base else ""
        out.append(f"<line x1='{L}' x2='{W - R}' y1='{y(v):.1f}' y2='{y(v):.1f}' stroke='var(--line)'{dash}/>"
                   f"<text x='{L - 6}' y='{y(v) + 4:.1f}' text-anchor='end' font-size='11' fill='var(--muted)'>{fmt.format(v)}</text>")
    for i in (0, len(dates) // 2, len(dates) - 1):
        anchor = "start" if i == 0 else ("end" if i == len(dates) - 1 else "middle")
        out.append(f"<text x='{x(i):.1f}' y='{H - 6}' text-anchor='{anchor}' font-size='11' fill='var(--muted)'>{_e(str(dates[i])[:7])}</text>")
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(ys) if v is not None and v == v)
    if fill:
        out.append(f"<polygon points='{x(0):.1f},{y(base):.1f} {pts} {x(len(ys) - 1):.1f},{y(base):.1f}' "
                   f"fill='{color}' opacity='0.18'/>")
    out.append(f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='2'/></svg>")
    return "".join(out)


def bar_chart(labels, vals, H=200) -> str:
    vals = [0.0 if v is None or v != v else v for v in vals]
    if not vals:
        return ""
    W, L, R, Tp, B = 720, 48, 10, 10, 26
    m = max(abs(v) for v in vals) or 0.01
    lo, hi = min(-m * 0.1, min(vals)), max(m * 0.1, max(vals))
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad
    y = lambda v: Tp + (H - Tp - B) * (hi - v) / (hi - lo)
    bw = (W - L - R) / len(vals)
    out = [f"<svg viewBox='0 0 {W} {H}' role='img' style='width:100%;height:auto'>",
           f"<line x1='{L}' x2='{W - R}' y1='{y(0):.1f}' y2='{y(0):.1f}' stroke='var(--muted)' opacity='.5'/>"]
    for i, (lab, v) in enumerate(zip(labels, vals)):
        x0 = L + i * bw + bw * 0.15
        top, h = (y(v), y(0) - y(v)) if v >= 0 else (y(0), y(v) - y(0))
        col = "var(--pos)" if v >= 0 else "var(--neg)"
        out.append(f"<rect x='{x0:.1f}' y='{top:.1f}' width='{bw * 0.7:.1f}' height='{max(1, h):.1f}' rx='2' fill='{col}'>"
                   f"<title>{_e(lab)}: {_pct(v)}</title></rect>")
        out.append(f"<text x='{x0 + bw * 0.35:.1f}' y='{H - 6}' text-anchor='middle' font-size='11' fill='var(--muted)'>{_e(lab)}</text>")
        ty = top - 4 if v >= 0 else top + h + 12
        out.append(f"<text x='{x0 + bw * 0.35:.1f}' y='{ty:.1f}' text-anchor='middle' font-size='10' fill='var(--muted)'>{_pct(v, 0)}</text>")
    out.append("</svg>")
    return "".join(out)


def histogram(vals, bins=24, H=180) -> str:
    vals = np.array([v for v in vals if v is not None and v == v])
    if len(vals) < 5:
        return ""
    lo, hi = np.percentile(vals, 1), np.percentile(vals, 99)
    if hi <= lo:
        return ""
    counts, edges = np.histogram(np.clip(vals, lo, hi), bins=bins, range=(lo, hi))
    W, L, R, Tp, B = 720, 20, 10, 10, 26
    mx = counts.max() or 1
    bw = (W - L - R) / bins
    out = [f"<svg viewBox='0 0 {W} {H}' role='img' style='width:100%;height:auto'>"]
    for i, c in enumerate(counts):
        mid = (edges[i] + edges[i + 1]) / 2
        h = (H - Tp - B) * c / mx
        col = "var(--pos)" if mid >= 0 else "var(--neg)"
        out.append(f"<rect x='{L + i * bw + 1:.1f}' y='{H - B - h:.1f}' width='{bw - 2:.1f}' height='{h:.1f}' fill='{col}' opacity='.8'>"
                   f"<title>{_pct(edges[i], 0)} … {_pct(edges[i + 1], 0)}: {c}</title></rect>")
    zx = L + (W - L - R) * (0 - lo) / (hi - lo)
    if L <= zx <= W - R:
        out.append(f"<line x1='{zx:.1f}' x2='{zx:.1f}' y1='{Tp}' y2='{H - B}' stroke='var(--muted)' stroke-dasharray='3 3'/>")
    for v in (lo, 0.0, hi):
        if lo <= v <= hi:
            xx = L + (W - L - R) * (v - lo) / (hi - lo)
            out.append(f"<text x='{xx:.1f}' y='{H - 6}' text-anchor='middle' font-size='11' fill='var(--muted)'>{_pct(v, 0)}</text>")
    out.append("</svg>")
    return "".join(out)


def build(out: dict, res: dict, lang: str = "zh") -> str:
    from stockproof.lab import HOLDOUT_YEARS as HOLDOUT
    lang = lang if lang in T else "en"
    L = T[lang]
    v = out["verdict"]
    phase = L["explore"] if out["phase"] == "explore" else L["confirm"]
    kpi = lambda label, val: f"<div class='kpi'><b>{val}</b><span>{_e(label)}</span></div>"
    pt = out.get("per_trade") or {}
    parts = [f"<header><h1>{_e(L['title'])}</h1><p>{_e(out.get('spec', {}).get('name') or out['description'])}</p>"
             f"<div class='meta'><span>{_e(phase)}</span><span>{_e(L['period'])}: {_e(out['period'])}</span>"
             f"<span>{_e(L['generated'].format(time=dt.datetime.now().strftime('%Y-%m-%d %H:%M')))}</span>"
             f"<span>id {_e(out['id'])}</span></div></header>"]
    sec = [f"<h2>{_e(L['verdict'])}</h2><div class='verdict {_e(v['code'])}'>{_e(v['text'])}</div><div class='kpis'>",
           kpi(L["ann"], _pct(out.get("ann_excess"))), kpi(L["t"], _num(out.get("t"), 1)),
           kpi(L["trades"], out.get("trades", 0)), kpi(L["win"], "—" if not pt.get("win") and pt.get("win") != 0 else f"{100 * pt['win']:.0f}%"),
           kpi(L["per_trade"], _pct(pt.get("mean"), 2)), kpi(L["dd"], _pct(out.get("max_dd")))]
    if out["phase"] == "explore":
        sec += [kpi(L["tries"], v["tries"]), kpi(L["need"], _num(v["t_needed"], 1))]
    sec.append("</div>")
    parts.append("<section class='card'>" + "".join(sec) + "</section>")

    st, wf = out.get("stress") or {}, out.get("walk_forward") or {}
    if st.get("text") or wf.get("text"):
        m = f"{st.get('mult', 2):g}"
        rb = [f"<h2>{_e(L['robust'])}</h2><div class='kpis'>"]
        if st.get("ann") is not None:
            rb.append(kpi(L["stress_ann"].format(m=m), _pct(st["ann"])))
        if wf.get("mean") is not None:
            rb.append(kpi(L["wf_mean"], _pct(wf["mean"])))
            if wf.get("variants", 1) > 1:
                rb.append(kpi(L["wf_ins"], _pct(wf.get("in_sample_best"))))
        rb.append("</div>")
        for x in (st, wf):
            if x.get("text"):
                bad = x.get("code") in ("fragile", "fades")
                rb.append(f"<div class='verdict {'no_edge' if bad else 'passes'}' style='margin-top:10px'>{_e(x['text'])}</div>")
        if wf.get("years"):
            rb.append(f"<h3>{_e(L['wf'])}</h3><table><thead><tr><th>{_e(L['wf_year'])}</th><th>{_e(L['wf_pick'])}</th>"
                      f"<th>{_e(L['wf_ex'])}</th></tr></thead><tbody>" +
                      "".join(f"<tr><td class='num'>{r['year']}</td><td>{_e(r['pick'])}</td><td><span class='chip "
                              f"{'positive' if r['excess'] >= 0 else 'negative'}'>{_pct(r['excess'])}</span></td></tr>"
                              for r in wf["years"]) + "</tbody></table>")
        parts.append("<section class='card'>" + "".join(rb) + "</section>")

    s = res["summary"]
    charts = []
    curve = s.get("curve")
    if isinstance(curve, pd.DataFrame) and len(curve):
        c = curve["long_excess"].groupby(pd.Grouper(freq="W")).last().dropna()
        dates = [d.date().isoformat() for d in c.index]
        charts.append(f"<h2>{_e(L['curve'])}</h2>" + line_chart(dates, list(c.to_numpy())))
        dd = (c / c.cummax() - 1)
        charts.append(f"<h3>{_e(L['dd_title'])}</h3>" +
                      line_chart(dates, list(dd.to_numpy()), color="var(--neg)", base=0.0, fmt="{:.0%}", fill=True, H=150))
    elif res.get("periods"):
        per = res["periods"]
        c = np.cumprod([1 + p["return"] - p["market"] for p in per])
        charts.append(f"<h2>{_e(L['curve'])}</h2>" + line_chart([p["date"] for p in per], list(c)))
    if out.get("years"):
        charts.append(f"<h2>{_e(L['years'])}</h2>" + bar_chart([str(y["year"]) for y in out["years"]],
                                                              [y["excess"] for y in out["years"]]))
    tr = res.get("trades") or []
    if len(tr) >= 5:
        charts.append(f"<h2>{_e(L['dist'])}</h2>" + histogram([t["excess"] for t in tr]))
    if charts:
        parts.append("<section class='card'>" + "".join(charts) + "</section>")

    def table(rows):
        return ("<table><thead><tr><th></th><th>in</th><th>out</th><th></th></tr></thead><tbody>" +
                "".join(f"<tr><td class='tk'>{_e(r['ticker'])}</td><td class='num'>{_e(r['entry'])}</td>"
                        f"<td class='num'>{_e(r['exit'])}</td><td><span class='chip {'positive' if r['excess'] >= 0 else 'negative'}'>"
                        f"{_pct(r['excess'])}</span></td></tr>" for r in rows) + "</tbody></table>")
    if out.get("best_trades"):
        parts.append(f"<section class='card grid2'><div><h2>{_e(L['best'])}</h2>{table(out['best_trades'])}</div>"
                     f"<div><h2>{_e(L['worst'])}</h2>{table(out['worst_trades'])}</div></section>")

    spec_rows = [(L["strategy"], out["description"]), (L["universe"], out["universe"]), (L["events"], out["events"]),
                 (L["positions"], _num(out.get("avg_positions"), 1)), (L["sharpe"], _num(out.get("sharpe"), 2))]
    if out["phase"] == "explore" and v.get("p_adjusted") is not None:
        spec_rows.append((L["padj"], _num(v["p_adjusted"], 3)))
    parts.append(f"<section class='card'><h2>{_e(L['how'])}</h2><table><tbody>" +
                 "".join(f"<tr><td class='num'>{_e(a)}</td><td>{_e(b)}</td></tr>" for a, b in spec_rows) +
                 f"</tbody></table><p class='note'>{_e(L['how_text'].format(y=HOLDOUT))}</p>"
                 f"<p class='note'>{_e(L['caveat'])}</p></section>")
    return (f"<!doctype html><html lang='{'zh-CN' if lang == 'zh' else 'en'}'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'><title>{_e(L['title'])} · {_e(out['id'])}</title>"
            f"<style>{CSS}{EXTRA}</style></head><body><div class='wrap'>{''.join(parts)}</div></body></html>")
