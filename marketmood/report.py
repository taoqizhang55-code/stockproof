"""
Self-contained HTML report (one file, no internet needed to open it).
Works in light and dark mode, and on phones.
"""

from __future__ import annotations

import datetime as dt
import html

import pandas as pd

from marketmood.i18n import t
from marketmood.summary import mood_label

CSS = """
:root { --bg:#f7f7f5; --card:#ffffff; --text:#1d1d1f; --muted:#6e6e73; --line:#e5e5e2;
        --pos:#1a7f4b; --pos-bg:#e3f4ea; --neg:#c0392b; --neg-bg:#fbe7e4;
        --neu:#6e6e73; --neu-bg:#eeeeec; --accent:#2a5bd7; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#151517; --card:#1f1f22; --text:#ececee; --muted:#9a9aa0; --line:#323236;
          --pos:#4cc488; --pos-bg:#16352a; --neg:#ff7a6b; --neg-bg:#3d1f1c;
          --neu:#a0a0a6; --neu-bg:#2a2a2e; --accent:#7aa2ff; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text);
       font:15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }
.wrap { max-width:960px; margin:0 auto; padding:28px 16px 60px; }
header h1 { margin:0; font-size:28px; letter-spacing:-0.02em; }
header p { margin:4px 0 0; color:var(--muted); }
.meta { display:flex; flex-wrap:wrap; gap:8px 18px; margin-top:12px; color:var(--muted); font-size:13px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px; margin-top:20px; }
h2 { font-size:17px; margin:0 0 12px; }
table { width:100%; border-collapse:collapse; font-size:14px; }
th { text-align:left; color:var(--muted); font-weight:500; font-size:12px; text-transform:uppercase;
     letter-spacing:0.04em; padding:6px 8px; border-bottom:1px solid var(--line); }
td { padding:10px 8px; border-bottom:1px solid var(--line); vertical-align:middle; }
tr:last-child td { border-bottom:none; }
.tk { font-weight:600; }
.tk small { display:block; color:var(--muted); font-weight:400; font-size:12px; }
.bar { position:relative; height:8px; background:var(--neu-bg); border-radius:4px; min-width:120px; }
.bar .mid { position:absolute; left:50%; top:-3px; bottom:-3px; width:1px; background:var(--muted); opacity:.5; }
.bar .fill { position:absolute; top:0; bottom:0; border-radius:4px; }
.chip { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; font-weight:600;
        white-space:nowrap; font-variant-numeric:tabular-nums; }
.positive { color:var(--pos); background:var(--pos-bg); }
.negative { color:var(--neg); background:var(--neg-bg); }
.neutral, .none { color:var(--neu); background:var(--neu-bg); }
.num { font-variant-numeric:tabular-nums; color:var(--muted); }
.few { display:inline-block; margin-left:6px; padding:1px 6px; border-radius:4px; font-size:11px;
       color:var(--muted); border:1px dashed var(--muted); vertical-align:middle; }
details { border-top:1px solid var(--line); }
details:first-of-type { border-top:none; }
summary { cursor:pointer; padding:12px 2px; display:flex; align-items:center; gap:10px; list-style:none; }
summary::-webkit-details-marker { display:none; }
summary::before { content:"▸"; color:var(--muted); transition:transform .15s; }
details[open] summary::before { transform:rotate(90deg); }
.news { list-style:none; margin:0 0 12px; padding:0; }
.news li { display:grid; grid-template-columns:56px 1fr; gap:4px 12px; padding:10px 4px;
           border-top:1px dashed var(--line); }
.news li.low { opacity:.5; }
.news a { color:var(--text); text-decoration:none; font-weight:500; }
.news a:hover { color:var(--accent); text-decoration:underline; }
.why { grid-column:2; color:var(--muted); font-size:13px; }
.sub { grid-column:2; color:var(--muted); font-size:12px; }
.note { color:var(--muted); font-size:13px; }
.wide { overflow-x:auto; }
@media (max-width:600px) { .hide-sm { display:none; } }
"""


def _chip(score, lang: str) -> str:
    label = mood_label(score)
    text = "—" if score is None or pd.isna(score) else f"{score:+.2f}"
    return f'<span class="chip {label}" title="{html.escape(t(lang, label))}">{text}</span>'


def _bar(score) -> str:
    if score is None or pd.isna(score):
        return '<div class="bar"><div class="mid"></div></div>'
    width = abs(score) * 50
    left = 50 if score >= 0 else 50 - width
    color = "var(--pos)" if score >= 0 else "var(--neg)"
    return (f'<div class="bar"><div class="mid"></div><div class="fill" '
            f'style="left:{left:.1f}%;width:{width:.1f}%;background:{color}"></div></div>')


def _few(r, lang: str) -> str:
    if not r.get("few", False):
        return ""
    return (f'<span class="few" title="{html.escape(t(lang, "few"))}">'
            f'{html.escape(t(lang, "few_short"))}</span>')


def build_report(summary: pd.DataFrame, details: pd.DataFrame, names: dict, *,
                 lang: str, model: str, days: int, min_relevance: float,
                 min_sample: int = 5) -> str:
    esc = html.escape
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = []
    for _, r in summary.iterrows():
        rows.append(
            f'<tr><td class="tk">{esc(r.ticker)}<small>{esc(names.get(r.ticker, ""))}</small></td>'
            f'<td>{_chip(r.mood, lang)}{_few(r, lang)}</td><td class="hide-sm">{_bar(r.mood)}</td>'
            f'<td class="num">{r.relevant} / {r.headlines}</td>'
            f'<td class="num">{r.positive} / {r.negative}</td></tr>')

    sections = []
    for _, r in summary.iterrows():
        g = details[details["ticker"] == r.ticker].sort_values(
            ["relevance", "score"], ascending=[False, False])
        items = []
        for _, h in g.iterrows():
            dup = pd.notna(getattr(h, "duplicate_of", None))
            low = h.relevance < min_relevance or dup
            title = esc(h.title)
            link = f'<a href="{esc(h.link)}" target="_blank" rel="noopener">{title}</a>' if h.link else title
            low_note = (f" · {esc(t(lang, 'dup'))}" if dup else
                        f" · {esc(t(lang, 'low_relevance'))}" if low else "")
            items.append(
                f'<li class="{"low" if low else ""}"><div>{_chip(h.score, lang)}</div>'
                f'<div>{link}</div><div class="why">{esc(h.reason)}</div>'
                f'<div class="sub">{esc(h.date)} · {esc(h.source)} · '
                f'{esc(t(lang, "relevance"))} {h.relevance:.1f}{low_note}</div></li>')
        body = f'<ul class="news">{"".join(items)}</ul>' if items else f'<p class="note">{esc(t(lang, "no_news"))}</p>'
        sections.append(
            f'<details><summary><span class="tk">{esc(r.ticker)}</span> {_chip(r.mood, lang)}{_few(r, lang)}'
            f'<span class="num">{r.relevant} / {r.headlines}</span></summary>{body}</details>')

    return f"""<!doctype html>
<html lang="{'zh-CN' if lang == 'zh' else 'en'}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(t(lang, 'title'))} · {now[:10]}</title><style>{CSS}</style></head>
<body><div class="wrap">
<header><h1>{esc(t(lang, 'title'))}</h1><p>{esc(t(lang, 'subtitle'))}</p>
<div class="meta"><span>{esc(t(lang, 'generated'))}: {now}</span>
<span>{esc(t(lang, 'model'))}: {esc(model)}</span><span>{esc(t(lang, 'window', days=days))}</span></div></header>
<section class="card"><h2>{esc(t(lang, 'overview'))}</h2><div class="wide"><table>
<thead><tr><th>{esc(t(lang, 'ticker'))}</th><th>{esc(t(lang, 'mood'))}</th><th class="hide-sm"></th>
<th>{esc(t(lang, 'relevant'))} / {esc(t(lang, 'headlines'))}</th><th>{esc(t(lang, 'pos_neg'))}</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div></section>
<section class="card"><h2>{esc(t(lang, 'details'))}</h2>{''.join(sections)}</section>
<section class="card"><h2>{esc(t(lang, 'how_title'))}</h2><p class="note">{esc(t(lang, 'how'))}</p>
<p class="note">{esc(t(lang, 'few'))}: &lt; {min_sample}.</p>
<p class="note">{esc(t(lang, 'disclaimer'))}</p></section>
</div></body></html>"""
