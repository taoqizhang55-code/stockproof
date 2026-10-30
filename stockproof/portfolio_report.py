"""Portfolio check-up report: one self-contained HTML page with inline SVG charts."""

from __future__ import annotations

import datetime as dt

from stockproof.lab_report import EXTRA, _e, _num, _pct, bar_chart, line_chart
from stockproof.report import CSS

T = {
    "en": {"title": "Portfolio check-up", "findings": "What stands out", "weights": "Holdings",
           "ind": "By industry", "corr": "Which holdings move together (1-year correlation)", "stress": "Replaying past crashes on today's weights",
           "risk": "Share of money vs share of risk", "curve": "Today's weights over the past year (growth of 1)",
           "kpi_vol": "Volatility / yr", "kpi_beta": "Beta", "kpi_dd": "Max drawdown (1 yr)", "kpi_n": "Effective no. of positions",
           "kpi_ret": "Return (1 yr)", "kpi_dr": "Diversification ratio", "w": "Weight", "risk_c": "Risk share",
           "vol": "Vol", "beta": "Beta", "rank": "Market rank", "card": "Scorecard", "pnl": "P/L", "est": "estimated from beta",
           "index": "Index", "money": "money", "riskw": "risk", "generated": "Generated {time}",
           "fx": "Converted to CNY at {fx} (approximate)"},
    "zh": {"title": "持仓体检", "findings": "主要发现", "weights": "持仓", "ind": "行业分布",
           "corr": "哪些持仓同涨同跌（近一年相关系数）", "stress": "用今天的持仓重演历史大跌", "risk": "资金占比 vs 风险占比",
           "curve": "按今天的持仓比例，过去一年的走势（起点 1）", "kpi_vol": "年化波动", "kpi_beta": "贝塔",
           "kpi_dd": "近一年最大回撤", "kpi_n": "等效持股数", "kpi_ret": "近一年收益", "kpi_dr": "分散度",
           "w": "仓位", "risk_c": "风险占比", "vol": "波动", "beta": "贝塔", "rank": "全市场排名", "card": "评分卡",
           "pnl": "盈亏", "est": "按贝塔估算", "index": "指数", "money": "资金", "riskw": "风险",
           "generated": "生成于 {time}", "fx": "按 {fx} 折算成人民币（近似汇率）"},
}


def heatmap(tickers, matrix) -> str:
    n = len(tickers)
    if n < 2:
        return ""
    cell, L, Tp = min(48, 560 // n), 110, 90
    W, H = L + cell * n + 10, Tp + cell * n + 10
    out = [f"<svg viewBox='0 0 {W} {H}' role='img' style='width:100%;max-width:{W}px;height:auto'>"]
    for i, t in enumerate(tickers):
        out.append(f"<text x='{L - 6}' y='{Tp + cell * i + cell / 2 + 4:.1f}' text-anchor='end' font-size='11' fill='var(--muted)'>{_e(t)}</text>")
        out.append(f"<text transform='translate({L + cell * i + cell / 2 + 4:.1f},{Tp - 6}) rotate(-50)' font-size='11' fill='var(--muted)'>{_e(t)}</text>")
        for j in range(n):
            v = matrix[i][j]
            v = 0.0 if v is None else v
            col = "var(--neg)" if v >= 0 else "var(--accent)"
            op = 0.08 + 0.85 * min(1.0, abs(v)) if i != j else 0.12
            out.append(f"<rect x='{L + cell * j}' y='{Tp + cell * i}' width='{cell - 2}' height='{cell - 2}' rx='3' fill='{col}' opacity='{op:.2f}'>"
                       f"<title>{_e(tickers[i])} / {_e(tickers[j])}: {v:.2f}</title></rect>")
            if cell >= 30 and i != j:
                out.append(f"<text x='{L + cell * j + cell / 2 - 1:.1f}' y='{Tp + cell * i + cell / 2 + 3:.1f}' text-anchor='middle' "
                           f"font-size='10' fill='var(--text)'>{v:.1f}</text>")
    out.append("</svg>")
    return "".join(out)


def pair_bars(labels, a, b, la, lb) -> str:
    rows = "".join(
        f"<tr><td class='tk'>{_e(l)}</td><td style='width:60%'>"
        f"<div style='height:8px;background:var(--accent);opacity:.75;border-radius:4px;width:{100 * x:.1f}%' title='{_e(la)} {_pct(x, 0)}'></div>"
        f"<div style='height:8px;background:var(--neg);opacity:.75;border-radius:4px;width:{100 * y:.1f}%;margin-top:3px' title='{_e(lb)} {_pct(y, 0)}'></div>"
        f"</td><td class='num'>{100 * x:.0f}% / {100 * y:.0f}%</td></tr>" for l, x, y in zip(labels, a, b))
    return (f"<p class='note'><span style='color:var(--accent)'>━━ {_e(la)}</span> &nbsp; "
            f"<span style='color:var(--neg)'>━━ {_e(lb)}</span></p><table><tbody>{rows}</tbody></table>")


def build(r: dict, lang: str = "zh") -> str:
    lang = lang if lang in T else "en"
    L = T[lang]
    p = r.get("portfolio") or {}
    kpi = lambda label, val: f"<div class='kpi'><b>{val}</b><span>{_e(label)}</span></div>"
    level = {"warn": "no_edge", "info": "", "ok": "passes"}
    parts = [f"<header><h1>{_e(L['title'])}</h1><div class='meta'><span>{_e(r['as_of'])}</span>"
             f"<span>{_e(L['generated'].format(time=dt.datetime.now().strftime('%Y-%m-%d %H:%M')))}</span></div></header>",
             "<section class='card'><h2>" + _e(L["findings"]) + "</h2>" +
             "".join(f"<div class='verdict {level.get(x['level'], '')}' style='margin-top:8px'>{_e(x['text'])}</div>"
                     for x in r["findings"]) +
             "<div class='kpis'>" + kpi(L["kpi_ret"], _pct(p.get("ret"))) + kpi(L["kpi_vol"], _pct(p.get("ann_vol"), 0).lstrip("+")) +
             kpi(L["kpi_beta"], _num(p.get("beta"), 2)) + kpi(L["kpi_dd"], _pct(p.get("max_dd"))) +
             kpi(L["kpi_n"], _num(r.get("effective_n"), 1)) + kpi(L["kpi_dr"], _num(r.get("diversification_ratio"), 2)) +
             "</div></section>"]
    hold = r["holdings"]
    rows = "".join(
        f"<tr><td class='tk'>{_e(h['ticker'])}<small>{_e(h.get('name') or '')} · {_e(h.get('industry') or '')}</small></td>"
        f"<td class='num'>{100 * h['weight']:.1f}%</td><td class='num'>{100 * h['risk_share']:.0f}%</td>"
        f"<td class='num'>{_pct(h.get('vol'), 0).lstrip('+')}</td><td class='num'>{_num(h.get('beta'), 2)}</td>"
        f"<td class='num'>{_pct(h.get('pnl_pct')) if h.get('pnl_pct') is not None else '—'}</td>"
        f"<td class='num'>{(str(h['rank']['rank']) + '/' + str(h['rank']['of'])) if h.get('rank') else '—'}</td>"
        f"<td class='num'>{(_num(h['card']['score'], 0) + ' ' + _e(h['card']['label'] or '')) if h.get('card') else '—'}</td></tr>"
        for h in hold)
    fx = " · ".join(f"{k} {v}" for k, v in (r.get("fx") or {}).items() if k != "CNY")
    note = f"<p class='note'>{_e(L['fx'].format(fx=fx))}</p>" if r.get("fx") else ""
    parts.append(f"<section class='card'><h2>{_e(L['weights'])}</h2><div style='overflow-x:auto'><table><thead><tr><th></th>"
                 f"<th>{_e(L['w'])}</th><th>{_e(L['risk_c'])}</th><th>{_e(L['vol'])}</th><th>{_e(L['beta'])}</th>"
                 f"<th>{_e(L['pnl'])}</th><th>{_e(L['rank'])}</th><th>{_e(L['card'])}</th></tr></thead><tbody>{rows}</tbody></table></div>{note}</section>")
    ind = r.get("industries") or {}
    ind_rows = "".join(f"<tr><td class='tk'>{_e(k)}</td><td style='width:60%'><div style='height:10px;background:var(--accent);"
                       f"opacity:.75;border-radius:4px;width:{100 * v:.1f}%'></div></td><td class='num'>{100 * v:.0f}%</td></tr>"
                       for k, v in ind.items())
    parts.append(f"<section class='card grid2'><div><h2>{_e(L['ind'])}</h2><table><tbody>{ind_rows}</tbody></table>"
                 f"</div><div><h2>{_e(L['risk'])}</h2>" +
                 pair_bars([h["ticker"] for h in hold], [h["weight"] for h in hold], [max(0, h["risk_share"]) for h in hold],
                           L["money"], L["riskw"]) + "</div></section>")
    c = r.get("corr") or {}
    if len(c.get("tickers", [])) >= 2:
        parts.append(f"<section class='card'><h2>{_e(L['corr'])}</h2>{heatmap(c['tickers'], c['matrix'])}</section>")
    st = r.get("stress") or []
    if st:
        parts.append(f"<section class='card'><h2>{_e(L['stress'])}</h2>" +
                     bar_chart([s["name"] for s in st], [s["portfolio"] for s in st]) +
                     "<table><tbody>" + "".join(
                         f"<tr><td>{_e(s['name'])}<small class='num' style='display:block'>{_e(s['from'])} → {_e(s['to'])}</small></td>"
                         f"<td><span class='chip {'negative' if s['portfolio'] < 0 else 'positive'}'>{_pct(s['portfolio'])}</span></td>"
                         f"<td class='num'>{_e(L['index'])}: {' · '.join(f'{k} {_pct(v)}' for k, v in s['index'].items())}</td>"
                         f"<td class='num'>{(_e(L['est']) + ': ' + _e(', '.join(s['estimated']))) if s['estimated'] else ''}</td></tr>"
                         for s in st) + "</tbody></table></section>")
    cv = r.get("curve") or {}
    if len(cv.get("values", [])) > 2:
        parts.append(f"<section class='card'><h2>{_e(L['curve'])}</h2>{line_chart(cv['dates'], cv['values'])}</section>")
    parts.append(f"<p class='note'>{_e(r.get('note', ''))}</p>")
    if r.get("problems"):
        parts.append(f"<p class='note'>{_e('; '.join(r['problems']))}</p>")
    return (f"<!doctype html><html lang='{'zh-CN' if lang == 'zh' else 'en'}'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'><title>{_e(L['title'])}</title>"
            f"<style>{CSS}{EXTRA}</style></head><body><div class='wrap'>{''.join(parts)}</div></body></html>")
