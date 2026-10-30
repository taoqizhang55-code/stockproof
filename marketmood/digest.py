"""
Daily digest: "what happened to your stocks today", on one page.

Every section is computed from saved data (no guessing): unusual moves with their explanation,
important company announcements, new earnings reports, reports coming up, the strongest news
moods. The LLM only writes the 3-4 sentence opening, from those items, citing them like [3].

Saved as marketmood_data/digests/<date>.html (+ .json); the daily job builds one after each run
and shows a macOS notification.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import subprocess
import sys

from marketmood import clock
from marketmood import announcements, earnings_calendar, explain, quotes
from marketmood.report import CSS

TEXT = {
    "en": {"title": "marketmood · Daily digest", "highlights": "Highlights", "moves": "Unusual moves",
           "anns": "Important announcements", "earnings": "New earnings reports", "calendar": "Reporting soon",
           "mood": "Strongest news mood", "none": "Nothing unusual today.", "why": "Why",
           "tone": "tone", "vs": "vs market", "few": "few headlines",
           "note": "Built from saved data; the opening was written by AI from the items below only. Not investment advice.",
           "notify": "{moves} unusual moves · {anns} important announcements · {earn} new reports",
           "no_explain": "No explanation yet (needs an LLM key).", "stocks": "{n} stocks"},
    "zh": {"title": "marketmood · 每日简报", "highlights": "今日要点", "moves": "异动", "anns": "重要公告",
           "earnings": "新发布的财报", "calendar": "即将发布财报", "mood": "新闻情绪最强/最弱",
           "none": "今天没有特别的事。", "why": "原因", "tone": "语气", "vs": "相对大盘", "few": "新闻较少",
           "note": "根据已保存的数据生成；开头的要点由 AI 仅根据下面列出的内容撰写。不构成投资建议。",
           "notify": "{moves} 只异动 · {anns} 条重要公告 · {earn} 份新财报",
           "no_explain": "还没有解释（需要 LLM 密钥）。", "stocks": "{n} 只股票"},
}


def digest_dir(data_dir: str) -> str:
    return os.path.join(data_dir, "digests")


def collect(app, lang: str, client=None, model_id: str | None = None, explain_top: int = 3) -> dict:
    """All digest sections for the dashboard's watchlist. `app` is a dashboard.Dashboard."""
    store = app._store()
    wl = app.settings["watchlist"]
    today = clock.today()
    since1 = (today - dt.timedelta(days=1)).isoformat()

    moves = explain.unusual_today(app.data_dir, wl, days=1)
    for i, m in enumerate(moves):
        m["name"] = app.name_of(m["ticker"])
        if i < explain_top and client is not None:
            try:
                x = explain.explain(store, client, model_id, app.data_dir, m["ticker"], m["day"], m["name"], lang)
                m["why"] = x.get("summary")
                m["evidence"] = x.get("evidence", [])
            except Exception as e:
                m["why_error"] = type(e).__name__

    anns = [dict(a, name=app.name_of(a["ticker"]))
            for a in announcements.recent(store, [t for t in wl if t.endswith((".SH", ".SZ", ".BJ", ".HK"))],
                                          days=2, min_importance=2, lang=lang)]
    earn = [a for a in app.alerts(lang, days=2)]
    cal = earnings_calendar.upcoming(app.data_dir, wl, days=5)
    for c in cal:
        c["name"] = app.name_of(c["ticker"])
    rows = [r for r in app.overview(lang) if r.get("mood") is not None and not r.get("few")]
    rows.sort(key=lambda r: r["mood"])
    mood = {"low": rows[:3], "high": rows[::-1][:3]}
    return {"date": today.isoformat(), "lang": lang, "moves": moves, "anns": anns[:12], "earnings": earn[:10],
            "calendar": cal[:10], "mood": mood, "watchlist": len(wl)}


def _items_for_llm(d: dict) -> list[str]:
    out = []
    for m in d["moves"]:
        out.append(f"move: {m['ticker']} {m['name']} {quotes.fmt_pct(m['ret'])} (vs market {quotes.fmt_pct(m['excess'])})"
                   + (f" — {m['why']}" if m.get("why") else ""))
    for a in d["anns"]:
        out.append(f"announcement: {a['ticker']} {a['name']} [{a['category_name']}] {a['title']}"
                   + (f" — {a['read']['summary']}" if a.get("read") else ""))
    for e in d["earnings"]:
        out.append(f"earnings: {e['ticker']} {e['name']} tone {e.get('tone')} SUE {e.get('sue')}")
    for c in d["calendar"]:
        out.append(f"upcoming report: {c['ticker']} {c['name']} on {c['date']}")
    return out


def highlights(client, d: dict) -> str | None:
    items = _items_for_llm(d)
    if client is None or not items:
        return None
    language = "Simplified Chinese" if d["lang"] == "zh" else "English"
    lines = "\n".join(f"[{i}] {t}" for i, t in enumerate(items, 1))
    data = client.chat_json(
        "Write the opening of an investor's daily digest about the stocks they follow.\n"
        f"Items (the ONLY facts you may use):\n{lines}\n\n"
        f"Write 3-4 short sentences in {language}: the most important things first, cite items like [2]. "
        "No advice, no predictions, no facts that are not in the items.\n"
        'Reply ONLY with JSON: {"text": "..."}')
    return str(data.get("text", ""))[:900] or None


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def render(d: dict, text: str | None) -> str:
    T = TEXT.get(d["lang"], TEXT["en"])
    pct = quotes.fmt_pct
    sec = []
    if text:
        sec.append(f"<section class='card'><h2>{_e(T['highlights'])}</h2><p class='big'>{_e(text)}</p></section>")
    if d["moves"]:
        li = "".join(
            f"<li><b>{_e(m['ticker'])}</b> {_e(m['name'])} <span class='chip {'positive' if m['ret'] > 0 else 'negative'}'>"
            f"{pct(m['ret'])}</span> <span class='note'>{_e(T['vs'])} {pct(m['excess'])} · {_e(m['day'])}</span>"
            + (f"<div class='why'>{_e(m['why'])}</div>" if m.get("why") else "") + "</li>" for m in d["moves"])
        sec.append(f"<section class='card'><h2>⚡ {_e(T['moves'])}</h2><ul class='dg'>{li}</ul></section>")
    if d["anns"]:
        li = "".join(
            f"<li><span class='note'>{_e(a['date'])}</span> <b>{_e(a['ticker'])}</b> {_e(a['name'])} "
            f"<span class='badge'>{_e(a['category_name'])}</span> <a href='{_e(a['url'])}'>{_e(a['title'].split(':', 1)[-1])}</a>"
            + (f"<div class='why'>{_e(a['read']['summary'])}</div>" if a.get("read") else "") + "</li>" for a in d["anns"])
        sec.append(f"<section class='card'><h2>{_e(T['anns'])}</h2><ul class='dg'>{li}</ul></section>")
    if d["earnings"]:
        def earn_line(e):
            tone = "—" if e.get("tone") is None else f"{e['tone']:+.2f}"
            sue = "" if e.get("sue") is None else f" · SUE {e['sue']:+.1f}"
            return (f"<li><b>{_e(e['ticker'])}</b> {_e(e['name'])} <span class='note'>{_e(e.get('date'))}</span> "
                    f"{_e(T['tone'])} {_e(tone)}{_e(sue)}</li>")
        li = "".join(earn_line(e) for e in d["earnings"])
        sec.append(f"<section class='card'><h2>{_e(T['earnings'])}</h2><ul class='dg'>{li}</ul></section>")
    if d["calendar"]:
        li = "".join(f"<li><span class='note'>{_e(c['date'])}</span> <b>{_e(c['ticker'])}</b> {_e(c['name'])}</li>"
                     for c in d["calendar"])
        sec.append(f"<section class='card'><h2>{_e(T['calendar'])}</h2><ul class='dg'>{li}</ul></section>")
    hi, lo = d["mood"]["high"], d["mood"]["low"]
    if hi or lo:
        cell = lambda rs: "".join(f"<li><b>{_e(r['ticker'])}</b> {_e(r['name'])} <span class='chip "
                                  f"{'positive' if r['mood'] > 0 else 'negative'}'>{r['mood']:+.2f}</span></li>" for r in rs)
        sec.append(f"<section class='card'><h2>{_e(T['mood'])}</h2><div class='cols2'><ul class='dg'>{cell(hi)}</ul>"
                   f"<ul class='dg'>{cell(lo)}</ul></div></section>")
    if len(sec) <= (1 if text else 0):
        sec.append(f"<section class='card'><p>{_e(T['none'])}</p></section>")
    css = CSS + (".dg{list-style:none;margin:0;padding:0}.dg li{padding:8px 0;border-top:1px solid var(--line)}"
                 ".dg li:first-child{border-top:none}.why{color:var(--muted);font-size:13px;margin-top:4px}"
                 ".big{font-size:16px;line-height:1.6}.badge{font-size:11px;border:1px solid var(--line);border-radius:6px;"
                 "padding:1px 6px}.cols2{display:grid;grid-template-columns:1fr 1fr;gap:16px}"
                 "@media(max-width:600px){.cols2{grid-template-columns:1fr}}a{color:var(--text)}")
    return (f"<!doctype html><html lang='{'zh-CN' if d['lang'] == 'zh' else 'en'}'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'><title>{_e(T['title'])} {d['date']}</title>"
            f"<style>{css}</style></head><body><div class='wrap'><header><h1>{_e(T['title'])}</h1>"
            f"<p>{_e(d['date'])} · {_e(T['stocks'].format(n=d['watchlist']))}</p></header>{''.join(sec)}"
            f"<p class='note' style='margin-top:18px'>{_e(T['note'])}</p></div></body></html>")


def build(app, lang: str, client=None, model_id: str | None = None) -> dict:
    """Collect, write the opening, save HTML + JSON. Returns {path, summary, data}."""
    d = collect(app, lang, client, model_id)
    try:
        text = highlights(client, d)
    except Exception:
        text = None
    os.makedirs(digest_dir(app.data_dir), exist_ok=True)
    base = os.path.join(digest_dir(app.data_dir), d["date"])
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write(render(d, text))
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump({"data": d, "text": text}, f, ensure_ascii=False, default=str)
    T = TEXT.get(lang, TEXT["en"])
    summary = T["notify"].format(moves=len(d["moves"]), anns=len(d["anns"]), earn=len(d["earnings"]))
    return {"path": base + ".html", "summary": summary, "text": text, "data": d}


def notify(title: str, message: str) -> None:
    """macOS notification (silently skipped elsewhere)."""
    if sys.platform != "darwin":
        return
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(["osascript", "-e", f'display notification "{esc(message)}" with title "{esc(title)}"'],
                   capture_output=True, timeout=10)


def list_dates(data_dir: str) -> list[str]:
    d = digest_dir(data_dir)
    if not os.path.isdir(d):
        return []
    return sorted((f[:-5] for f in os.listdir(d) if f.endswith(".html")), reverse=True)
