"""
Local dashboard: a small web server on your own computer (http://127.0.0.1:8765).

Uses only Python's standard library, so there is nothing extra to install.
It only listens on 127.0.0.1 (your machine), never on the network, and refuses
requests that come from other websites.

Pages and API:
  GET  /                  the dashboard
  GET  /api/state         watchlist, language, model, refresh progress
  GET  /api/overview      one row per stock: news mood + latest earnings
  GET  /api/stock?ticker= headlines, mood history, earnings detail for one stock
  POST /api/watchlist     {"tickers": ["AAPL", "T=AT&T"]}  (replace the list)
  POST /api/settings      {"lang": "zh"}
  POST /api/refresh       {"kind": "news" | "earnings"}   runs in the background
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pandas as pd

from stockproof import clock
from stockproof import __version__, code_stamp, announcements, cn, compare, core, digest, earnings_calendar, explain, quotes, research
from stockproof.companies import display_name
from stockproof.i18n import TEXT
from stockproof.llm import LLMClient, LLMError
from stockproof.store import Store
from stockproof.summary import daily_mood, summarize

MAX_LOG = 60


def _daily_last(data_dir: str):
    from stockproof.schedule import read_last
    last = read_last(data_dir)
    return {"finished": last.get("finished"), "ok": last.get("ok")} if last else None


def _clean(value):
    """Make pandas / numpy values JSON-friendly (NaN -> None)."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        value = value.item()
    if isinstance(value, float) and value != value:
        return None
    if isinstance(value, (pd.Timestamp, dt.date)):
        return value.strftime("%Y-%m-%d")
    return value


class Dashboard:
    def __init__(self, data_dir: str, provider: str, model: str | None, base_url: str | None,
                 per_ticker: int = 20, days: int = 7, min_relevance: float = 0.5, min_sample: int = 5):
        self.data_dir = data_dir
        self.store_path_dir = data_dir
        self.provider, self.model_name, self.base_url = provider, model, base_url
        self.per_ticker, self.days = per_ticker, days
        self.min_relevance, self.min_sample = min_relevance, min_sample
        self.settings_path = os.path.join(data_dir, "dashboard.json")
        os.makedirs(data_dir, exist_ok=True)
        self.settings = self._load_settings()
        self.lock = threading.Lock()
        self.echo = False                  # the CLI turns this on to print progress
        self.job = {"running": False, "kind": None, "done": 0, "total": 0, "current": "",
                    "log": [], "error": None, "finished_at": None}
        self._eps_cache = {}
        self.demo = None                   # {"as_of": ..., "model": ...} in `stockproof demo` (read-only, no key)

    # ---------- settings ----------
    def _load_settings(self) -> dict:
        if os.path.exists(self.settings_path):
            with open(self.settings_path, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
        data.setdefault("watchlist", [])
        data.setdefault("names", {})
        data.setdefault("lang", "en")
        return data

    def save_settings(self) -> None:
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, ensure_ascii=False, indent=2)

    def set_watchlist(self, entries: list[str]) -> None:
        tickers, names = [], dict(self.settings.get("names", {}))
        for e in entries:
            tk, _, name = str(e).partition("=")
            tk = cn.canonical(tk.strip().upper())
            if not tk or len(tk) > 12 or not all(c.isalnum() or c in ".-" for c in tk):
                continue
            if tk not in tickers:
                tickers.append(tk)
            if name.strip():
                names[tk] = name.strip()[:80]
        self.settings["watchlist"] = tickers
        self.settings["names"] = {k: v for k, v in names.items() if k in tickers}
        self.save_settings()

    def name_of(self, tk: str) -> str:
        return display_name(tk, self.settings.get("names"), self.data_dir)

    # ---------- data for the page ----------
    def _store(self) -> Store:
        return Store(self.data_dir)          # one connection per request thread

    def _sec(self):
        from stockproof.sec import SECCache
        return SECCache(self.data_dir)

    def _cik_map(self) -> dict:
        raw = self._sec().cached("company_tickers.json") or {}
        return {str(r["ticker"]).upper().replace(".", "-"): int(r["cik_str"]) for r in raw.values()}

    def _eps_history(self, tk: str, ciks: dict):
        """EPS/SUE history from saved files only (no network). Memoized by file time.
        US: SEC companyfacts file; China: cn/eps_<symbol>.json."""
        from stockproof.eps import add_sue, quarterly_eps
        info = cn.parse(tk)
        if info:
            path = os.path.join(self.data_dir, "cn", cn.eps_cache_name(info["symbol"]))
        elif tk in ciks:
            path = os.path.join(self._sec().dir, f"facts_{ciks[tk]}.json")
        else:
            return None
        if not os.path.exists(path):
            return None
        key = (path, os.path.getmtime(path))
        if key not in self._eps_cache:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            q = cn.eps_from_records(data) if info else quarterly_eps(data)
            self._eps_cache[key] = add_sue(q)
        return self._eps_cache[key]

    def _events(self, market: str):
        """Saved research events (8-K / actual dates only), memoized by file time."""
        path = os.path.join(research.results_dir(self.data_dir), f"{market}_earnings.csv")
        if not os.path.exists(path):
            return None
        key = (path, os.path.getmtime(path))
        if key not in self._eps_cache:
            ev = pd.read_csv(path, dtype={"accession": object})
            self._eps_cache[key] = ev[ev["date_source"] == "8-K"] if "date_source" in ev else ev
        return self._eps_cache[key]

    @staticmethod
    def _study_market(tk: str) -> str | None:
        info = cn.parse(tk)
        if not info:
            return "us"
        return None if info["market"] == "HK" else "cn"      # no Hong Kong study yet

    def _latest_report(self, tk: str, read: dict | None, hist) -> dict:
        """The latest announcement and the SUE that belongs to it (None while it isn't known yet:
        US companies publish the press release weeks before the 10-Q that carries the XBRL EPS)."""
        date = read.get("filed") if read else None
        sue, pending = None, False
        if hist is not None and hist["sue"].notna().any():
            last = hist.dropna(subset=["sue"]).iloc[-1]
            if date:
                gap = (pd.Timestamp(date) - pd.Timestamp(last["end"])).days
                # US results come within ~3 months of the quarter end; the previous quarter is
                # ~4 months back by then. A-share annual reports may come as late as April 30.
                limit = 95 if not cn.parse(tk) else 125
                if 0 <= gap <= limit:
                    sue = float(last["sue"])
                else:
                    pending = gap > limit
            else:
                sue = float(last["sue"])
                date = None
        return {"date": date, "sue": sue, "sue_pending": pending,
                "tone": read.get("tone") if read else None, "guidance": read.get("guidance") if read else None}

    def history(self, tk: str, rep: dict) -> dict:
        market = self._study_market(tk)
        if market is None:
            return {"market": None}
        ev = self._events(market)
        if ev is None:
            return {"market": market, "missing": True}
        return {"market": market, **research.history_for(ev, rep.get("sue"), rep.get("tone"))}

    def alerts(self, lang: str, days: int = 30) -> list[dict]:
        """Watchlist companies that reported in the last `days` days, newest first."""
        store = self._store()
        ciks = self._cik_map()
        since = (clock.today() - dt.timedelta(days=days)).isoformat()
        out = []
        for tk in self.settings["watchlist"]:
            read = store.latest_earnings(tk, lang)
            if not read or not read.get("filed") or str(read["filed"]) < since:
                continue
            rep = self._latest_report(tk, read, self._eps_history(tk, ciks))
            out.append({"ticker": tk, "name": self.name_of(tk), **rep, "history": self.history(tk, rep)})
        return _clean(sorted(out, key=lambda r: str(r["date"]), reverse=True))

    def _price_cols(self, tk: str) -> dict:
        try:
            q = quotes.summary(self.data_dir, tk)
        except Exception:
            q = None
        if not q:
            return {"d1": None, "d1_excess": None, "unusual": False}
        recent_day = q["date"] >= (clock.today() - dt.timedelta(days=5)).isoformat()
        return {"d1": q["d1"] if recent_day else None, "d1_excess": q["d1_excess"] if recent_day else None,
                "unusual": bool(q["move"] and q["move"]["date"] == q["date"] and recent_day)}

    def unusual(self) -> list[dict]:
        rows = explain.unusual_today(self.data_dir, self.settings["watchlist"])
        return _clean([{**r, "name": self.name_of(r["ticker"])} for r in rows])

    def compare_reports(self, tk: str, lang: str) -> dict:
        if self.demo:
            store = self._store()
            store.conn.executescript(compare.SCHEMA)
            row = store.conn.execute("SELECT result FROM report_comparisons WHERE ticker = ? ORDER BY (lang = ?) DESC, "
                                     "made_at DESC LIMIT 1", (tk, lang)).fetchone()
            return _clean(json.loads(row[0])) if row else {"error": "demo"}
        client = LLMClient.from_provider(self.provider, self.model_name, self.base_url)
        model_id = f"{self.provider}:{client.model}"
        sec = None
        if not cn.is_cn(tk):
            ciks = self._cik_map()
            sec = (self._sec(), {t: {"cik": c} for t, c in ciks.items()})
        try:
            return _clean(compare.compare(self._store(), client, model_id, tk, self.name_of(tk), lang, sec=sec))
        except compare.NotEnough as e:
            return {"error": str(e)}

    def explain_move(self, tk: str, day: str | None, lang: str) -> dict:
        if self.demo:                      # saved explanations only
            return _clean(explain.explain(self._store(), None, self.demo["model"], self.data_dir, tk, day,
                                          self.name_of(tk), lang))
        client = LLMClient.from_provider(self.provider, self.model_name, self.base_url)
        model_id = f"{self.provider}:{client.model}"
        return _clean(explain.explain(self._store(), client, model_id, self.data_dir, tk, day,
                                      self.name_of(tk), lang))

    def paper_overview(self, aid: str | None = None) -> dict:
        """Every paper account with its headline numbers; one account in full when `aid` is given."""
        from stockproof import paper
        store = self._store()
        accts = []
        for a in paper.accounts(store):
            st = paper.state(store, self.data_dir, a["id"])
            accts.append({k: st.get(k) for k in ("value", "return", "benchmark_return", "excess", "max_drawdown", "as_of",
                                                 "pending", "cancelled")} | {"id": a["id"], "name": a["name"],
                                                                             "kind": a["kind"], "note": a["note"],
                                                                             "start_day": a["start_day"], "market": a["market"]})
        out = {"accounts": accts}
        if aid:
            out["detail"] = paper.state(store, self.data_dir, aid)
            if (paper.account(store, aid) or {}).get("kind") == "strategy":
                out["gap"] = paper.gap(store, self.data_dir, aid)
        return _clean(out)

    def paper_action(self, body: dict) -> dict:
        from stockproof import paper
        store = self._store()
        act = body.get("action")
        zh = self.settings["lang"] == "zh"
        if act == "new":
            aid = paper.create_account(store, str(body.get("name") or ("模拟盘" if zh else "paper"))[:60],
                                       float(body.get("cash") or 1_000_000), body.get("market") if body.get("market") in ("cn", "us") else "cn")
            return {"id": aid}
        if act == "strategy":
            spec = paper.spec_from_experiment(self.data_dir, str(body.get("exp_id"))) if body.get("exp_id") else body.get("spec")
            aid = paper.create_strategy_account(store, self.data_dir, spec, float(body.get("cash") or 1_000_000),
                                                body.get("name"), self.settings["lang"])
            return {"id": aid}
        if act == "forecast":
            aid = paper.create_forecast_account(store, self.data_dir, str(body.get("horizon") or "6m"),
                                                int(body.get("n") or 50), float(body.get("cash") or 1_000_000),
                                                body.get("name"), self.settings["lang"])
            paper.step_forecast(store, self.data_dir, aid)
            return {"id": aid}
        if act in ("buy", "sell"):
            tk = str(body.get("ticker", "")).strip()
            tk = cn.canonical(tk) if cn.is_cn(tk) else tk.upper()
            if not re.fullmatch(r"[A-Z0-9.\-]{1,16}", tk):
                return {"error": "bad ticker"}
            oid = paper.place(store, str(body.get("account")), tk, act, shares=int(body.get("shares") or 0),
                              value=float(body.get("value") or 0), note=str(body.get("note") or ""))
            return {"id": oid}
        if act == "from_team":
            from stockproof import team
            store.conn.executescript(team.SCHEMA)
            row = store.conn.execute("SELECT result FROM team_calls WHERE id=?", (str(body.get("call_id")),)).fetchone()
            if not row:
                return {"error": "no such team call"}
            call = json.loads(row[0])
            call["call_id"] = body.get("call_id")
            oid = paper.from_team_call(store, str(body.get("account")), call, float(body.get("value") or 100_000))
            return {"id": oid} if oid else {"error": "团队观点是中性，没有下单" if zh else "neutral call: no order"}
        if act == "run":
            return _clean(paper.run_all(store, self.data_dir, fetch=not self.demo, log=lambda *a: None))
        return {"error": "unknown action"}

    def alerts_check(self, lang: str) -> dict:
        from stockproof import alerts
        store = self._store()
        new = alerts.watch(self, store, once=True, lang=lang, notify=False, log=lambda *a: None) if not self.demo else []
        return _clean({"new": new, "recent": alerts.recent(store, 50), "watching": alerts.watch_list(self, store),
                       "open": alerts.market_open(), "note": alerts.NOT_ORDER if lang == "zh" else alerts.NOT_ORDER_EN})

    def research_team(self, tk: str, lang: str, force: bool = False, question: str | None = None) -> dict:
        from stockproof import team
        store = self._store()
        if self.demo:
            team.score_calls(store, self.data_dir, fetch=False)
            hit = store.conn.execute("SELECT result FROM team_calls WHERE ticker=? ORDER BY made_at DESC",
                                     (tk,)).fetchone() if store.conn.execute(
                "SELECT name FROM sqlite_master WHERE name='team_calls'").fetchone() else None
            return _clean(json.loads(hit[0])) if hit else {"error": "demo"}
        client = LLMClient.from_provider(self.provider, self.model_name, self.base_url)
        model_id = f"{self.provider}:{client.model}"
        res = team.run(self, store, client, model_id, tk, lang, log=self._log, force=force, question=question)
        team.score_calls(store, self.data_dir, fetch=False)
        res["track_record"] = team.track_record(store, lang, limit=8)
        return _clean(res)

    def important_announcements(self, lang: str, days: int = 7) -> list[dict]:
        rows = announcements.recent(self._store(), [t for t in self.settings["watchlist"] if cn.is_cn(t)],
                                    days=days, min_importance=2, lang=lang)
        return _clean([{**r, "name": self.name_of(r["ticker"])} for r in rows])

    def calendar(self, days: int = 14) -> dict:
        saved = earnings_calendar.load(self.data_dir)
        items = earnings_calendar.upcoming(self.data_dir, self.settings["watchlist"], days)
        return _clean({"updated": saved.get("updated"), "errors": saved.get("errors", []),
                       "items": [{**i, "name": self.name_of(i["ticker"])} for i in items]})

    def _forecast(self, tk: str):
        info = cn.parse(tk)
        return cn.latest_forecast(info, cn.CNCache(self.data_dir), offline=True) if info else None

    def overview(self, lang: str) -> list[dict]:
        tickers = self.settings["watchlist"]
        if not tickers:
            return []
        store = self._store()
        since = (clock.today() - dt.timedelta(days=self.days)).isoformat()
        details = store.scored(tickers, None, lang, since=since, any_lang=True)
        summary = summarize(details, tickers, self.min_relevance, self.min_sample)
        ciks = self._cik_map()
        rows = []
        for _, r in summary.iterrows():
            tk = r["ticker"]
            read = store.latest_earnings(tk, lang)
            hist = self._eps_history(tk, ciks)
            sue = None
            if hist is not None and hist["sue"].notna().any():
                sue = float(hist["sue"].dropna().iloc[-1])
            rows.append({
                "ticker": tk, "name": self.name_of(tk),
                "mood": r["mood"], "few": bool(r["few"]), "relevant": int(r["relevant"]),
                "headlines": int(r["headlines"]), "positive": int(r["positive"]),
                "negative": int(r["negative"]),
                "e_filed": read["filed"] if read else None,
                "e_tone": read["tone"] if read else None,
                "e_guidance": read["guidance"] if read else None,
                "sue": sue,
                "market": (cn.parse(tk) or {}).get("market", "US"),
                **self._price_cols(tk),
            })
        return _clean(rows)

    def technical(self, ticker: str, lang: str) -> dict | None:
        """Candlestick chart data + technical facts (trend, support/resistance, signals)."""
        from stockproof import ta
        bars = quotes.load_bars(self.data_dir, ticker.upper())
        if len(bars.dropna(subset=["close"])) < 30:
            return None
        out = ta.analyze(bars, lang)
        out["chart"] = ta.chart_data(bars)
        return out

    def stock(self, ticker: str, lang: str) -> dict:
        tk = ticker.upper()
        store = self._store()
        df = store.scored([tk], None, lang, any_lang=True)
        recent = df[df["date"] >= (clock.today() - dt.timedelta(days=self.days)).isoformat()]
        heads = recent.sort_values(["relevance", "score"], ascending=[False, False])
        history = daily_mood(df, self.min_relevance)
        history = history[history["date"] >= (clock.today() - dt.timedelta(days=90)).isoformat()]
        hist = self._eps_history(tk, self._cik_map())
        read = store.latest_earnings(tk, lang)
        rep = self._latest_report(tk, read, hist)
        eps_rows = []
        if hist is not None:
            for q in hist.tail(8).iloc[::-1].itertuples():
                eps_rows.append({"end": q.end, "fiscal": q.fiscal, "eps": q.eps,
                                 "year_ago": q.eps_year_ago, "change": q.change, "sue": q.sue,
                                 "filed": q.filed, "q4": bool(q.q4_derived)})
        from stockproof import links
        hl = links.resolve_items([{"title": h.title, "link": h.link, "date": h.date, "source": h.source,
                                   "relevance": h.relevance, "score": h.score, "reason": h.reason,
                                   "lang": h.lang, "dup": pd.notna(getattr(h, "duplicate_of", None))}
                                  for h in heads.itertuples()], self.data_dir, online=False)  # cached/offline only
        return _clean({
            "ticker": tk, "name": self.name_of(tk),
            "headlines": hl,
            "history": [{"date": h.date, "mood": h.mood, "n": h.n} for h in history.itertuples()],
            "earnings": read,
            "report": rep,
            "history_like": self.history(tk, rep),
            "forecast": self._forecast(tk),
            "price": quotes.summary(self.data_dir, tk),
            "technical": self.technical(tk, lang),
            "announcements": announcements.recent(store, [tk], days=60, min_importance=1, lang=lang)[:30]
                             if cn.is_cn(tk) else [],
            "eps": eps_rows,
            "screen": self._screen_rank(tk, lang),
            "min_relevance": self.min_relevance,
        })

    def _screen_rank(self, tk: str, lang: str) -> dict | None:
        from stockproof import screener
        try:
            return screener.lookup(self.data_dir, tk, lang)
        except Exception:
            return None

    def screen_page(self, lang: str) -> dict:
        """The latest whole-market screen, its history test, and today's scorecards (for the 选股 tab)."""
        from stockproof import scorecard, screener
        saved = screener.load_latest(self.data_dir)
        test = None
        p = os.path.join(self.data_dir, "screens", "cn_backtest.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    bt = json.load(f)
                test = {"composite": {k: (bt.get("composite") or {}).get(k) for k in ("n", "ann_excess", "t", "hit_rate", "max_dd")},
                        "factors": bt.get("factors"), "updated": bt.get("updated")}
            except (OSError, ValueError):
                test = None
        cards = {c["ticker"]: {"score": c["overall"].get("score"), "label": c["overall"].get("label"),
                               "label_text": c["overall"].get("label_text")}
                 for c in scorecard.load_batch(self.data_dir)
                 if self.demo or c.get("day") == clock.today().isoformat()}
        if not saved:
            return {"meta": None, "results": [], "test": test, "cards": cards}
        return _clean({"meta": saved["meta"], "results": saved["results"], "test": test, "cards": cards})

    def scorecard(self, tk: str, lang: str, refresh: bool = False) -> dict:
        """One evidence scorecard (synchronous: ~5 s from saved data, ~1 min with refresh)."""
        from stockproof import scorecard
        if self.demo:
            saved = {c["ticker"]: c for c in scorecard.load_batch(self.data_dir)}
            if tk in saved:
                return saved[tk]
            return scorecard.build(self, self._store(), None, None, tk, lang)
        try:
            client = LLMClient.from_provider(self.provider, self.model_name, self.base_url)
            model_id = f"{self.provider}:{client.model}"
        except LLMError:
            client, model_id = None, None
        store = self._store()
        problems = []
        if refresh and client is not None:
            if self.echo:
                print(f"[scorecard] {tk}: refreshing news, report, announcements ...", flush=True)
            problems = scorecard.refresh_data(self, store, client, model_id, tk, lang, log=lambda m: None)
        card = scorecard.build(self, store, client, model_id, tk, lang, force=refresh)
        scorecard.save_batch(self.data_dir, [card])
        if self.echo:
            ov = card["overall"]
            print(f"[scorecard] {tk}: {ov.get('score')} {ov.get('label_text')}", flush=True)
        card["refresh_problems"] = problems
        return card

    def lab_caps(self) -> dict:
        from stockproof import lab
        try:
            return _clean(lab.capabilities(self.data_dir))
        except Exception as e:
            return {"types": {}, "error": f"{type(e).__name__}: {e}"}

    def state(self) -> dict:
        with self.lock:
            job = dict(self.job, log=list(self.job["log"][-12:]))
        model = self.model_name or ""
        try:
            from stockproof.llm import PROVIDERS
            model = model or PROVIDERS[self.provider]["model"]
        except KeyError:
            pass
        return {"version": __version__, "code": CODE_STAMP, "pid": os.getpid(), "watchlist": self.settings["watchlist"],
                "names": {tk: self.name_of(tk) for tk in self.settings["watchlist"]},
                "lang": self.settings["lang"], "model": f"{self.provider}:{model}", "job": job,
                "sec_contact": bool((os.environ.get("STOCKPROOF_SEC_CONTACT") or "").strip()),
                "research": {m: (research.saved_meta(self.data_dir, m) or {}).get("updated") for m in ("us", "cn")},
                "daily": _daily_last(self.data_dir), "demo": self.demo}

    def research_page(self, market: str, lang: str) -> str:
        from stockproof.research_report import build_research_report
        res = research.results_from_saved(self.data_dir, market)
        if res is None:
            return None
        return build_research_report(res, lang=lang)

    def _run_research(self, market: str, lang: str) -> None:
        """Re-run the study with the same price file as last time (US) or the saved A-share prices (cn)."""
        from stockproof import cli
        meta = research.saved_meta(self.data_dir, market) or {}
        argv = ["research", "--market", market, "--data-dir", self.data_dir, "--lang", lang,
                "--benchmark", meta.get("prices", {}).get("benchmark", "ew"),
                "--report", os.path.join(research.results_dir(self.data_dir), f"report_{market}.html")]
        if meta.get("prices_path"):
            argv += ["--prices", meta["prices_path"]]
        elif market == "us":
            raise RuntimeError("run `stockproof research --prices your_prices.csv` once in the terminal first")
        args = cli.build_parser().parse_args(argv)
        code = args.func(args)
        if code:
            raise RuntimeError(f"research stopped (code {code}); see the terminal")

    # ---------- background refresh ----------
    def _log(self, msg: str) -> None:
        if self.echo:                      # also show progress in the terminal
            with self.lock:
                n, total = self.job.get("done", 0), self.job.get("total", 0)
            step = f"{n + 1}/{total}" if n < total else "after"
            print(f"  [{self.job.get('kind', '')} {step}] {msg}", flush=True)
        with self.lock:
            self.job["log"].append(msg)
            self.job["log"] = self.job["log"][-MAX_LOG:]

    def start_refresh(self, kind: str) -> tuple[bool, str]:
        if self.demo:
            return False, "demo"
        with self.lock:
            if self.job["running"]:
                return False, "busy"
            tickers = list(self.settings["watchlist"])
            if kind in ("screen", "moneymap", "etf", "margin", "moneyhistory", "ntresearch", "forecast", "forecast_download"):
                tickers = [kind]                      # whole market, independent of the watchlist
            elif not tickers:
                return False, "empty"
            if kind.startswith("research_"):
                tickers = [kind]                      # one step; progress is printed in the terminal
            self.job = {"running": True, "kind": kind, "done": 0, "total": len(tickers), "current": "",
                        "log": [], "error": None, "finished_at": None}
        threading.Thread(target=self._run, args=(kind, tickers, self.settings["lang"]),
                         daemon=True).start()
        return True, "started"

    def _run(self, kind: str, tickers: list[str], lang: str) -> None:
        try:
            if kind.startswith("research_"):
                with self.lock:
                    self.job["current"] = kind
                self._run_research(kind.split("_", 1)[1], lang)
                with self.lock:
                    self.job["done"] = 1
                return
            if kind == "margin":
                from stockproof import margin
                with self.lock:
                    self.job["current"] = kind
                margin.history(self.data_dir, 20, fetch=True)
                with self.lock:
                    self.job["done"] = 1
                return
            if kind in ("forecast", "forecast_download"):
                from stockproof import forecast as fc
                with self.lock:
                    self.job["current"] = kind
                if kind == "forecast_download":
                    fc.download_prices(self.data_dir, log=self._log)
                fc.run(self.data_dir, log=self._log)
                with self.lock:
                    self.job["done"] = 1
                return
            if kind == "ntresearch":
                from stockproof import nt_research
                with self.lock:
                    self.job["current"] = kind
                nt_research.run(self.data_dir, log=self._log, fetch_etf=True)
                with self.lock:
                    self.job["done"] = 1
                return
            if kind == "moneyhistory":
                from stockproof import flows
                with self.lock:
                    self.job["current"] = kind
                r = flows.download_history(self.data_dir, "2016", log=self._log)
                self._log(f"history: {len(r['downloaded'])} quarters downloaded, {len(r['failed'])} failed")
                with self.lock:
                    self.job["done"] = 1
                return
            if kind == "etf":
                from stockproof import etf_flows
                with self.lock:
                    self.job["current"] = kind
                etf_flows.daily(self.data_dir, 60, fetch=True, log=self._log)
                with self.lock:
                    self.job["done"] = 1
                return
            if kind == "moneymap":
                from stockproof import flows
                with self.lock:
                    self.job["current"] = kind
                df = flows.holders(self.data_dir, None, fetch=True, log=self._log)
                self._log(f"money map: {len(df)} holder rows for {flows.latest_quarter()}")
                with self.lock:
                    self.job["done"] = 1
                return
            if kind == "screen":
                from stockproof import screener
                with self.lock:
                    self.job["current"] = kind
                res = screener.run(self.data_dir, lang=lang, log=self._log)
                self._log(f"screen: {res['meta']['screened']} stocks scored, top {len(res['results'])} saved")
                with self.lock:
                    self.job["done"] = 1
                return
            client = LLMClient.from_provider(self.provider, self.model_name, self.base_url)
            model_id = f"{self.provider}:{client.model}"
            store = self._store()
            sec = None
            if kind == "earnings" and any(not cn.is_cn(t) for t in tickers):
                from stockproof.sec import SECCache, SECError, contact
                try:
                    contact()
                    cache = SECCache(self.data_dir)
                    sec = (cache, cache.ticker_map())
                except SECError as e:
                    self._log(f"US stocks skipped: {e}")
            for tk in tickers:
                with self.lock:
                    self.job["current"] = tk
                if kind == "news":
                    res = core.scan_ticker(store, client, model_id, tk, self.name_of(tk),
                                           self.per_ticker, lang)
                    self._log(f"{tk}: {res['error']}" if res["error"]
                              else f"{tk}: {res['headlines']} headlines, {res['scored']} new scores")
                    fatal = res["fatal"]
                else:
                    name = self.name_of(tk)
                    row = core.earnings_any(store, self.data_dir, client, model_id, tk, lang,
                                            name=name if name != tk else None, sec=sec)
                    self._log(f"{tk}: " + ("; ".join(row["errors"]) if row["errors"]
                                           else ("read " + row["read"]["filed"] if row["read"] else "no report")))
                    fatal = row["fatal"]
                with self.lock:
                    self.job["done"] += 1
                if fatal:
                    raise LLMError("stopped: the LLM provider rejected the key or the balance is too low")
            if kind == "news":
                try:                                  # daily prices, for the "today" column and unusual moves
                    quotes.refresh(self.data_dir, tickers, log=self._log)
                except Exception as e:
                    self._log(f"prices: {type(e).__name__}: {e}")
            if kind == "news" and any(cn.is_cn(t) for t in tickers):
                try:                                  # Chinese company announcements (rules + LLM for important ones)
                    st = announcements.refresh(store, client, model_id, tickers,
                                               {t: self.name_of(t) for t in tickers}, lang, log=self._log)
                    self._log(f"announcements: {st['new']} new, {st['read']} summarized")
                except Exception as e:
                    self._log(f"announcements: {type(e).__name__}: {e}")
                    if core.is_fatal(e):
                        raise
            if kind == "earnings":
                try:                                  # who reports next: no LLM, a few requests
                    earnings_calendar.refresh(self.data_dir, tickers, log=self._log)
                except Exception as e:
                    self._log(f"calendar: {type(e).__name__}: {e}")
        except Exception as e:
            with self.lock:
                self.job["error"] = str(e)
        finally:
            with self.lock:
                self.job["running"] = False
                self.job["current"] = ""
                self.job["finished_at"] = dt.datetime.now().isoformat(timespec="seconds")
                err = self.job["error"]
            if self.echo:
                print(f"{kind} refresh stopped: {err}" if err else
                      (f"{kind} finished" if kind.startswith("research_")
                       else f"{kind} refresh finished ({len(tickers)} stocks)"), flush=True)


def make_handler(app: Dashboard, port: int):
    from stockproof.dashboard_page import PAGE

    allowed_origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = f"stockproof/{__version__}"

        def log_message(self, fmt, *args):      # keep the terminal quiet
            pass

        def _send(self, code: int, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else (
                body.encode("utf-8") if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode("utf-8"))
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _lang(self, qs) -> str:
            lang = (qs.get("lang") or [app.settings["lang"]])[0]
            return lang if lang in TEXT else "en"

        def do_GET(self):
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            try:
                if url.path == "/":
                    return self._send(200, PAGE, "text/html; charset=utf-8")
                if url.path == "/api/state":
                    return self._send(200, app.state())
                if url.path == "/api/i18n":
                    return self._send(200, TEXT[self._lang(qs)])
                if url.path == "/api/overview":
                    return self._send(200, app.overview(self._lang(qs)))
                if url.path == "/digest":
                    dates = digest.list_dates(app.data_dir)
                    day = (qs.get("date") or [dates[0] if dates else ""])[0]
                    if day not in dates:
                        t = TEXT[self._lang(qs)]
                        page = (f"<!doctype html><meta charset='utf-8'><body style='font:15px -apple-system,"
                                f"sans-serif;color:#6e6e73;padding:24px'>{html.escape(t['d_digest_none'])}</body>")
                        return self._send(200, page, "text/html; charset=utf-8")
                    with open(os.path.join(digest.digest_dir(app.data_dir), day + ".html"), encoding="utf-8") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                if url.path == "/api/digests":
                    return self._send(200, digest.list_dates(app.data_dir))
                if url.path == "/research":
                    market = (qs.get("market") or ["us"])[0]
                    if market not in ("us", "cn"):
                        return self._send(400, {"error": "market must be us or cn"})
                    page = app.research_page(market, self._lang(qs))
                    if page is None:
                        t = TEXT[self._lang(qs)]
                        page = (f"<!doctype html><meta charset='utf-8'><body style='font:15px -apple-system,"
                                f"sans-serif;color:#6e6e73;padding:24px'>{html.escape(t['d_research_none'])}</body>")
                    return self._send(200, page, "text/html; charset=utf-8")
                if url.path.startswith("/portfolio/"):
                    rid = url.path[11:]
                    from stockproof import portfolio
                    p = os.path.join(portfolio.pdir(app.data_dir), "reports", rid + ".html")
                    if not re.fullmatch(r"[0-9\-]{8,30}", rid) or not os.path.exists(p):
                        return self._send(404, {"error": "not found"})
                    with open(p, encoding="utf-8") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                if url.path == "/api/portfolio/reports":
                    from stockproof import portfolio
                    return self._send(200, portfolio.saved(app.data_dir))
                if url.path == "/api/lab/caps":
                    from stockproof import lab
                    return self._send(200, app.lab_caps())
                if url.path == "/api/lab":
                    from stockproof import lab
                    return self._send(200, lab.list_experiments(app.data_dir))
                if url.path.startswith("/lab/"):
                    exp = url.path[5:]
                    if not re.fullmatch(r"[0-9A-Za-z\-]{6,60}", exp):
                        return self._send(404, {"error": "not found"})
                    from stockproof import lab
                    p = os.path.join(lab.lab_dir(app.data_dir), "reports", exp + ".html")
                    if not os.path.exists(p):
                        return self._send(404, {"error": "not found"})
                    with open(p, encoding="utf-8") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                if url.path == "/api/moneymap":
                    from stockproof import flows
                    lang = self._lang(qs)
                    cat = (qs.get("category") or ["national"])[0]
                    if cat not in flows.LABEL:
                        return self._send(400, {"error": "unknown category"})
                    q = flows.latest_quarter()
                    p = os.path.join(flows.flows_dir(app.data_dir), f"holders_{q}.csv")
                    if not os.path.exists(p):
                        return self._send(200, {"need_download": True, "quarter": q})
                    res = flows.money_map(app.data_dir, cat, q, lang=lang, fetch=False, log=lambda *a: None)
                    ht_path = os.path.join(flows.flows_dir(app.data_dir), "history_tests.json")
                    if os.path.exists(ht_path):
                        try:
                            with open(ht_path, encoding="utf-8") as f:
                                ht = json.load(f)
                            res["history_test"] = {**{k: ht[k] for k in ("hold_days", "holdout_start", "quarters")},
                                                   **(ht["results"].get(cat) or {})}
                        except (OSError, ValueError, KeyError):
                            pass
                    res["categories"] = {k: v[0 if lang == "zh" else 1] for k, v in flows.LABEL.items()}
                    return self._send(200, res)
                if url.path == "/api/margin":
                    from stockproof import margin
                    return self._send(200, _clean(margin.market(app.data_dir, 20, fetch=False)))
                if url.path == "/api/team/call":
                    from stockproof import team
                    store = app._store()
                    store.conn.executescript(team.SCHEMA)
                    row = store.conn.execute("SELECT result FROM team_calls WHERE id=?", ((qs.get("id") or [""])[0],)).fetchone()
                    return self._send(200, json.loads(row[0]) if row else {"error": "not found"})
                if url.path == "/api/day":
                    from stockproof import dayinfo
                    tk = (qs.get("ticker") or [""])[0].upper()
                    day = (qs.get("date") or [""])[0]
                    if not re.fullmatch(r"[A-Z0-9.\-]{1,16}", tk) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                        return self._send(400, {"error": "bad request"})
                    return self._send(200, _clean(dayinfo.day_info(app._store(), app.data_dir, tk, day, self._lang(qs))))
                if url.path == "/api/paper":
                    return self._send(200, app.paper_overview((qs.get("id") or [None])[0]))
                if url.path == "/api/pxalerts":
                    from stockproof import alerts
                    return self._send(200, _clean({"recent": alerts.recent(app._store(), 50)}))
                if url.path == "/api/team/record":
                    from stockproof import team
                    store = app._store()
                    team.score_calls(store, app.data_dir, fetch=False)
                    return self._send(200, _clean(team.track_record(store, self._lang(qs), limit=30)))
                if url.path == "/api/forecast":
                    from stockproof import forecast as fc
                    res = fc.load(app.data_dir)
                    if res is None:
                        return self._send(200, {"need_run": True})
                    tk = (qs.get("ticker") or [""])[0].upper()
                    lang = self._lang(qs)
                    return self._send(200, _clean({"made": res["made"], "universe": res.get("universe"),
                                                   "summary": fc.summary_text(res, lang),
                                                   "stock": fc.stock_view(res, tk, lang) if tk else None}))
                if url.path == "/api/ntresearch":
                    from stockproof import nt_research
                    r = nt_research.load(app.data_dir)
                    if r is None:
                        return self._send(200, {"need_run": True})
                    zh = self._lang(qs) == "zh"
                    return self._send(200, _clean({**r, "summary": nt_research.summary_text(r, self._lang(qs)),
                                                   "kind_labels": nt_research.KIND_ZH if zh else {k: k for k in nt_research.KIND_ZH}}))
                if url.path == "/api/moneyhistory":
                    from stockproof import flows
                    import re as _re
                    n = len([f for f in os.listdir(flows.flows_dir(app.data_dir)) if _re.fullmatch(r"holders_\d{8}\.csv", f)])
                    return self._send(200, {"quarters": n})
                if url.path == "/api/etfflows":
                    from stockproof import etf_flows
                    r = etf_flows.summary(app.data_dir, 60, self._lang(qs), fetch=False, log=lambda *a: None)
                    if r.get("error"):
                        return self._send(200, {"need_download": True})
                    stale = (dt.date.today() - dt.date.fromisoformat(r["to"])).days > 4
                    return self._send(200, _clean({**r, "stale": stale}))
                if url.path == "/api/smartmoney":
                    from stockproof import flows
                    tk = (qs.get("ticker") or [""])[0].upper()
                    lang = self._lang(qs)
                    res = flows.stock_holders(app.data_dir, tk, quarters=1, lang=lang, fetch=False)
                    if not res.get("error"):
                        res["dragon_tiger"] = flows.dragon_tiger(app.data_dir, tk, days=30, fetch=not app.demo)[:8]
                        res["main_force"] = None if app.demo else flows.main_force(app.data_dir, tk, days=20)
                        try:
                            from stockproof import margin
                            res["margin"] = margin.stock(app.data_dir, tk, days=20, fetch=False)
                        except Exception:
                            res["margin"] = None
                        nm = app.name_of(tk)
                        res["name"] = res.get("stock_name") or nm if nm == tk else nm
                    return self._send(200, _clean(res))
                if url.path == "/api/breakouts":
                    from stockproof import market_scan
                    return self._send(200, market_scan.latest(app.data_dir) or {})
                if url.path == "/api/screen":
                    return self._send(200, app.screen_page(self._lang(qs)))
                if url.path == "/api/unusual":
                    return self._send(200, app.unusual())
                if url.path == "/api/announcements":
                    return self._send(200, app.important_announcements(self._lang(qs)))
                if url.path == "/api/calendar":
                    return self._send(200, app.calendar())
                if url.path == "/api/alerts":
                    return self._send(200, app.alerts(self._lang(qs)))
                if url.path == "/api/stock":
                    tk = (qs.get("ticker") or [""])[0]
                    if tk.upper() not in app.settings["watchlist"]:
                        return self._send(404, {"error": "not in watchlist"})
                    return self._send(200, app.stock(tk, self._lang(qs)))
                m = re.fullmatch(r"/chart/([A-Za-z0-9.^_\-]{1,16})\.svg", url.path)
                if m:                                 # a chart image, e.g. for DeepSeek Harness answers
                    from stockproof import chart_svg
                    tk = m.group(1).upper()
                    bars = quotes.load_bars(app.data_dir, tk)
                    if bars["high"].notna().sum() < 30 and not app.demo:
                        try:
                            quotes.update(app.data_dir, tk)
                            bars = quotes.load_bars(app.data_dir, tk)
                        except Exception:
                            pass
                    svg = chart_svg.render(bars, tk, app.name_of(tk), self._lang(qs))
                    return self._send(200, svg, "image/svg+xml; charset=utf-8")
                m = re.fullmatch(r"/card/(team|paper|lab)/([A-Za-z0-9.\-_]{1,64})\.svg", url.path)
                if m:                                 # a shareable result card
                    from stockproof import card
                    svg = card.render(m.group(1), m.group(2), app._store(), app.data_dir, self._lang(qs))
                    if svg is None:
                        return self._send(404, {"error": "not found"})
                    return self._send(200, svg, "image/svg+xml; charset=utf-8")
                if not url.path.startswith("/api/"):
                    # a mistyped or pasted address (e.g. extra characters after the slash): go home
                    self.send_response(302)
                    self.send_header("Location", "/")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return None
                return self._send(404, {"error": "not found"})
            except Exception as e:
                return self._send(500, {"error": f"{type(e).__name__}: {e}"})

        def do_POST(self):
            origin = self.headers.get("Origin")
            if origin and origin not in allowed_origins:
                return self._send(403, {"error": "requests from other websites are not allowed"})
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._send(415, {"error": "send JSON"})
            try:
                length = min(int(self.headers.get("Content-Length") or 0), 100_000)
                body = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._send(400, {"error": "bad JSON"})
            path = urlparse(self.path).path
            if path == "/api/watchlist":
                entries = body.get("tickers")
                if not isinstance(entries, list):
                    return self._send(400, {"error": "tickers must be a list"})
                app.set_watchlist(entries[:300])
                return self._send(200, app.state())
            if path == "/api/settings":
                if body.get("lang") in TEXT:
                    app.settings["lang"] = body["lang"]
                    app.save_settings()
                return self._send(200, app.state())
            if path == "/api/digest" and app.demo:
                return self._send(200, {"date": (digest.list_dates(app.data_dir) or [""])[0], "summary": ""})
            if path == "/api/digest":
                try:
                    client = LLMClient.from_provider(app.provider, app.model_name, app.base_url)
                    model_id = f"{app.provider}:{client.model}"
                except LLMError:
                    client, model_id = None, None
                dg = digest.build(app, app.settings["lang"], client, model_id)
                return self._send(200, {"date": dg["data"]["date"], "summary": dg["summary"]})
            if path == "/api/compare":
                tk = str(body.get("ticker", "")).upper()
                if tk not in app.settings["watchlist"]:
                    return self._send(404, {"error": "not in watchlist"})
                try:
                    return self._send(200, app.compare_reports(tk, app.settings["lang"]))
                except LLMError as e:
                    return self._send(502, {"error": str(e)})
                except Exception as e:
                    return self._send(200, {"error": f"{type(e).__name__}: {str(e)[:160]}"})
            if path == "/api/explain":
                tk = str(body.get("ticker", "")).upper()
                if tk not in app.settings["watchlist"]:
                    return self._send(404, {"error": "not in watchlist"})
                day = body.get("day")
                if day is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day)):
                    return self._send(400, {"error": "day must be YYYY-MM-DD"})
                try:
                    return self._send(200, app.explain_move(tk, day, app.settings["lang"]))
                except LLMError as e:
                    return self._send(502, {"error": str(e)})
            if path == "/api/team":
                from stockproof import team
                text = str(body.get("text") or "")[:500]
                tk = str(body.get("ticker", "")).upper() or (team.resolve(app, text) or "")
                if not tk:
                    zh = app.settings["lang"] == "zh"
                    return self._send(200, {"error": "没认出是哪只股票：请写上股票名称或代码，比如“分析一下科大讯飞”或“600519 能买吗”。"
                                            if zh else "Couldn't tell which stock: include its name or code, e.g. 'analyse NVDA'."})
                if not re.fullmatch(r"[A-Z0-9.^\-]{1,16}", tk):
                    return self._send(400, {"error": "bad ticker"})
                try:
                    return self._send(200, app.research_team(tk, app.settings["lang"], bool(body.get("force")),
                                                             text or None))
                except LLMError as e:
                    return self._send(502, {"error": str(e)})
                except Exception as e:
                    return self._send(200, {"error": f"{type(e).__name__}: {str(e)[:160]}"})
            if path == "/api/paper":
                try:
                    return self._send(200, app.paper_action(body))
                except Exception as e:
                    return self._send(200, {"error": f"{type(e).__name__}: {str(e)[:160]}"})
            if path == "/api/ask":
                from stockproof import ask
                text = str(body.get("text", ""))[:500]
                client = None
                if not app.demo:
                    try:
                        client = LLMClient.from_provider(app.provider, app.model_name, app.base_url)
                    except Exception:
                        client = None
                return self._send(200, _clean({**ask.route(app, text, client), "argv": ask.cli_argv(ask.route(app, text))}))
            if path == "/api/pxalerts":
                try:
                    return self._send(200, app.alerts_check(app.settings["lang"]))
                except Exception as e:
                    return self._send(200, {"error": f"{type(e).__name__}: {str(e)[:160]}"})
            if path == "/api/breakouts":
                if app.demo:
                    return self._send(200, {"message": "demo"})
                from stockproof import market_scan
                lang = body.get("lang") if body.get("lang") in ("en", "zh") else app.settings["lang"]
                try:
                    return self._send(200, market_scan.scan(app.data_dir, lang=lang, log=lambda *a: None))
                except Exception as e:
                    return self._send(200, {"error": f"{type(e).__name__}: {str(e)[:160]}"})
            if path == "/api/lab/reset":
                from stockproof import lab
                lab.reset(app.data_dir)
                return self._send(200, {"ok": True})
            if path in ("/api/lab/run", "/api/lab/confirm"):
                from stockproof import lab
                if app.demo:
                    return self._send(200, {"error": "demo"})
                try:
                    if path.endswith("run"):
                        r = lab.explore(app.data_dir, body.get("spec"), app.settings["lang"], log=lambda *a: None)
                    else:
                        r = lab.confirm(app.data_dir, str(body.get("id", "")), app.settings["lang"], log=lambda *a: None)
                    r["report_url"] = "/lab/" + r["id"]
                    return self._send(200, _clean(r))
                except lab.SpecError as e:
                    return self._send(200, {"error": str(e)})
                except Exception as e:
                    return self._send(200, {"error": f"{type(e).__name__}: {str(e)[:200]}"})
            if path == "/api/portfolio":
                from stockproof import portfolio
                if app.demo:
                    return self._send(200, {"error": "demo"})
                try:
                    client = LLMClient.from_provider(app.provider, app.model_name, app.base_url)
                except LLMError:
                    client = None
                try:
                    r = portfolio.checkup(app.data_dir, body.get("holdings"), lang=app.settings["lang"], client=client,
                                          log=lambda *a: None)
                    if isinstance(body.get("text"), str):
                        portfolio.remember(app.data_dir, body["text"])
                    return self._send(200, {"id": r["id"], "findings": r["findings"], "problems": r.get("problems")})
                except portfolio.HoldingsError as e:
                    return self._send(200, {"error": str(e)})
                except Exception as e:
                    return self._send(200, {"error": f"{type(e).__name__}: {str(e)[:160]}"})
            if path == "/api/scorecard":
                tk = cn.canonical(str(body.get("ticker", "")).strip().upper())
                if not tk or len(tk) > 12 or not all(c.isalnum() or c in ".-" for c in tk):
                    return self._send(400, {"error": "bad ticker"})
                try:
                    return self._send(200, app.scorecard(tk, app.settings["lang"], bool(body.get("refresh"))))
                except LLMError as e:
                    return self._send(502, {"error": str(e)})
                except Exception as e:
                    return self._send(200, {"error": f"{type(e).__name__}: {str(e)[:160]}"})
            if path == "/api/refresh":
                kind = body.get("kind")
                if kind not in ("news", "earnings", "research_us", "research_cn", "screen", "moneymap", "etf", "margin",
                                "moneyhistory", "ntresearch", "forecast", "forecast_download"):
                    return self._send(400, {"error": "unknown refresh kind"})
                ok, msg = app.start_refresh(kind)
                return self._send(200 if ok else 409, {"ok": ok, "message": msg})
            return self._send(404, {"error": "not found"})

    return Handler


def bind(app: Dashboard, port: int, tries: int = 20):
    """The server on `port`, or on the next free port when that one is taken (e.g. another stockproof)."""
    for p in range(port, port + tries):
        try:
            return ThreadingHTTPServer(("127.0.0.1", p), make_handler(app, p)), p
        except OSError:
            continue
    raise SystemExit(f"Ports {port}-{port + tries - 1} are all in use: close another program or pass --port.")


CODE_STAMP = 0                  # set when the server starts: which code this process is running


def serve(app: Dashboard, port: int = 8765, open_browser: bool = True) -> None:
    global CODE_STAMP
    CODE_STAMP = code_stamp()
    server, actual = bind(app, port)
    if actual != port:
        print(f"Port {port} is in use (maybe another stockproof page is open), using {actual} instead.")
    port = actual
    url = f"http://127.0.0.1:{port}/"
    print(f"stockproof dashboard running at {url}  (press Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
