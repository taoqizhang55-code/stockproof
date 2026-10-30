"""
Build the offline demo bundle (stockproof/demo_data) from a real stockproof_data folder.

    python tools/make_demo.py                      # uses ./stockproof_data
    python tools/make_demo.py --data-dir path --tickers AAPL NVDA 600519 ...

Copies only what the dashboard shows for a few stocks: their headlines and AI scores, earnings readings,
announcements, saved explanations / comparisons, prices, the latest screen and scorecards, the research
results and the policy study summary. API keys and personal settings are never copied (keys aren't stored
anywhere; the SEC contact lives only in your shell).

Before running it, make fresh scorecards so the demo has them:
    python -m stockproof scorecard --top 8
    python -m stockproof scorecard AAPL NVDA 600519 300750 000898 00700 --no-refresh
"""

import argparse
import datetime as dt
import json
import os
import shutil
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from stockproof import cn  # noqa: E402

DEFAULT = ["AAPL", "NVDA", "MSFT", "JPM", "MRK", "BABA", "600519.SH", "300750.SZ", "000898.SZ", "00700.HK",
           "09988.HK"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stockproof", "demo_data")
EPS_CONCEPTS = ["EarningsPerShareBasic", "EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"]


def copy(src, dst):
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return True
    return False


def latest(folder, prefix, suffix):
    if not os.path.isdir(folder):
        return None
    files = sorted(f for f in os.listdir(folder) if f.startswith(prefix) and f.endswith(suffix) and f[len(prefix):len(prefix) + 1].isdigit())
    return files[-1] if files else None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="stockproof_data")
    ap.add_argument("--tickers", nargs="*", default=DEFAULT)
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    src, OUT_DIR = a.data_dir, a.out
    tickers = [cn.canonical(t) for t in a.tickers]
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR)

    # --- the latest screen and scorecards (cards for the watchlist and the screen's top list)
    sd = os.path.join(src, "screens")
    screen_file = latest(sd, "cn_", ".json")
    screen = json.load(open(os.path.join(sd, screen_file), encoding="utf-8")) if screen_file else None
    if screen:
        os.makedirs(os.path.join(OUT_DIR, "screens"))
        screen["results"] = screen["results"][:20]
        keep = set(tickers) | {r["ticker"] for r in screen["results"]}
        screen["all"] = {k: v for k, v in screen.get("all", {}).items() if k in keep}
        json.dump(screen, open(os.path.join(OUT_DIR, "screens", screen_file), "w", encoding="utf-8"), ensure_ascii=False)
        copy(os.path.join(sd, "cn_backtest.json"), os.path.join(OUT_DIR, "screens", "cn_backtest.json"))
    cards_file = latest(sd, "scorecards_", ".json")
    n_cards = 0
    if cards_file:
        cards = json.load(open(os.path.join(sd, cards_file), encoding="utf-8"))
        cards = [c for c in cards if c.get("ticker") in (set(tickers) | {r["ticker"] for r in (screen or {}).get("results", [])})]
        n_cards = len(cards)
        json.dump(cards, open(os.path.join(OUT_DIR, "screens", cards_file), "w", encoding="utf-8"), ensure_ascii=False)

    # --- database rows for these tickers
    db = os.path.join(src, "stockproof.db")
    if not os.path.exists(db):                                    # name before 0.3
        db = os.path.join(src, "marketmood.db")
    con = sqlite3.connect(db)
    out = sqlite3.connect(os.path.join(OUT_DIR, "stockproof.db"))
    tables = {r[0]: r[1] for r in con.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")}
    marks = ",".join("?" * len(tickers))

    def take(table, where, params=()):
        if table not in tables:
            return 0
        out.execute(tables[table])
        rows = con.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()
        if rows:
            out.executemany(f"INSERT OR REPLACE INTO {table} VALUES ({','.join('?' * len(rows[0]))})", rows)
        return len(rows)

    counts = {
        "headlines": take("headlines", f"ticker IN ({marks})", tickers),
        "scores": take("scores", f"headline_id IN (SELECT id FROM headlines WHERE ticker IN ({marks}))", tickers),
        "earnings_reads": take("earnings_reads", f"ticker IN ({marks})", tickers),
        "announcements": take("announcements", f"ticker IN ({marks})", tickers),
        "announcement_reads": take("announcement_reads",
                                   f"art_code IN (SELECT art_code FROM announcements WHERE ticker IN ({marks}))", tickers),
        "move_explanations": take("move_explanations", f"ticker IN ({marks})", tickers),
        "report_comparisons": take("report_comparisons", f"ticker IN ({marks})", tickers),
    }
    for t in ("policy_reads", "scorecards"):                       # schemas only (cards are in screens/)
        if t in tables:
            out.execute(tables[t])
    out.commit()
    out.execute("VACUUM")
    out.close()

    # --- prices, calendar, digest, names, EPS history
    for t in tickers + ["^SPX", "^CSI300", "^HSI"]:
        name = t.replace("^", "_") + ".csv"
        copy(os.path.join(src, "quotes", name), os.path.join(OUT_DIR, "quotes", name))
    try:
        cal = json.load(open(os.path.join(src, "calendar.json"), encoding="utf-8"))
        if isinstance(cal, dict) and isinstance(cal.get("items"), list):
            cal["items"] = [i for i in cal["items"] if i.get("ticker") in tickers]
        elif isinstance(cal, dict):
            cal = {k: v for k, v in cal.items() if k in tickers or not isinstance(v, (dict, list))}
        json.dump(cal, open(os.path.join(OUT_DIR, "calendar.json"), "w", encoding="utf-8"), ensure_ascii=False)
    except (OSError, ValueError):
        pass
    day = latest(os.path.join(src, "digests"), "", ".json")
    if day:
        for ext in (".json", ".html"):
            copy(os.path.join(src, "digests", day[:-5] + ext), os.path.join(OUT_DIR, "digests", day[:-5] + ext))
    names = {}
    try:
        names = json.load(open(os.path.join(src, "cn", "names.json"), encoding="utf-8"))
    except (OSError, ValueError):
        pass
    os.makedirs(os.path.join(OUT_DIR, "cn"), exist_ok=True)
    json.dump({k: v for k, v in names.items() if k in tickers or (screen and k in screen.get("all", {}))},
              open(os.path.join(OUT_DIR, "cn", "names.json"), "w", encoding="utf-8"), ensure_ascii=False)
    for t in tickers:
        info = cn.parse(t)
        if info:
            copy(os.path.join(src, "cn", cn.eps_cache_name(info["symbol"])), os.path.join(OUT_DIR, "cn", cn.eps_cache_name(info["symbol"])))
    try:
        tick = json.load(open(os.path.join(src, "sec", "company_tickers.json"), encoding="utf-8"))
        tick = {k: v for k, v in tick.items() if str(v.get("ticker", "")).upper() in tickers}
        os.makedirs(os.path.join(OUT_DIR, "sec"), exist_ok=True)
        json.dump(tick, open(os.path.join(OUT_DIR, "sec", "company_tickers.json"), "w"))
        for v in tick.values():                                   # EPS facts only (the full files are MBs)
            p = os.path.join(src, "sec", f"facts_{int(v['cik_str'])}.json")
            if os.path.exists(p):
                facts = json.load(open(p, encoding="utf-8"))
                gaap = facts.get("facts", {}).get("us-gaap", {})
                slim = {"cik": facts.get("cik"), "entityName": facts.get("entityName"),
                        "facts": {"us-gaap": {c: gaap[c] for c in EPS_CONCEPTS if c in gaap}}}
                json.dump(slim, open(os.path.join(OUT_DIR, "sec", f"facts_{int(v['cik_str'])}.json"), "w"))
    except (OSError, ValueError):
        pass

    # --- research results and the policy study summary
    for m in ("us", "cn"):
        for f in (f"{m}_earnings.csv", f"{m}_news.csv", f"{m}_meta.json", f"{m}_backtest.json"):
            copy(os.path.join(src, "research", f), os.path.join(OUT_DIR, "research", f))
    lab_src = os.path.join(src, "lab")                           # the lab notebook and its reports
    if os.path.exists(os.path.join(lab_src, "trials.jsonl")):
        copy(os.path.join(lab_src, "trials.jsonl"), os.path.join(OUT_DIR, "lab", "trials.jsonl"))
        for f in os.listdir(os.path.join(lab_src, "reports")):
            if f.endswith(".html"):
                copy(os.path.join(lab_src, "reports", f), os.path.join(OUT_DIR, "lab", "reports", f))
    for f in ("results.json", "industry_map.json"):
        copy(os.path.join(src, "policy", f), os.path.join(OUT_DIR, "policy", f))

    meta = {"as_of": dt.date.today().isoformat(), "model": "deepseek:deepseek-chat", "watchlist": tickers,
            "lang": a.lang, "made": dt.datetime.now().isoformat(timespec="seconds")}
    json.dump({"watchlist": tickers, "names": {}, "lang": a.lang},
              open(os.path.join(OUT_DIR, "dashboard.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(meta, open(os.path.join(OUT_DIR, "demo.json"), "w", encoding="utf-8"), ensure_ascii=False)
    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(OUT_DIR) for f in fs)
    print(f"Demo bundle: {os.path.abspath(OUT_DIR)}  ({size / 1e6:.1f} MB)")
    print(f"  {len(tickers)} stocks · {n_cards} scorecards · " + ", ".join(f"{k} {v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
