"""HTML report for the earnings module (same look as the news report)."""

from __future__ import annotations

import datetime as dt
import html

import pandas as pd

from marketmood.i18n import t
from marketmood.report import CSS, _chip

EXTRA_CSS = """
.grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:10px; margin:10px 0; }
.kv { background:var(--bg); border-radius:10px; padding:8px 10px; }
.kv b { display:block; font-size:12px; color:var(--muted); font-weight:500; }
.badge { display:inline-block; padding:2px 8px; border-radius:6px; font-size:12px; border:1px solid var(--line);
         white-space:nowrap; }
.raised, .initiated { color:var(--pos); border-color:var(--pos); }
.lowered, .withdrawn { color:var(--neg); border-color:var(--neg); }
ul.pts { margin:6px 0 10px 18px; padding:0; }
.hist td, .hist th { padding:5px 8px; font-size:13px; }
a.src { color:var(--accent); font-size:13px; }
"""


def _sue_chip(v) -> str:
    if v is None or pd.isna(v):
        return '<span class="chip none">—</span>'
    cls = "positive" if v >= 1 else "negative" if v <= -1 else "neutral"
    return f'<span class="chip {cls}">{v:+.1f}</span>'


def _guidance(g: str, lang: str) -> str:
    g = g or "none"
    return f'<span class="badge {html.escape(g)}">{html.escape(t(lang, "g_" + g))}</span>'


def build_earnings_report(rows: list[dict], *, lang: str, model: str) -> str:
    """rows: one dict per ticker with keys ticker, name, read (dict or None), history (DataFrame)."""
    esc = html.escape
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    overview, cards = [], []
    for r in rows:
        read, hist = r.get("read"), r.get("history")
        last = hist.dropna(subset=["sue"]).iloc[-1] if hist is not None and hist["sue"].notna().any() else None
        overview.append(
            f'<tr><td class="tk">{esc(r["ticker"])}<small>{esc(r["name"])}</small></td>'
            f'<td class="num">{esc(read["filed"]) if read else "—"}</td>'
            f'<td>{_chip(read["tone"], lang) if read else _chip(None, lang)}</td>'
            f'<td>{_guidance(read["guidance"], lang) if read else "—"}</td>'
            f'<td>{_sue_chip(last["sue"] if last is not None else None)}</td></tr>')

        body = []
        fc = r.get("forecast")
        if fc:
            change = "" if fc.get("change_pct") is None else f"{fc['change_pct']:+.0f}%"
            body.append(f'<p><span class="badge">{esc(t(lang, "e_forecast"))}</span> '
                        f'{esc(t(lang, "e_forecast_line", type=fc.get("type") or "", change=change, period=fc.get("period") or "", date=fc.get("date") or ""))}</p>'
                        f'<p class="note">{esc(fc.get("reason") or "")}</p>')
        if read:
            body.append(
                f'<div class="grid"><div class="kv"><b>{esc(t(lang, "e_period"))}</b>{esc(read["period"])}</div>'
                f'<div class="kv"><b>{esc(t(lang, "e_revenue"))}</b>{esc(read["revenue_growth"])}</div>'
                f'<div class="kv"><b>{esc(t(lang, "e_eps"))}</b>{esc(read["eps"])}</div>'
                f'<div class="kv"><b>{esc(t(lang, "e_guidance"))}</b>{_guidance(read["guidance"], lang)}</div></div>'
                f'<p>{esc(read["summary"])}</p>')
            if read["key_points"]:
                body.append(f'<b>{esc(t(lang, "e_points"))}</b><ul class="pts">'
                            + "".join(f"<li>{esc(x)}</li>" for x in read["key_points"]) + "</ul>")
            if read["risks"]:
                body.append(f'<b>{esc(t(lang, "e_risks"))}</b><ul class="pts">'
                            + "".join(f"<li>{esc(x)}</li>" for x in read["risks"]) + "</ul>")
            if str(read.get("url", "")).startswith(("https://", "http://")):
                body.append(f'<a class="src" href="{esc(read["url"])}" target="_blank" rel="noopener">'
                            f'{esc(t(lang, "e_read"))} ↗</a>')
        else:
            body.append(f'<p class="note">{esc(t(lang, "e_none"))}</p>')

        if hist is not None and len(hist):
            h = hist.tail(8).iloc[::-1]
            trs = "".join(
                f'<tr><td class="num">{q.end:%Y-%m-%d}{"*" if q.q4_derived else ""}</td>'
                f'<td class="num">{esc(q.fiscal)}</td><td class="num">{q.eps:.2f}</td>'
                f'<td class="num">{"" if pd.isna(q.eps_year_ago) else f"{q.eps_year_ago:.2f}"}</td>'
                f'<td class="num">{"" if pd.isna(q.change) else f"{q.change:+.2f}"}</td>'
                f'<td>{_sue_chip(q.sue)}</td><td class="num">{q.filed:%Y-%m-%d}</td></tr>'
                for q in h.itertuples())
            body.append(
                f'<details><summary>{esc(t(lang, "e_history"))}</summary><div class="wide"><table class="hist">'
                f'<thead><tr><th>{esc(t(lang, "e_quarter_end"))}</th><th></th><th>{esc(t(lang, "e_eps"))}</th>'
                f'<th>{esc(t(lang, "e_year_ago"))}</th><th>{esc(t(lang, "e_change"))}</th>'
                f'<th>SUE</th><th>{esc(t(lang, "e_filed"))}</th></tr></thead><tbody>{trs}</tbody></table></div>'
                f'<p class="note">* {esc(t(lang, "e_q4"))}</p></details>')

        cards.append(
            f'<section class="card"><h2>{esc(r["ticker"])} · {esc(r["name"])} '
            f'{_chip(read["tone"], lang) if read else ""}</h2>{"".join(body)}</section>')

    return f"""<!doctype html>
<html lang="{'zh-CN' if lang == 'zh' else 'en'}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(t(lang, 'e_title'))} · {now[:10]}</title><style>{CSS}{EXTRA_CSS}</style></head>
<body><div class="wrap">
<header><h1>{esc(t(lang, 'e_title'))}</h1><p>{esc(t(lang, 'e_subtitle'))}</p>
<div class="meta"><span>{esc(t(lang, 'generated'))}: {now}</span><span>{esc(t(lang, 'model'))}: {esc(model)}</span>
<span>SEC EDGAR</span></div></header>
<section class="card"><h2>{esc(t(lang, 'overview'))}</h2><div class="wide"><table>
<thead><tr><th>{esc(t(lang, 'ticker'))}</th><th>{esc(t(lang, 'e_release'))}</th><th>{esc(t(lang, 'e_tone'))}</th>
<th>{esc(t(lang, 'e_guidance'))}</th><th>{esc(t(lang, 'e_sue'))}</th></tr></thead>
<tbody>{''.join(overview)}</tbody></table></div></section>
{''.join(cards)}
<section class="card"><h2>{esc(t(lang, 'how_title'))}</h2><p class="note">{esc(t(lang, 'e_how'))}</p>
<p class="note">{esc(t(lang, 'disclaimer'))}</p></section>
</div></body></html>"""
