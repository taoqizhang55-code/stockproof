"""
stockproof as an MCP server: the same engine as the dashboard, as tools an AI agent can call
(DeepSeek Harness, Claude, Cursor, any MCP client).

  python -m stockproof mcp                    # stdio server (what agents launch)
  python -m stockproof mcp --dsh-config       # print a DeepSeek Harness config entry for this computer

Every tool returns data computed by stockproof from news feeds, company filings and prices, with
links to the sources. The server's instructions ask the model to cite them, never to invent
numbers, and not to give buy/sell advice. Tools that call an LLM (why_did_it_move,
compare_with_last_report, refresh_stock, daily_digest with make_new) use the same API key as the
rest of stockproof and say so in their descriptions.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys

INSTRUCTIONS = """stockproof: stock news, earnings reports, company announcements, prices and research for
US stocks, China A-shares and Hong Kong stocks (codes like AAPL, 600519, 300750, 00700).

How to use it well:
- "What can you do?" / "你能做什么" / a greeting / first contact -> stockproof_menu() and show its "text" to the
  user in full (every group with examples, the / commands and the dashboard), not a shortened summary. If a tool
  result contains "welcome", do the same after answering.
  Daily-use tools (watchlist, stock_brief, why_did_it_move, compare_with_last_report, company_announcements,
  earnings_calendar, daily_digest) are as important as the lab: use whichever fits the question.
- Start with watchlist() or stock_brief(ticker). For a stock that isn't followed yet, call refresh_stock(ticker)
  first (about 30-60 seconds, a little LLM credit), then stock_brief.
- Numbers (returns, SUE, tone, base rates) come from the tools. Never invent figures, dates or news.
- Cite the source links the tools return when you state a fact from them.
- Charts / technicals / 支撑位 / 压力位 / K线 / 突破 -> technical_analysis(ticker) (open_chart=True to show the
  candlestick chart); it returns `chart_markdown` (an image of the candlestick chart with the zones): put it on
  its own line in your answer, exactly as given and not in a code block, then explain it. Only when that is
  missing, paste `text_chart` (a chart in characters) in a ``` code block. "Any signals today?" -> scan_signals (watchlist). "Which stocks broke out today?" / 全市场突破 /
  今天哪些股票放量突破 -> scan_market. Quote the rule given with each signal; these are observations, not orders.
- 国家队 / 社保 / 北向 / 险资 / 外资 买了什么, 资金地图 -> money_map(category); for the national team also call
  national_team_etf (since 2024 汇金 mostly buys broad ETFs, which top-10 holder lists never show). "Who holds X / 主力 / 龙虎榜" ->
  smart_money(ticker). Quarterly top-10 data is late and partial; main-force flow is an estimate: say so.
- "分析一下 X" / "X 能买吗" / "give me a view on X" -> research_team; pass what the user wants discussed as `question`
  in their words (e.g. "重点看扣非亏损会不会持续") (a cited multi-analyst view, logged and
  scored later; never present it as advice or an order). "How accurate is the team?" -> team_track_record.
- "长期怎么投、定投、资产配置、每月存多少钱怎么投" -> long_term_plan.
- "未来几个月/半年/一年会涨吗、长期走势" -> long_term_forecast (3/6/12-month rank with its track record; say if the
  model failed its test). Never forecast tomorrow's direction.
- "跟着国家队买能赚钱吗 / 预测国家队下季度买什么" -> national_team_research (not money_map).
- Not sure which tool fits a sentence -> ask(text) returns the tool and arguments to call. "做成卡片 / 分享 /
  share this" -> share_card(kind, id) for a team call_id, a paper account or a lab experiment id.
- 模拟盘 / paper trading -> paper_trading(action=...): list, show, new, buy, sell, run, gap, strategy (a lab
  experiment id), from_team (a team call id). Orders fill at the NEXT trading day's open under pessimistic rules
  (limit-up/down, 5% of volume, impact, T+1); records are append-only. Never claim a paper order was a real one, and
  never place real orders: stockproof has no broker connection. Only place a paper order when the user asks for it.
- 提醒 / alerts / 盯盘 -> price_alerts (zone breaks, team plan levels reached, paper fills); not orders. For continuous
  watching tell the user to run `stockproof alerts --watch` in a terminal.
- "Why did X move?" -> why_did_it_move. "What changed in the latest report?" -> compare_with_last_report.
  "Who reports soon?" -> earnings_calendar. "Anything important today?" -> daily_digest.
- Historical base rates (history_like, research_findings) are averages over many companies, not forecasts.
  The research found the post-earnings drift is not profitable after trading costs; say so if asked to trade on it.
- "Which stocks look strongest?" -> screen_stocks (A-shares, whole market, ranked shortlist with reasons).
  "What does the evidence say about X?" -> evidence_scorecard (dimensions with sources and whether each was
  validated historically). Present scores as evidence summaries, never as a buy/sell signal.
- QUANT LAB (this is what you cannot do without these tools): to test any trading idea on real point-in-time
  history, call lab_capabilities() once, then lab_backtest(spec). Translate the user's idea faithfully into a spec;
  if a condition isn't available, say so instead of approximating silently. Report the verdict text as given.
  Every new variant you try is counted and raises the bar; don't tweak parameters until something looks good —
  if you try several variants, tell the user how many and what the multiple-testing verdict says. When a result
  passes, offer lab_confirm(id): one run on the locked recent years, which can't be repeated. Every run also returns
  `stress` (the same test with all costs doubled; "fragile" = the edge dies at 2x costs) and `walk_forward` (each year,
  the best variant picked using only earlier years, scored on the next year; "fades" = the pick didn't hold up).
  Report both in plain words; a fragile or fading result is not a strategy to trade. Mention the report
  link (it opens in the browser). Use lab_similar for "what usually happens after a report like this one",
  lab_screen for custom conditions over all A-shares, lab_policy_history for 新闻联播 policy events.
  When you explain WHY a result looks the way it does (crowding, a sector cycle…), say it is a hypothesis
  unless the tool output shows it, and offer a test that could check it.
- DASHBOARD: the same features exist as a local web page. When the user asks for the dashboard / 网页看板 / 看板 / 网页版 / 仪表盘,
  or would rather click than type, call open_dashboard(tab). Don't open it unasked. After a lab run or portfolio check-up you may offer
  once to open the matching tab ("lab" / "portfolio"); don't open it unasked.
- PORTFOLIO CHECK-UP: when the user shares holdings (a list, or a broker screenshot you read), call
  portfolio_checkup with ticker + shares (or value / weight). Report the findings and the report link; explain
  concentration, overlap and stress-test numbers in plain words. Never tell them what to buy or sell.
- Do not give buy/sell recommendations. Describe the evidence, the uncertainty and what the data does not show.
- Answer in the user's language."""


def _server_class():
    try:
        from mcp.server.mcpserver import MCPServer          # MCP Python SDK 2.x
        return MCPServer
    except ImportError:
        try:
            from mcp.server.fastmcp import FastMCP           # MCP Python SDK 1.x
            return FastMCP
        except ImportError as e:
            raise SystemExit("The MCP server needs the MCP SDK (Python 3.10+):  pip install mcp") from e


class Tools:
    """The tool implementations, independent of the MCP SDK (so they can be tested directly)."""

    def __init__(self, data_dir: str, provider: str = "deepseek", model: str | None = None,
                 base_url: str | None = None):
        from stockproof.dashboard import Dashboard
        self.app = Dashboard(data_dir, provider, model, base_url)
        self.app.echo = False
        self.auto_dashboard = False          # opt-in: open the dashboard by itself the very first time
        self.welcome = False                 # set by the MCP server: first answer ever introduces everything
        self._auto_done = False

    # ---------------------------------------------------------------- helpers
    def _lang(self, lang: str | None) -> str:
        return lang if lang in ("en", "zh") else self.app.settings.get("lang", "en")

    def _tk(self, ticker: str) -> str:
        from stockproof import cn
        return cn.canonical(str(ticker).strip().upper())

    def _clean(self, x):
        from stockproof.dashboard import _clean
        return _clean(x)

    # ---------------------------------------------------------------- tools
    def watchlist(self, lang: str | None = None) -> dict:
        lang = self._lang(lang)
        rows = self.app.overview(lang)
        keep = ("ticker", "name", "d1", "unusual", "mood", "few", "relevant", "headlines",
                "e_filed", "e_tone", "e_guidance", "sue", "market")
        state = self.app.state()
        return self._clean({"stocks": [{k: r.get(k) for k in keep} for r in rows],
                            "last_automatic_update": (state.get("daily") or {}).get("finished"),
                            "fields": {"d1": "today's return", "mood": "relevance-weighted news mood -1..1 (last 7 days)",
                                       "relevant": "relevant headlines", "e_tone": "LLM tone of the latest earnings report -1..1",
                                       "sue": "standardized earnings surprise of the latest quarter",
                                       "unusual": "today's move is unusual for this stock"}})

    def stock_brief(self, ticker: str, lang: str | None = None) -> dict:
        from stockproof import earnings_calendar
        lang, tk = self._lang(lang), self._tk(ticker)
        if tk not in self.app.settings["watchlist"]:
            return {"ticker": tk, "followed": False,
                    "hint": "Not in the watchlist yet: call refresh_stock to fetch its news, earnings and prices."}
        d = self.app.stock(tk, lang)
        heads = [h for h in d["headlines"] if (h.get("relevance") or 0) >= d["min_relevance"] and not h.get("dup")][:8]
        e = d.get("earnings") or {}
        nxt = [c for c in earnings_calendar.upcoming(self.app.data_dir, [tk], days=60)][:1]
        return self._clean({
            "ticker": tk, "name": d["name"], "followed": True,
            "price": d.get("price"),
            "news": [{k: h.get(k) for k in ("date", "title", "link", "score", "reason", "source")} for h in heads],
            "latest_earnings": {k: e.get(k) for k in ("filed", "period", "tone", "guidance", "summary", "revenue_growth",
                                                     "eps", "key_points", "risks", "url", "doc_title")} if e else None,
            "earnings_surprise": d.get("report"),
            "after_similar_reports": d.get("history_like"),
            "next_report": nxt[0] if nxt else None,
            "forecast": d.get("forecast"),
            "announcements": [{k: a.get(k) for k in ("date", "title", "category_name", "importance", "url", "read")}
                              for a in (d.get("announcements") or [])[:10]],
        })

    def why_did_it_move(self, ticker: str, date: str | None = None, lang: str | None = None) -> dict:
        tk = self._tk(ticker)
        if tk not in self.app.settings["watchlist"]:
            return {"error": "not followed; call refresh_stock first"}
        return self.app.explain_move(tk, date, self._lang(lang))

    def technical_analysis(self, ticker: str, open_chart: bool = False, lang: str | None = None) -> dict:
        from stockproof import quotes, ta
        tk = self._tk(ticker)
        bars = quotes.load_bars(self.app.data_dir, tk)
        if bars["high"].notna().sum() < 30:                     # missing or closes only: fetch full bars
            try:
                quotes.update(self.app.data_dir, tk)
                bars = quotes.load_bars(self.app.data_dir, tk)
            except Exception as e:
                if len(bars.dropna(subset=["close"])) < 30:
                    return {"error": f"prices unavailable ({type(e).__name__}: {str(e)[:120]})"}
        out = ta.analyze(bars, self._lang(lang))
        if "error" in out:
            return out
        out = {"ticker": tk, "name": self.app.name_of(tk), **out}
        img = self._chart_image(tk, out.get("date", ""), self._lang(lang))
        if img:
            out["chart_markdown"] = img
            out["chart_howto"] = ("Put chart_markdown on its own line at the top of your answer, exactly as given, "
                                  "NOT in a code block: it renders as the candlestick chart image.")
        else:
            out["text_chart"] = ta.text_chart(bars, out.get("zones"), lang=self._lang(lang))
            out["chart_howto"] = "Paste text_chart verbatim inside a ``` code block (a chart drawn in characters)."
        if tk in self.app.settings["watchlist"]:
            out["chart_url"] = f"http://127.0.0.1:8765/#stock={tk}"
            if open_chart:
                out["dashboard"] = self.open_dashboard(f"stock={tk}")
        else:
            out["chart"] = "follow the stock (refresh_stock) to see its candlestick chart in the dashboard"
        return self._clean(out)

    def money_map(self, category: str = "national", quarter: str | None = None, lang: str | None = None) -> dict:
        from stockproof import flows
        lang = self._lang(lang)
        if category not in flows.LABEL:
            return {"error": f"category must be one of {list(flows.LABEL)}"}
        try:
            out = flows.money_map(self.app.data_dir, category, quarter, lang=lang, log=lambda *a: None)
            ht = flows.history_tests(self.app.data_dir, log=lambda *a: None)
            if ht and category in ht.get("results", {}):
                out["history_test"] = {"what": f"buy at the next close after the disclosure, hold {ht['hold_days']} days, "
                                               f"vs equal-weighted CSI 300 members, after costs, before {ht['holdout_start']}",
                                       **ht["results"][category]}
                out["history_test_howto"] = ("Report this next to the map: copying these disclosed moves has NOT beaten "
                                             "the market historically unless ann > 0 with t > 2. Say so plainly.")
            return self._clean(out)
        except Exception as e:
            return {"error": f"holder data unavailable ({type(e).__name__}: {str(e)[:120]})"}

    def national_team_etf(self, days: int = 60, lang: str | None = None) -> dict:
        from stockproof import etf_flows
        days = max(10, min(int(days), 250))
        try:
            r = etf_flows.summary(self.app.data_dir, days, self._lang(lang), log=lambda *a: None)
        except Exception as e:
            return {"error": f"ETF data unavailable ({type(e).__name__}: {str(e)[:120]})"}
        if "daily" in r:
            r["daily"] = r["daily"][-20:]
        return self._clean(r)

    def market_leverage(self, lang: str | None = None) -> dict:
        from stockproof import margin
        try:
            r = margin.market(self.app.data_dir, 20)
        except Exception as e:
            return {"error": f"margin data unavailable ({type(e).__name__})"}
        for x in r.values():
            x.pop("daily", None)
        return self._clean({**r, "note": "融资余额 = money borrowed to buy stocks. Totals compare only stocks eligible "
                                         "on both days. Describe the trend; it is not a forecast."})

    def smart_money(self, ticker: str, lang: str | None = None) -> dict:
        from stockproof import cn, flows
        tk = self._tk(ticker)
        if not cn.is_cn(tk) or cn.parse(tk)["market"] == "HK":
            return {"error": "smart-money data is for China A-shares"}
        lang = self._lang(lang)
        out = {"ticker": tk, "name": self.app.name_of(tk)}
        try:
            out["holders"] = flows.stock_holders(self.app.data_dir, tk, quarters=2, lang=lang, log=lambda *a: None)
        except Exception as e:
            out["holders"] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
        out["dragon_tiger"] = flows.dragon_tiger(self.app.data_dir, tk, days=30)[:10]
        out["main_force_estimate"] = flows.main_force(self.app.data_dir, tk, days=20)
        try:
            from stockproof import margin
            m = margin.stock(self.app.data_dir, tk, days=20)
            if m and m.get("series"):
                m["series"] = m["series"][-5:]
            out["margin_financing"] = m
        except Exception:
            out["margin_financing"] = None
        out["note"] = ("Top-10 holders are quarterly and late; 龙虎榜 shows only days the stock hit an exchange "
                       "threshold; main-force flow is an order-size ESTIMATE. None of these has been history-tested "
                       "as a signal yet: present them as facts about who holds / traded, not as predictions.")
        return self._clean(out)

    def _chart_image(self, tk: str, day: str, lang: str) -> str | None:
        """Markdown for the chart image served by the local dashboard (started in the background if needed)."""
        if os.environ.get("STOCKPROOF_CHART_IMAGES", "1") == "0":
            return None
        port = 8765
        r = self.open_dashboard("home", port=port, open_browser=False, _wait=20.0)
        if r.get("error"):
            return None
        from urllib.parse import quote
        title = ("K线图" if lang == "zh" else "candlestick chart")
        return f"![{self.app.name_of(tk)} {title}](http://127.0.0.1:{port}/chart/{quote(tk)}.svg?lang={lang}&d={day})"

    def scan_signals(self, days: int = 3, lang: str | None = None) -> dict:
        from stockproof import quotes, ta
        days = max(1, min(int(days), 20))
        rules = ta.RULES if self._lang(lang) == "zh" else ta.RULES_EN
        hits = []
        for tk in self.app.settings["watchlist"]:
            bars = quotes.load_bars(self.app.data_dir, tk)
            if len(bars.dropna(subset=["close"])) < 40:
                continue
            for sg in ta.signals(bars, days=days):
                hits.append({"ticker": tk, "name": self.app.name_of(tk), **sg, "rule": rules[sg["kind"]]})
        order = {k: i for i, k in enumerate(["breakout", "breakdown", "pullback", "golden_cross", "death_cross"])}
        hits.sort(key=lambda h: (h["date"], -order.get(h["kind"], 9)), reverse=True)
        return self._clean({"days": days, "signals": hits[:80],
                            "note": "Signals describe price action, not forecasts. Test one on history with lab_backtest."})

    def scan_market(self, direction: str = "both", refresh: bool = True, lang: str | None = None) -> dict:
        from stockproof import market_scan
        lang = self._lang(lang)
        res = None
        if refresh:
            try:
                res = market_scan.scan(self.app.data_dir, direction if direction in ("up", "down") else "both",
                                       lang=lang, log=lambda *a: None)
            except Exception as e:
                res = market_scan.latest(self.app.data_dir)
                if res is None:
                    return {"error": f"market list unavailable ({type(e).__name__}); try again later"}
                res = {**res, "stale": f"live scan failed ({type(e).__name__}); showing the last saved scan"}
        else:
            res = market_scan.latest(self.app.data_dir)
            if res is None:
                return {"error": "no scan saved yet; call with refresh=True"}
        return self._clean({**res, "hits": res["hits"][:40]})

    def compare_with_last_report(self, ticker: str, lang: str | None = None) -> dict:
        tk = self._tk(ticker)
        if tk not in self.app.settings["watchlist"]:
            return {"error": "not followed; call refresh_stock first"}
        return self.app.compare_reports(tk, self._lang(lang))

    def company_announcements(self, ticker: str, days: int = 30, important_only: bool = True,
                              lang: str | None = None) -> dict:
        from stockproof import announcements, cn
        tk = self._tk(ticker)
        if not cn.is_cn(tk):
            return {"error": "announcements are tracked for China A-shares and Hong Kong stocks; "
                             "for US stocks see latest_earnings in stock_brief"}
        rows = announcements.recent(self.app._store(), [tk], days=max(1, min(int(days), 365)),
                                    min_importance=2 if important_only else 1, lang=self._lang(lang))
        return self._clean({"ticker": tk, "announcements": rows[:40]})

    def earnings_calendar(self, days: int = 14) -> dict:
        return self.app.calendar(max(1, min(int(days), 60)))

    def daily_digest(self, make_new: bool = False, lang: str | None = None) -> dict:
        from stockproof import digest
        lang = self._lang(lang)
        if make_new:
            client, model_id = self._client()
            out = digest.build(self.app, lang, client, model_id)
            return self._clean({"date": out["data"]["date"], "highlights": out["text"], "summary": out["summary"],
                                "sections": out["data"]})
        dates = digest.list_dates(self.app.data_dir)
        if not dates:
            return {"error": "no digest yet; call daily_digest with make_new=true"}
        with open(os.path.join(digest.digest_dir(self.app.data_dir), dates[0] + ".json"), encoding="utf-8") as f:
            saved = json.load(f)
        return self._clean({"date": dates[0], "highlights": saved.get("text"), "sections": saved.get("data")})

    def research_findings(self, market: str = "us") -> dict:
        from stockproof import research
        if market not in ("us", "cn"):
            return {"error": "market must be us or cn"}
        res = research.results_from_saved(self.app.data_dir, market)
        if res is None:
            return {"error": f"no study saved for {market}; run `stockproof research` first"}
        e, b = res.get("earnings") or {}, res.get("backtest") or {}

        def table(t):
            return t.to_dict("records") if hasattr(t, "to_dict") else t
        out = {"market": market, "updated": res.get("updated"), "announcements": e.get("n"),
               "by_surprise": table(e.get("sue_table")),
               "date_check": {k: table(v) for k, v in (e.get("by_source") or {}).items()},
               "llm_tone": {"n": e.get("n_tone"), "by_tone": table(e.get("tone_table")),
                            "regressions": e.get("reg_tone")} if e.get("n_tone") else None,
               "backtest": {k: b.get(k) for k in ("params", "n_long", "long_excess", "long_excess_gross",
                                                   "long_short", "long_trade", "short_trade")} if b else None,
               "notes": ["reaction = market-adjusted return on days 0-1 after the announcement; drift = days 2-61",
                         "t-statistics above about 2 are unlikely to be luck",
                         "averages over many companies, not a forecast for any one stock"]}
        return self._clean(out)

    def screen_stocks(self, top: int = 20, ticker: str | None = None, lang: str | None = None) -> dict:
        from stockproof import screener
        lang = self._lang(lang)
        if ticker:
            return self._clean({"ticker": self._tk(ticker), **screener.lookup(self.app.data_dir, ticker, lang)})
        saved = screener.load_latest(self.app.data_dir)
        if not saved:
            return {"error": "no screen saved yet; run `stockproof screen` in the terminal first"}
        keep = ("rank", "ticker", "name", "industry", "score", "reasons", "cap", "pe", "end", "public")
        return self._clean({"as_of": saved["meta"].get("as_of"), "screened": saved["meta"].get("screened"),
                            "method": "average percentile of earnings surprise, revenue growth, profit growth, "
                                      "annualized ROE and 60-day return; at most 3 per industry",
                            "history_test": self._screen_test(),
                            "results": [{k: r.get(k) for k in keep} for r in saved["results"][:max(1, min(top, 50))]],
                            "note": "A shortlist to research further, not a forecast or advice."})

    def _screen_test(self):
        import json as _json
        p = os.path.join(self.app.data_dir, "screens", "cn_backtest.json")
        try:
            with open(p, encoding="utf-8") as f:
                c = _json.load(f).get("composite") or {}
            return {k: c.get(k) for k in ("n", "ann_excess", "t", "hit_rate")}
        except (OSError, ValueError):
            return None

    def evidence_scorecard(self, ticker: str, refresh: bool = False, lang: str | None = None) -> dict:
        from stockproof import scorecard
        from stockproof.store import Store
        lang, tk = self._lang(lang), self._tk(ticker)
        client, model_id = self._client()
        store = Store(self.app.data_dir)
        problems = []
        if refresh and client is not None:
            try:
                problems = scorecard.refresh_data(self.app, store, client, model_id, tk, lang, log=lambda m: None)
            except RuntimeError as e:
                return {"error": str(e)}
        card = scorecard.build(self.app, store, client, model_id, tk, lang)
        card["refresh_problems"] = problems
        return self._clean(card)

    def research_team(self, ticker: str, question: str | None = None, lang: str | None = None) -> dict:
        from stockproof import team
        from stockproof.store import Store
        lang, tk = self._lang(lang), self._tk(ticker)
        client, model_id = self._client()
        if client is None:
            return {"error": "the research team needs an LLM key (DEEPSEEK_API_KEY)"}
        store = Store(self.app.data_dir)
        try:
            res = team.run(self.app, store, client, model_id, tk, lang, log=lambda *a: None, question=question)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:200]}"}
        team.score_calls(store, self.app.data_dir, fetch=False)
        res["track_record"] = team.track_record(store, lang, limit=5)["summary"]
        res.pop("evidence_full", None)
        res["howto"] = ("Lead with the final stance + confidence + horizon, then the plan (levels are from the computed "
                        "zones; they are things to watch, not orders), risks and what would change the view. Mention "
                        "cap_note verbatim if present. Offer the analysts' and the debate's details on request. Cite "
                        "evidence ids as given. Mention it was written to the forward log (call_id) and will be scored.")
        return self._clean(res)

    def paper_trading(self, action: str = "list", account: str | None = None, ticker: str | None = None,
                      shares: int | None = None, value: float | None = None, name: str | None = None,
                      cash: float | None = None, experiment_id: str | None = None, call_id: str | None = None,
                      lang: str | None = None) -> dict:
        from stockproof import paper
        from stockproof.store import Store
        store = Store(self.app.data_dir)
        zh = self._lang(lang) == "zh"
        rules = ("下一个交易日开盘成交，涨停不买、跌停不卖，最多当天成交量的 5%，冲击成本，T+1；记录不可修改。这是模拟盘，不是实盘委托。"
                 if zh else "Fills at the next open; no buys at limit-up / sells at limit-down; 5% of volume; impact; T+1; "
                 "append-only. Paper only, not a real order.")
        try:
            acct = paper.find_account(store, account) if account else None
            if action in ("buy", "sell", "show", "gap", "from_team") and not acct:
                return {"error": "no such paper account", "accounts": paper.accounts(store)}
            if action == "new":
                aid = paper.create_account(store, name or ("模拟盘" if zh else "paper"), cash or 1_000_000)
                return {"id": aid, "rules": rules}
            if action == "plan":
                aid = paper.create_plan_account(store, self.app.data_dir, name if name in ("conservative", "balanced", "growth") else "balanced",
                                                cash or 1_000_000, None, self._lang(lang))
                paper.step_plan(store, self.app.data_dir, aid)
                return {"id": aid, "account": paper.account(store, aid), "rules": rules}
            if action == "forecast":
                aid = paper.create_forecast_account(store, self.app.data_dir, "6m", 50, cash or 1_000_000, name, self._lang(lang))
                paper.step_forecast(store, self.app.data_dir, aid)
                return {"id": aid, "account": paper.account(store, aid), "rules": rules,
                        "howto": "Holds the 6-month forecast's top 50, rebalanced quarterly; buys fill at the next open."}
            if action == "strategy":
                if not experiment_id:
                    return {"error": "give experiment_id (from lab_backtest / lab_experiments)"}
                spec = paper.spec_from_experiment(self.app.data_dir, experiment_id)
                aid = paper.create_strategy_account(store, self.app.data_dir, spec, cash or 1_000_000, name, self._lang(lang))
                return {"id": aid, "account": paper.account(store, aid), "rules": rules,
                        "howto": "From today on, each daily run places the strategy's orders; compare later with action=gap."}
            if action in ("buy", "sell"):
                tk = self._tk(ticker or "")
                oid = paper.place(store, acct["id"], tk, action, shares=shares or 0, value=value or 0, source="agent")
                return {"order_id": oid, "account": acct["name"], "ticker": tk, "rules": rules}
            if action == "from_team":
                import json as _json
                from stockproof import team
                store.conn.executescript(team.SCHEMA)
                row = store.conn.execute("SELECT result FROM team_calls WHERE id=?", (call_id or "",)).fetchone()
                if not row:
                    return {"error": "no such team call id"}
                call = {**_json.loads(row[0]), "call_id": call_id}
                return {"order_id": paper.from_team_call(store, acct["id"], call, value or 100_000), "rules": rules}
            if action == "run":
                return self._clean(paper.run_all(store, self.app.data_dir, fetch=True, log=lambda *a: None))
            if action == "gap":
                return self._clean(paper.gap(store, self.app.data_dir, acct["id"]))
            if action == "show":
                st = paper.state(store, self.app.data_dir, acct["id"])
                st["nav"] = st["nav"][-30:]
                st["orders"] = st["orders"][-20:]
                return self._clean(st)
            out = []
            for a in paper.accounts(store):
                st = paper.state(store, self.app.data_dir, a["id"])
                out.append({k: st.get(k) for k in ("value", "return", "benchmark_return", "excess", "max_drawdown", "pending")}
                           | {"id": a["id"], "name": a["name"], "kind": a["kind"], "start_day": a["start_day"], "note": a["note"]})
            return self._clean({"accounts": out, "rules": rules})
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:200]}"}

    def price_alerts(self, check: bool = True, lang: str | None = None) -> dict:
        from stockproof import alerts
        from stockproof.store import Store
        store = Store(self.app.data_dir)
        lang = self._lang(lang)
        new = alerts.watch(self.app, store, once=True, lang=lang, notify=False, log=lambda *a: None) if check else []
        return self._clean({"new": new, "recent": alerts.recent(store, 20), "watching": alerts.watch_list(self.app, store),
                            "market_open": alerts.market_open(),
                            "note": (alerts.NOT_ORDER if lang == "zh" else alerts.NOT_ORDER_EN)
                            + (" 持续盯盘：在终端运行 stockproof alerts --watch。" if lang == "zh" else
                               " For continuous watching run `stockproof alerts --watch`.")})

    TOOL_FOR = {"plan": "long_term_plan", "forecast": "long_term_forecast", "nt_research": "national_team_research", "day": "day_detail", "team": "research_team", "team_record": "team_track_record", "why": "why_did_it_move",
                "technical": "technical_analysis", "smart_money": "smart_money", "moneymap": "money_map",
                "etf": "national_team_etf", "margin": "market_leverage", "breakouts": "scan_market",
                "compare": "compare_with_last_report", "calendar": "earnings_calendar", "digest": "daily_digest",
                "portfolio": "portfolio_checkup", "screen": "screen_stocks", "scorecard": "evidence_scorecard",
                "lab": "lab_capabilities", "paper_order": "paper_trading", "paper": "paper_trading",
                "alerts": "price_alerts", "menu": "stockproof_menu"}

    def ask(self, text: str, lang: str | None = None) -> dict:
        from stockproof import ask
        client, _ = self._client()
        r = ask.route(self.app, text, client)
        a, tk = r["args"], r["ticker"]
        args = {"forecast": {"ticker": tk}, "day": {"ticker": tk, "date": a.get("date")}, "team": {"ticker": tk, "question": a.get("question")}, "why": {"ticker": tk}, "technical": {"ticker": tk, "open_chart": False},
                "smart_money": {"ticker": tk}, "moneymap": {"category": a.get("category", "national")},
                "compare": {"ticker": tk}, "scorecard": {"ticker": tk},
                "portfolio": {"holdings": a.get("holdings", [])}, "breakouts": {"direction": a.get("direction", "both")},
                "paper_order": {"action": a.get("side", "buy"), "ticker": tk, "value": a.get("value"), "shares": a.get("shares")},
                "paper": {"action": "list"}}.get(r["intent"], {})
        return self._clean({**r, "next_tool": self.TOOL_FOR.get(r["intent"]), "next_args": args,
                            "howto": "Call next_tool with next_args now (for paper_order, the account defaults to the latest "
                                     "manual paper account: call paper_trading(action='list') first if unsure). If the "
                                     "intent looks wrong for what the user said, pick the right tool yourself."})

    def long_term_plan(self, profile: str = "balanced", monthly_amount: float = 3000.0, holdings: dict | None = None,
                       lang: str | None = None) -> dict:
        from stockproof import plan
        lang = self._lang(lang)
        if profile not in plan.PROFILES:
            profile = "balanced"
        try:
            h = plan.history(self.app.data_dir)
            hold = {a: float(v) for a, v in (holdings or {}).items() if a in plan.ASSETS}
            m = plan.this_month(self.app.data_dir, profile, float(monthly_amount), hold, lang=lang)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {str(e)[:200]}"}
        for p in h["profiles"].values():
            p.pop("lump_path", None)
        return self._clean({"history": h, "summary": plan.summary_text(h, lang), "this_month": m,
                            "note": "Lead with the history (including buying at the 2007/2015 tops) and this month's buys. "
                                    "Mention the caveats. Paper account: paper_trading(action='plan'). Not advice."})

    def long_term_forecast(self, ticker: str | None = None, refresh: bool = False, lang: str | None = None) -> dict:
        from stockproof import forecast as fc
        res = fc.load(self.app.data_dir)
        if res is None or refresh:
            try:
                res = fc.run(self.app.data_dir, log=lambda *a: None)
            except Exception as e:
                return {"error": f"{type(e).__name__}: {str(e)[:200]}"}
        lang = self._lang(lang)
        out = {"made": res["made"], "universe": res.get("universe"), "track_record": fc.summary_text(res, lang),
               "horizons": {k: {"passes": v.get("passes"), "status": v.get("status"), "explore": v.get("explore"), "holdout": v.get("holdout"),
                                "weights": v.get("weights")} for k, v in res["horizons"].items()},
               "note": "Forecast = rank vs all stocks over 3/6/12 months and the past average excess of that tenth. Say "
                       "whether the model passed its walk-forward test (most don't); never present a failed model as a "
                       "prediction. Whole-market prices: `stockproof forecast --download`. Not advice."}
        if ticker:
            out["stock"] = fc.stock_view(res, self._tk(ticker), lang)
        if res.get("universe") != "all":
            out["warning"] = "Only today's CSI 300 members are covered (survivorship); suggest `stockproof forecast --download`."
        return self._clean(out)

    def national_team_research(self, refresh: bool = False, lang: str | None = None) -> dict:
        from stockproof import nt_research as nr
        r = nr.load(self.app.data_dir)
        if r is None or refresh:
            try:
                r = nr.run(self.app.data_dir, log=lambda *a: None)
            except Exception as e:
                return {"error": f"{type(e).__name__}: {str(e)[:200]}",
                        "howto": "Needs the holder history (stockproof moneymap --history 2016) and research prices."}
        lang = self._lang(lang)
        s = r["signals"]
        return self._clean({
            "conclusions": nr.summary_text(r, lang), "made": r["made"], "universe": r["universe"],
            "signal_tests": sorted(s["tests"], key=lambda t: -abs(t["t"] or 0)), "bar": s["bar"], "n_tests": s["n_tests"],
            "period": s["period"], "etf_timing": r["etf"],
            "forecast": {k: v for k, v in r["predict"].items() if k != "quarters"},
            "note": "diff = 60-day return after the disclosure minus other stocks disclosed the same month (t clustered by "
                    "month). Present the conclusions; the forecast is not a buy list (buying it ahead never paid). Not advice."})

    def day_detail(self, ticker: str, date: str, lang: str | None = None) -> dict:
        from stockproof import dayinfo, quotes
        from stockproof.store import Store
        tk = self._tk(ticker)
        if len(quotes.load_bars(self.app.data_dir, tk).dropna(subset=["close"])) < 30:
            try:
                quotes.update(self.app.data_dir, tk)
            except Exception as e:
                return {"error": f"prices unavailable ({type(e).__name__})"}
        return self._clean(dayinfo.day_info(Store(self.app.data_dir), self.app.data_dir, tk, date, self._lang(lang)))

    def share_card(self, kind: str, id: str, lang: str | None = None) -> dict:
        from urllib.parse import quote
        from stockproof import card
        from stockproof.store import Store
        lang = self._lang(lang)
        if kind not in ("team", "paper", "lab"):
            return {"error": "kind must be team (a research-team call_id), paper (an account id) or lab (an experiment id)"}
        ref = id
        if kind == "paper":
            from stockproof import paper
            a = paper.find_account(Store(self.app.data_dir), id)
            if not a:
                return {"error": "no such paper account"}
            ref = a["id"]
        svg = card.render(kind, ref, Store(self.app.data_dir), self.app.data_dir, lang)
        if svg is None:
            return {"error": "not found"}
        os.makedirs(os.path.join(self.app.data_dir, "cards"), exist_ok=True)
        path = os.path.join(self.app.data_dir, "cards", f"{kind}-{ref}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        out = {"file": path, "kind": kind, "id": ref}
        if os.environ.get("STOCKPROOF_CHART_IMAGES", "1") != "0":
            r = self.open_dashboard("home", port=8765, open_browser=False, _wait=20.0)
            if not r.get("error"):
                url = f"http://127.0.0.1:8765/card/{kind}/{quote(ref)}.svg?lang={lang}"
                out.update(url=url, card_markdown=f"![stockproof card]({url})",
                           howto="Put card_markdown on its own line (not in a code block). For a PNG, the dashboard's "
                                 "'生成分享卡片' button downloads one.")
        return out

    def team_track_record(self, lang: str | None = None) -> dict:
        from stockproof import team
        from stockproof.store import Store
        store = Store(self.app.data_dir)
        n = team.score_calls(store, self.app.data_dir, fetch=True)
        return self._clean({**team.track_record(store, self._lang(lang), limit=20), "newly_scored": n})

    def stockproof_menu(self, lang: str | None = None) -> dict:
        zh = self._lang(lang) == "zh"
        g = lambda name, tools, ask: {"group": name, "tools": tools, "try": ask}
        if zh:
            groups = [g("日常看盘", ["watchlist", "stock_brief", "technical_analysis", "scan_signals", "why_did_it_move", "compare_with_last_report",
                                  "company_announcements", "earnings_calendar", "daily_digest", "refresh_stock"],
                        ["我关注的股票今天怎么样？", "茅台最近有什么新闻和公告？", "宁德时代今天为什么跌？",
                         "腾讯这期财报和上期比变了什么？", "下周谁发财报？", "今天的简报"]),
                      g("AI 投研团队", ["research_team", "team_track_record"],
                        ["让 AI 投研团队分析一下科大讯飞", "AI 团队过去的判断准不准？"]),
                      g("一句话与分享卡片", ["ask", "share_card", "day_detail"],
                        ["茅台能买吗？", "科大讯飞 10 月 15 号那天发生了什么？", "把刚才投研团队的结论做成分享卡片"]),
                      g("模拟盘与提醒", ["paper_trading", "price_alerts"],
                        ["建一个模拟盘，用 10 万模拟买入贵州茅台", "我的模拟盘跑赢沪深300 了吗？", "我的股票有没有突破或到达计划价位？"]),
                      g("长期投资计划", ["long_term_plan"], ["每月 3000 元怎么长期投资？", "定投沪深300 划算吗？", "我的股债比例要不要再平衡？"]),
                      g("中长期预测", ["long_term_forecast"], ["贵州茅台未来半年会跑赢大盘吗？", "这个预测模型过去准不准？", "预测科大讯飞未来一年"]),
                      g("资金地图", ["national_team_research", "money_map", "national_team_etf", "market_leverage", "smart_money"],
                        ["国家队这个季度买了什么？", "最近有没有国家队托底的迹象？", "杠杆资金最近在加仓还是撤退？", "社保基金加仓了哪些行业？", "科大讯飞的十大股东里有没有国家队？"]),
                      g("选股与评分卡", ["screen_stocks", "scan_market", "evidence_scorecard"],
                        ["全市场业绩最强的 A 股有哪些？", "今天全市场哪些股票放量突破了？", "江波龙的证据评分卡"]),
                      g("量化实验室", ["lab_capabilities", "lab_backtest", "lab_confirm", "lab_similar", "lab_screen",
                                    "lab_policy_history", "lab_experiments", "research_findings"],
                        ["业绩大超预期后买入持有 20 天能赚钱吗？", "江波龙这种财报，历史上之后一般怎么走？",
                         "找 ROE>20%、营收增长>30%、市盈率<30 的 A 股", "新闻联播说加快发展半导体以后，电子行业表现如何？"]),
                      g("持仓体检", ["portfolio_checkup"], ["帮我体检持仓：600519 100 股、00700 300 股、AAPL 50 股"]),
                      g("网页看板", ["open_dashboard"], ["打开网页看板", "打开网页看板的持仓体检页"])]
        else:
            groups = [g("Daily", ["watchlist", "stock_brief", "technical_analysis", "scan_signals", "why_did_it_move", "compare_with_last_report",
                                  "company_announcements", "earnings_calendar", "daily_digest", "refresh_stock"],
                        ["How are my stocks today?", "What's new with NVDA?", "Why did 300750 drop today?",
                         "What changed in Tencent's latest report?", "Who reports next week?"]),
                      g("AI research team", ["research_team", "team_track_record"],
                        ["Have the research team analyse NVDA", "How accurate has the team been?"]),
                      g("One sentence & share cards", ["ask", "share_card", "day_detail"],
                        ["Should I buy NVDA?", "Make a share card of the team's view", "Make a card of my paper account"]),
                      g("Paper trading & alerts", ["paper_trading", "price_alerts"],
                        ["Open a paper account and buy 10k of NVDA", "Is my paper account beating the index?", "Any alerts on my stocks?"]),
                      g("Long-term plan", ["long_term_plan"], ["How should I invest 3000 a month?", "Is dollar-cost averaging CSI 300 worth it?", "Should I rebalance?"]),
                      g("Forecasts", ["long_term_forecast"], ["Will Moutai beat the market over 6 months?", "Is the forecast model any good?", "Forecast 002230 for a year"]),
                      g("Smart money", ["national_team_research", "money_map", "national_team_etf", "market_leverage", "smart_money"],
                        ["What did the national team buy this quarter?", "Who holds 002230 among the big funds?"]),
                      g("Screen & scorecards", ["screen_stocks", "scan_market", "evidence_scorecard"],
                        ["Strongest A-shares by fundamentals?", "Which A-shares broke out today?", "Evidence scorecard for 301308"]),
                      g("Quant lab", ["lab_capabilities", "lab_backtest", "lab_confirm", "lab_similar", "lab_screen",
                                      "lab_policy_history", "lab_experiments", "research_findings"],
                        ["Does buying after big earnings beats work after costs?", "A-shares with ROE > 20% and P/E < 30"]),
                      g("Portfolio check-up", ["portfolio_checkup"], ["Check my portfolio: 600519 100, AAPL 50"]),
                      g("Dashboard", ["open_dashboard"], ["Open the dashboard", "Open the dashboard's lab tab"])]
        return {"groups": groups, "text": self._menu_text(zh), "watchlist": self.app.settings.get("watchlist", [])[:20],
                "note": "Information and research, not investment advice."}

    def _menu_text(self, zh: bool) -> str:
        if zh:
            return """**stockproof（有据）能帮你做这些事**（美股、A 股、港股）

**1. 日常看盘**
- 我关注的股票今天怎么样：涨跌、新闻情绪、最新财报 —— 问"我关注的股票今天怎么样？"
- 一只股票的全貌：新闻（附链接）、财报解读、业绩惊喜、公告、下次财报日 —— "茅台最近有什么新闻和公告？"
- K 线与技术面：趋势、支撑位/压力位、突破和回踩信号，打开 K 线图 —— "宁德时代的支撑位和压力位在哪？" "我关注的股票今天有没有突破？"
- 为什么涨跌：只用当天前后的新闻、公告、财报解释，注明出处 —— "宁德时代今天为什么跌？"
- 财报对比：最新两期相比，业绩、展望、风险、分红有什么变化 —— "腾讯这期财报和上期比变了什么？"
- 公告监控、财报日历、每日简报 —— "下周谁发财报？" "今天的简报"

**2. 资金地图**（A 股）
- 国家队、社保、险资、外资、北向、公募这个季度新进/加仓/减仓了什么，按行业汇总 —— "国家队这个季度买了什么？"
- 一只股票的十大股东里有没有"聪明钱"，近期龙虎榜机构买卖 —— "科大讯飞的十大股东里有没有国家队？"

**3. 选股与评分卡**
- 全市场 A 股选股名单，附理由，任意股票都能查排名 —— "全市场业绩最强的 A 股有哪些？"
- 全市场突破扫描：今天放量突破阻力、跌破支撑的股票 —— "今天全市场哪些股票放量突破了？"
- 证据评分卡：每个维度打分、附出处，并标明哪些经过历史检验 —— "江波龙的证据评分卡"

**4. 量化实验室**（DeepSeek 自己做不到的：用十年真实数据现场回测）
- 回测任何交易想法，扣交易费用、考虑涨跌停，生成图文报告；多试几个版本会自动提高门槛，防止过拟合 —— "业绩大超预期后买入持有 20 天能赚钱吗？"
- 类似情况历史上怎么走 —— "江波龙这种财报，之后一般怎么走？"
- 按任意条件筛选全部 A 股 —— "找 ROE>20%、营收增长>30%、市盈率<30 的 A 股"
- 新闻联播政策信号十年回看 —— "说加快发展半导体以后，电子行业表现如何？"

**5. 持仓体检**
- 集中度、哪些股票其实同涨同跌、风险从哪来、历史大跌重演 —— "帮我体检持仓：600519 100 股、00700 300 股、AAPL 50 股"（也可以直接发券商截图）

---

### 📊 推荐：打开网页看板体验一下

> 网页看板是 stockproof 的网页界面：上面所有功能都能**点着用、看图表**，比打字更直观。
> 想打开就说 **「打开网页看板」**（以后随时都可以）；也可以说「打开网页看板的持仓体检页」直接跳到某一页。

---

输入 `/stockproof` 可以选现成的问题（体检持仓、回测想法、为什么涨跌、评分卡……）

仅供信息和研究参考，不构成投资建议。"""
        return """**What stockproof can do** (US, China A-shares, Hong Kong)

**1. Daily watching**: today's moves and news mood for your watchlist; one stock's news, earnings read, surprise,
filings and next report date; why a stock moved (cited); what changed between reports; announcements, earnings
calendar, daily digest. Try: "How are my stocks today?", "Why did 300750 drop today?"

**2. Smart money** (A-shares): what the national team, pensions, insurers, QFII, northbound money and funds
bought or sold this quarter, by industry; who the big holders of one stock are. Try: "What did the national team buy?"

**3. Screen & scorecards**: whole-market breakout scan; whole-market A-share shortlist with reasons; evidence scorecards with sources and which
dimensions passed history tests. Try: "Evidence scorecard for 301308"

**4. Quant lab** (what an LLM can't do alone): backtest any idea on ten years of point-in-time data with costs and
price limits, with a guard against overfitting; base rates after similar reports; custom screens; policy signals.
Try: "Does buying after big earnings beats work after costs?"

**5. Portfolio check-up**: concentration, holdings that move together, risk sources, crash replays.
Try: "Check my portfolio: 600519 100, AAPL 50" (a broker screenshot works too)

---

### 📊 Try the dashboard

> A clickable web page with charts for everything above. Say **"open the dashboard"** (any time).

---

Type `/stockproof` for ready-made requests.

Information and research, not investment advice."""

    # ---------------------------------------------------------------- dashboard
    TABS = ("home", "stocks", "digest", "team", "screen", "money", "paper", "lab", "portfolio", "research")

    def _dashboard_state(self, port: int) -> dict | None:
        import json as _json
        import urllib.request
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=1.5) as r:
                return _json.loads(r.read().decode("utf-8")) if r.status == 200 else None
        except Exception:
            return None

    def _dashboard_up(self, port: int) -> bool:
        return self._dashboard_state(port) is not None

    def _stop_stale_dashboard(self, port: int) -> bool:
        """A dashboard started earlier keeps running old code after stockproof is updated: stop it so a
        fresh one starts. Only stops a stockproof dashboard that reports its own pid and older code."""
        import signal
        import time
        from stockproof import code_stamp
        st = self._dashboard_state(port)
        if not st or not st.get("pid") or st.get("code", 0) >= code_stamp():
            return False
        try:
            os.kill(int(st["pid"]), signal.SIGTERM)
        except (OSError, ValueError):
            return False
        t0 = time.time()
        while self._dashboard_up(port) and time.time() - t0 < 5:
            time.sleep(0.2)
        return True

    TOOL_TAB = {"long_term_plan": "paper", "paper_trading": "paper", "price_alerts": "paper", "research_team": "team", "team_track_record": "team", "money_map": "money", "smart_money": "money", "portfolio_checkup": "portfolio", "screen_stocks": "screen", "evidence_scorecard": "screen",
                "daily_digest": "digest", "research_findings": "research", "watchlist": "stocks",
                "stock_brief": "stocks", "why_did_it_move": "stocks", "compare_with_last_report": "stocks",
                "company_announcements": "stocks", "refresh_stock": "stocks"}

    def _marker(self, name: str) -> str:
        return os.path.join(self.app.data_dir, name)

    def first_time(self, name: str) -> bool:
        """True the first time ever (per data folder) this is asked for `name`; leaves a marker file."""
        p = self._marker(name)
        if os.path.exists(p):
            return False
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(dt.datetime.now().isoformat(timespec="seconds"))
        except OSError:
            pass
        return True

    def auto_open(self, tool: str, background: bool = True) -> None:
        """The very first time stockproof runs under an agent: start the dashboard and open its home page, so a new
        user sees everything it can do. Never again after that (open_dashboard on request)."""
        if not self.auto_dashboard or self._auto_done or tool == "open_dashboard":
            return
        self._auto_done = True
        if os.path.exists(self._marker(".dashboard_shown")):
            return

        def go():
            try:                     # first time: show it even if a dashboard is already running
                r = self.open_dashboard("home", _wait=120.0)
                if r.get("url"):
                    self.first_time(".dashboard_shown")
            except Exception:
                pass
        if background:
            import threading
            threading.Thread(target=go, daemon=True).start()
        else:
            go()

    def open_dashboard(self, tab: str = "home", port: int = 8765, open_browser: bool = True,
                       _spawn=None, _wait: float = 60.0) -> dict:
        """Start the local dashboard in the background (if it isn't running) and open it in the browser."""
        import subprocess
        import time
        tab = tab if tab in self.TABS or tab.startswith("stock=") else "home"
        url = f"http://127.0.0.1:{port}/" + ("" if tab == "home" else "#" + tab)
        started = False
        self._stop_stale_dashboard(port)
        if not self._dashboard_up(port):
            log = open(os.path.join(self.app.data_dir, "dashboard_from_agent.log"), "a", encoding="utf-8")
            cmd = [sys.executable, "-u", "-m", "stockproof", "dashboard", "--data-dir", self.app.data_dir,
                   "--port", str(port), "--no-browser"]
            (_spawn or subprocess.Popen)(cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                         start_new_session=True)            # keeps running after the agent exits
            started = True
            t0 = time.time()
            while not self._dashboard_up(port):
                if time.time() - t0 > _wait:
                    return {"error": f"the dashboard did not start within {int(_wait)} s; see "
                                     f"{os.path.join(self.app.data_dir, 'dashboard_from_agent.log')}"}
                time.sleep(0.4)
        if open_browser:
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception:
                pass
        return {"url": url, "started": started, "tab": tab,
                "note": "The dashboard runs locally (127.0.0.1 only) and keeps running in the background; "
                        "everything done here (watchlist, lab runs, portfolio check-ups) shows up there too."}

    # ---------------------------------------------------------------- quant lab
    def _open(self, path: str | None, open_report: bool):
        if path and open_report:
            try:
                import webbrowser
                webbrowser.open("file://" + os.path.abspath(path))
            except Exception:
                pass

    def _lab(self, fn, *a, **k):
        from stockproof import lab
        try:
            return self._clean(fn(*a, **k))
        except lab.SpecError as e:
            return {"error": str(e), "hint": "fix the spec (see lab_capabilities) and try again"}

    def lab_capabilities(self) -> dict:
        from stockproof import lab
        return self._lab(lab.capabilities, self.app.data_dir)

    def lab_backtest(self, spec: dict, open_report: bool = True, lang: str | None = None) -> dict:
        from stockproof import lab
        out = self._lab(lab.explore, self.app.data_dir, spec, self._lang(lang), log=lambda *a: None)
        self._open(out.get("report"), open_report)
        return out

    def lab_confirm(self, experiment_id: str, open_report: bool = True, lang: str | None = None) -> dict:
        from stockproof import lab
        out = self._lab(lab.confirm, self.app.data_dir, experiment_id, self._lang(lang), log=lambda *a: None)
        self._open(out.get("report"), open_report)
        return out

    def lab_similar(self, ticker: str, sue: float | None = None, lang: str | None = None) -> dict:
        from stockproof import lab
        return self._lab(lab.similar, self.app.data_dir, ticker, sue=sue, lang=self._lang(lang))

    def lab_screen(self, filters: list, sort_by: str = "rev_yoy", descending: bool = True, top: int = 30) -> dict:
        from stockproof import lab
        return self._lab(lab.custom_screen, self.app.data_dir, filters, sort_by, descending, top, log=lambda *a: None)

    def lab_policy_history(self, industry: str | None = None, keyword: str | None = None, stance: str | None = None,
                           kind: str | None = "new_measure", min_strength: int = 1, since: str | None = None) -> dict:
        from stockproof import lab
        return self._lab(lab.policy_history, self.app.data_dir, industry, keyword, stance, kind, min_strength, since)

    def lab_experiments(self, new_question: bool = False) -> dict:
        from stockproof import lab
        if new_question:
            lab.reset(self.app.data_dir)
        return self._clean({"experiments": lab.list_experiments(self.app.data_dir),
                            "tries_since_reset": lab.n_tries(self.app.data_dir, lab._since_reset(self.app.data_dir))})

    def portfolio_checkup(self, holdings: list, fx: dict | None = None, open_report: bool = True,
                          lang: str | None = None) -> dict:
        from stockproof import portfolio
        client, _ = self._client()
        try:
            out = portfolio.checkup(self.app.data_dir, holdings, fx, self._lang(lang), client, log=lambda *a: None)
        except portfolio.HoldingsError as e:
            return {"error": str(e)}
        self._open(out.get("report"), open_report)
        out.pop("corr", None)
        out.pop("curve", None)
        return self._clean(out)

    def refresh_stock(self, ticker: str, lang: str | None = None) -> dict:
        """Follow a stock (adds it to the watchlist) and fetch its news, earnings, prices, announcements."""
        lang, tk = self._lang(lang), self._tk(ticker)
        wl = list(self.app.settings["watchlist"])
        if tk not in wl:
            self.app.set_watchlist(wl + [tk])
            if tk not in self.app.settings["watchlist"]:
                return {"error": f"'{ticker}' is not a recognised ticker"}
        errors = []
        for kind in ("news", "earnings"):
            self.app.job = {"running": True, "kind": kind, "done": 0, "total": 1, "current": "",
                            "log": [], "error": None, "finished_at": None}
            self.app._run(kind, [tk], lang)
            if self.app.job.get("error"):
                errors.append(f"{kind}: {self.app.job['error']}")
        brief = self.stock_brief(tk, lang)
        brief["refresh_errors"] = errors
        return brief

    def add_to_watchlist(self, tickers: list[str]) -> dict:
        wl = list(self.app.settings["watchlist"])
        self.app.set_watchlist(wl + [t for t in tickers if self._tk(t) not in wl])
        return {"watchlist": self.app.settings["watchlist"],
                "note": "Call refresh_stock for each new stock to fetch its data now, or wait for the daily update."}

    def remove_from_watchlist(self, tickers: list[str]) -> dict:
        drop = {self._tk(t) for t in tickers}
        self.app.set_watchlist([t for t in self.app.settings["watchlist"] if t not in drop])
        return {"watchlist": self.app.settings["watchlist"]}

    def _client(self):
        from stockproof.llm import LLMClient, LLMError
        try:
            c = LLMClient.from_provider(self.app.provider, self.app.model_name, self.app.base_url)
            return c, f"{self.app.provider}:{c.model}"
        except LLMError:
            return None, None


# Ready-made requests: MCP prompts (clients that support them show them as slash commands) and, for DeepSeek
# Harness, skills (DSH lists skills in its / menu). {x} is what the user types after the command.
PROMPTS = [
    ("menu", "stockproof：能做什么", "List everything stockproof can do, with example questions", None,
     "用 stockproof_menu 列出 stockproof 能做的所有事情，把返回的 text 完整展示给我（每组功能和可以直接问的例子、/ 命令、网页看板）。"),
    ("dashboard", "打开网页看板", "Open the local dashboard (web page) in the browser", None,
     "用 open_dashboard 打开 stockproof 网页看板（如果我说了想看哪一页，就打开那一页：首页、股票、选股、实验室、持仓体检、研究）。"),
    ("watch", "看盘：我的股票今天怎么样", "Today's moves, news mood and important announcements for the watchlist", None,
     "用 watchlist 看我关注的股票今天怎么样：涨跌、新闻情绪、最新财报，以及有没有重要公告或异动；附原文链接。"),
    ("why_moved", "看盘：为什么涨跌", "Explain a stock's recent move from the news, filings and reports around it", "ticker",
     "{x} 最近为什么涨跌？用 why_did_it_move，只根据当天前后的新闻、公告和财报解释，注明出处和把握程度。"),
    ("compare_reports", "看盘：财报和上期比变了什么", "What changed between the latest two reports", "ticker",
     "用 compare_with_last_report 看 {x} 最新一期财报和上一期相比，业绩、展望、风险、业务、分红有什么变化。"),
    ("team", "AI 投研团队：分析一只股票", "Five AI analysts, a bull/bear debate and a PM's view, logged and scored later", "ticker",
     "用 research_team 让 AI 投研团队分析 {x}：先说结论（观点、置信度、观察期）、观察计划和风险，说明置信度为什么是这个水平，"
     "引用证据编号；说明这次判断已记入前瞻日志、到期会打分。不是买卖建议。"),
    ("plan", "长期投资计划：每月怎么投", "Long-term plan: what to buy each month", "amount",
     "用 long_term_plan 给我一个长期投资计划（每月投入 {x}）：先给出稳健/平衡/进取三种配置 2005 年以来的历史成绩（包括在 2007、2015 年最高点买入的结果、最差一年、最大回撤），"
     "再给出这个月每个 ETF 该买多少、A 股现在便宜还是贵。说明简化和风险，不是投资建议。"),
    ("forecast", "中长期预测：未来 3/6/12 个月", "3/6/12-month forecast with the model's track record", "ticker",
     "用 long_term_forecast 预测 {x} 未来 3、6、12 个月相对大盘的表现：说出排名百分位、历史同档的平均超额收益，"
     "以及这个模型有没有通过检验（扣成本后的真实成绩）；没通过就明说只能参考。不预测明天涨跌，不是投资建议。"),
    ("ntresearch", "跟着国家队做能赚钱吗", "Can acting on the national team make money?", None,
     "用 national_team_research 回答：跟着（或反着）国家队、社保、险资、北向的披露去买或回避，历史上能不能赚钱；ETF 托底之后大盘怎么走；"
     "下季度国家队最可能新进哪些股票、这种预测准不准、提前买赚不赚。先说结论，再给关键数字（和同月其他披露比的差、t 值、门槛），"
     "说明预测名单不是买入名单，这是历史研究不是投资建议。"),
    ("ask", "一句话问", "Ask anything in one sentence; stockproof picks the feature", "question",
     "{x}\n（用 stockproof 回答：先用 ask 找到合适的工具和参数，再调用它；结论要带出处，不是投资建议。）"),
    ("card", "生成分享卡片", "Make a shareable card of a team call, a paper account or a lab result", "what",
     "用 share_card 把{x}做成分享卡片（投研团队的判断用 call_id，模拟盘用账户名，实验室用实验编号；不知道编号就先查最近的记录），把 card_markdown 单独一行展示出来。"),
    ("paper", "模拟盘：我的模拟账户", "Paper accounts vs the index, with holdings and orders", None,
     "用 paper_trading（action=list，再对每个账户 action=show）看我的模拟盘：总资产、收益、和沪深300/标普500 比的超额、最大回撤、持仓和最近的订单；"
     "如果有策略账户，用 action=gap 说明回测和模拟盘成交之间的差距。说明成交规则是悲观的，这是模拟盘不是实盘。"),
    ("alerts", "提醒：突破、计划价位、成交", "Alerts: zone breaks, team plan levels, paper fills", None,
     "用 price_alerts 检查我的股票：有没有突破/跌破支撑阻力区间、到达 AI 投研团队计划里的价位、模拟单成交或取消。说明提醒不是交易指令；"
     "想持续盯盘就在终端运行 stockproof alerts --watch。"),
    ("team_record", "AI 投研团队：过去准不准", "The research team's scored track record", None,
     "用 team_track_record 看 AI 投研团队过去的判断和到期后的打分：总命中率、按置信度分的命中率、是否有衰减。样本少时要说明。"),
    ("moneymap", "资金地图：国家队/社保/北向在买什么", "What the national team, pensions, northbound money... did this quarter", "conditions",
     "用 money_map 看{x}这个季度在买什么、卖什么（没说就看国家队），按行业汇总，包括推断出的跌出前十；国家队还要用 national_team_etf 看 ETF 托底迹象。"
     "一定要说出历史检验结果：跟着公开披露买，历史上有没有跑赢大盘。"),
    ("breakouts", "全市场突破扫描", "Today's support/resistance breakouts across all A-shares", None,
     "用 scan_market 扫描今天全市场放量突破阻力、跌破支撑的股票，列出区间、触及次数和量比；说明这是图形事实，不是买卖信号。"),
    ("scorecard", "选股：证据评分卡", "Evidence scorecard for a stock, with sources and what was validated", "ticker",
     "用 evidence_scorecard 看 {x} 的证据评分卡，说明哪些维度经过历史检验、主要利好和风险，并附出处。"),
    ("screen", "选股：全市场名单或自定义条件", "Whole-market A-share shortlist, or a custom screen", "conditions",
     "选股：{x}。没有条件就用 screen_stocks 给我看今天的全市场名单和理由；有条件就用 lab_screen 按条件筛选全部 A 股。"),
    ("backtest", "实验室：回测一个想法", "Backtest a trading idea on point-in-time history, with the overfitting guard", "idea",
     "用量化实验室检验这个想法：{x}。先调用 lab_capabilities，再把想法如实翻译成策略并用 lab_backtest 回测；"
     "报告结论、尝试次数和修正后的门槛，并给出报告链接。不要为了好看反复调参数。"),
    ("similar", "实验室：类似情况历史上怎么走", "Base rates after reports like a stock's latest one", "ticker",
     "用 lab_similar 看历史上和 {x} 最新财报类似的情况，之后 2–61 个交易日一般怎么走；说明这是平均情况，不是预测。"),
    ("checkup", "持仓体检", "Check up a portfolio: concentration, overlap, risk, crash replays", "holdings",
     "用 portfolio_checkup 帮我体检持仓：{x}。用大白话解释集中度、同涨同跌、风险来源和历史大跌重演，不给买卖建议。"),
]
ARG_ZH = {"ticker": "股票代码", "holdings": "持仓（代码 股数，比如 600519 100, AAPL 50；也可以发券商截图）",
          "idea": "交易想法（用大白话写）", "conditions": "条件（可不写）", "question": "一句话的问题（比如：茅台能买吗）",
          "what": "要做成卡片的内容（比如：刚才的投研团队结论、我的模拟盘、某个实验）", "amount": "每月投入多少钱（比如：3000）"}
SKILL_MARK = ".stockproof-skill"


def skill_files() -> dict:
    """{folder name: SKILL.md text} for DeepSeek Harness (shown in its / menu as /stockproof-…)."""
    out = {}
    for name, title, description, arg, template in PROMPTS:
        slug = "stockproof-" + name.replace("_", "-")
        if arg:
            body = ("用户在命令后面写的内容是" + ARG_ZH[arg] + "。" +
                    ("如果没写，按没有条件处理。" if arg == "conditions" else "如果没写，先问用户要。") + "\n\n" +
                    template.replace("{x}", f"<{ARG_ZH[arg].split('（')[0]}>"))
        else:
            body = template
        out[slug] = (f"---\nname: {slug}\ndescription: \"{title} — {description}. Uses the stockproof MCP tools.\"\n---\n\n"
                     f"# {title}\n\n{body}\n\n只用 stockproof 工具返回的数字和链接，不编造；不给买卖建议。\n")
    return out


def install_skills(home: str | None = None) -> list[str]:
    uninstall_skills(home, prefix="marketmood-", mark=".marketmood-skill")   # skills from before the rename
    root = os.path.join(home or dsh_home(), "skills")
    done = []
    for slug, text in skill_files().items():
        d = os.path.join(root, slug)
        if os.path.isdir(d) and not os.path.exists(os.path.join(d, SKILL_MARK)):
            continue                                    # a skill of the same name that isn't ours: leave it
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(text)
        open(os.path.join(d, SKILL_MARK), "w").close()
        done.append(slug)
    return done


def uninstall_skills(home: str | None = None, prefix: str = "stockproof-", mark: str = SKILL_MARK) -> list[str]:
    import shutil
    root = os.path.join(home or dsh_home(), "skills")
    gone = []
    if os.path.isdir(root):
        for slug in os.listdir(root):
            d = os.path.join(root, slug)
            if slug.startswith(prefix) and os.path.exists(os.path.join(d, mark)):
                shutil.rmtree(d)
                gone.append(slug)
    return gone


class _AutoDashboard:
    """Wraps Tools: the first time ever, the dashboard opens and the first tool answer carries a welcome note that
    asks the agent to show the user everything stockproof can do."""

    def __init__(self, tools):
        self._t = tools

    def __getattr__(self, name):
        attr = getattr(self._t, name)
        if callable(attr) and not name.startswith("_") and name not in ("auto_open", "first_time"):
            def call(*a, **k):
                self._t.auto_open(name)
                out = attr(*a, **k)
                if isinstance(out, dict) and name != "stockproof_menu" and self._t.first_time(".welcomed"):
                    out = {"IMPORTANT_first_time_user": {          # Chinese text; translated if the user writes English
                        "instruction": WELCOME + " If the user writes in another language, translate it.",
                        "show_to_user_after_your_answer": self._t._menu_text(True)}, **out}
                elif name == "stockproof_menu":
                    self._t.first_time(".welcomed")
                return out
            return call
        return attr


WELCOME = ("This is the user's first time using stockproof. You MUST, after answering their question, show the "
           "text in 'show_to_user_after_your_answer' in full (it lists everything stockproof can do), which also "
           "tells them "
           "stockproof also has a dashboard, a local web page where every feature can be clicked and seen in charts, "
           "recommends opening it once to try it, and says they can open it any time by saying “打开网页看板” (in Chinese always call it 网页看板, never 仪表盘). Keep the "
           "menu text's 📊 dashboard section as it is (heading, quote block and bold), so it stands out. Offer to "
           "open it now; call open_dashboard(tab=\"home\") only if they agree (the home page shows every feature).")


def build_server(tools: Tools):
    from stockproof import __version__
    if getattr(tools, "auto_dashboard", False) or getattr(tools, "welcome", False):
        tools = _AutoDashboard(tools)
    Server = _server_class()
    try:
        srv = Server(name="stockproof", instructions=INSTRUCTIONS, version=__version__)
    except TypeError:                                   # SDK 1.x has no version argument
        srv = Server(name="stockproof", instructions=INSTRUCTIONS)

    @srv.tool()
    def stockproof_menu(lang: str | None = None) -> dict:
        """Everything stockproof can do, in four groups (daily stock watching, screen & scorecards, quant lab,
        portfolio check-up), with example questions. Call when the user asks what you can do."""
        return tools.stockproof_menu(lang)

    @srv.tool()
    def watchlist(lang: str | None = None) -> dict:
        """The followed stocks with today's return, news mood, latest earnings tone/guidance/SUE.
        lang: 'en' or 'zh' (default: the dashboard's language)."""
        return tools.watchlist(lang)

    @srv.tool()
    def stock_brief(ticker: str, lang: str | None = None) -> dict:
        """Everything known about one followed stock: price and returns, relevant headlines with links and
        AI scores, latest earnings report reading (with link), earnings surprise, what happened after similar
        reports historically, next report date, important announcements (China/HK). No LLM cost.
        ticker examples: AAPL, 600519, 300750, 00700."""
        return tools.stock_brief(ticker, lang)

    @srv.tool()
    def why_did_it_move(ticker: str, date: str | None = None, lang: str | None = None) -> dict:
        """Explain a price move (default: the latest unusual move in the last 10 days) using only the news,
        announcements and reports published around that day, with numbered citations and a confidence level.
        Says so when nothing found explains it. One LLM call (cached). date: YYYY-MM-DD."""
        return tools.why_did_it_move(ticker, date, lang)

    @srv.tool()
    def technical_analysis(ticker: str, open_chart: bool = False, lang: str | None = None) -> dict:
        """Technical picture of a stock from daily bars: trend (moving-average order, RSI, MACD), support and
        resistance zones (price levels where it turned several times, with touch counts and distance), 52-week
        range, and chart signals in the last 5 days (breakout on volume, breakdown, pullback, golden/death cross,
        MACD, RSI, Bollinger), each with its exact rule. Includes `chart_markdown`, a candlestick chart image with
        the zones marked: put it in your answer as is (not in a code block). open_chart=True opens the candlestick chart in the
        dashboard (followed stocks). Describes price action; not a forecast. Works for any A/HK/US stock."""
        return tools.technical_analysis(ticker, open_chart, lang)

    @srv.tool()
    def scan_signals(days: int = 3, lang: str | None = None) -> dict:
        """Scan every stock in the watchlist for chart signals in the last `days` trading days (breakouts,
        breakdowns, pullbacks to support, crosses, RSI/Bollinger extremes, volume spikes), newest first."""
        return tools.scan_signals(days, lang)

    @srv.tool()
    def scan_market(direction: str = "both", refresh: bool = True, lang: str | None = None) -> dict:
        """Whole-market A-share chart scan: which liquid stocks broke out above resistance (with volume) or broke
        down through support TODAY. direction: up / down / both. Takes ~30-60 s (downloads bars for the ~60 most
        traded movers); refresh=False returns the last saved scan. Each hit has the zone, touches, volume ratio and
        the rule. Chart facts, not orders, and untested as a strategy: say so, and offer lab_backtest."""
        return tools.scan_market(direction, refresh, lang)

    @srv.tool()
    def money_map(category: str = "national", quarter: str | None = None, lang: str | None = None) -> dict:
        """Smart-money map of A-shares for one quarter (国家队/社保/险资/外资 资金地图): what one kind of investor did
        in every company's top-10 tradable holders: new / added / reduced positions, by industry and by stock, with
        estimated value changes. category: national (汇金/证金/梧桐树/国新/诚通), social (社保/养老金), northbound
        (香港中央结算), insurance, qfii, fund. quarter: YYYYMMDD (default: the latest fully reported one). The first
        call for a quarter downloads ~56k rows (about 2 minutes), then it is cached. Quarterly and up to 4 months
        late: say so."""
        return tools.money_map(category, quarter, lang)

    @srv.tool()
    def national_team_etf(days: int = 60, lang: str | None = None) -> dict:
        """The national team's ETF channel (汇金买 ETF 托底): daily net creations in the big Shanghai-listed broad-index
        ETFs (CSI 300, SSE 50, CSI 500/1000, STAR 50), valued at NAV, with days flagged where an unusually large net
        creation came on a day the CSI 300 fell. Indirect evidence (anyone can create units): say "consistent with",
        never "confirmed". The first call downloads ~4 months of daily share counts (a few minutes), then cached."""
        return tools.national_team_etf(days, lang)

    @srv.tool()
    def market_leverage(lang: str | None = None) -> dict:
        """Leveraged money in A-shares (融资余额, 杠杆资金): the financing balance on Shanghai and Shenzhen over the last
        20 trading days, its change, and the stocks where it rose or fell most. First call downloads ~20 days (a few
        minutes), then cached. Use for "杠杆资金在加仓还是撤退", "融资余额". Facts, not a forecast."""
        return tools.market_leverage(lang)

    @srv.tool()
    def smart_money(ticker: str, lang: str | None = None) -> dict:
        """Who the smart money is in one A-share: national team / social security / insurers / QFII / northbound /
        funds among its top-10 tradable holders (with this quarter's changes and inferred exits), recent 龙虎榜 days
        with institutions' net buy, the 20-day margin-financing balance change (融资余额, leveraged money) and the
        20-day 'main force' flow ESTIMATE. Facts about holders, not a forecast."""
        return tools.smart_money(ticker, lang)

    @srv.tool()
    def compare_with_last_report(ticker: str, lang: str | None = None) -> dict:
        """What changed between the company's latest two earnings documents: results, outlook, risks,
        business, capital returns (each marked better/worse/neutral), risks named for the first time, tone
        shift, links to both documents. One LLM call (cached per pair of documents)."""
        return tools.compare_with_last_report(ticker, lang)

    @srv.tool()
    def company_announcements(ticker: str, days: int = 30, important_only: bool = True,
                              lang: str | None = None) -> dict:
        """China A-share / Hong Kong company announcements, classified (insider selling, buyback, regulator's
        letter, lawsuit, restructuring, earnings preview...) with importance, AI summary and impact when
        available, and links to the originals. No LLM cost."""
        return tools.company_announcements(ticker, days, important_only, lang)

    @srv.tool()
    def earnings_calendar(days: int = 14) -> dict:
        """Followed companies reporting earnings in the next `days` days: date, before/after market (US),
        analysts' consensus EPS (US), official appointment dates (A-shares)."""
        return tools.earnings_calendar(days)

    @srv.tool()
    def daily_digest(make_new: bool = False, lang: str | None = None) -> dict:
        """Today's digest for the watchlist: unusual moves with explanations, important announcements, new
        earnings reports, upcoming reports, strongest news moods. make_new=true builds a fresh one (LLM calls)."""
        return tools.daily_digest(make_new, lang)

    @srv.tool()
    def research_findings(market: str = "us") -> dict:
        """Results of stockproof's event studies on years of data (market: 'us' or 'cn'): how prices react to
        earnings surprises and to the AI's reading of reports, whether the drift continues, and a backtest with
        trading costs. Use for questions like 'does a good earnings surprise predict returns?'"""
        return tools.research_findings(market)

    @srv.tool()
    def screen_stocks(top: int = 20, ticker: str | None = None, lang: str | None = None) -> dict:
        """Whole-market China A-share shortlist from the latest `stockproof screen`: rank, score and plain-language
        reasons (earnings surprise, growth, ROE, trend), plus the rule's historical test. With `ticker`, where that
        one stock ranks (or why it isn't screened). A shortlist to research, not advice."""
        return tools.screen_stocks(top, ticker, lang)

    @srv.tool()
    def research_team(ticker: str, question: str | None = None, lang: str | None = None) -> dict:
        """AI research team on one stock (AI 投研团队): five analysts (fundamentals, technicals, news, capital flow,
        policy) each argue from their own numbered evidence, a bull and a bear researcher debate, and a portfolio
        manager with the risk check gives a stance (bullish / bearish / neutral / no_view), confidence, horizon, a
        watch plan with levels from the computed support/resistance zones, risks and what would change the view.
        Confidence is capped at low unless a history-tested area supports the stance. Every call is saved in an
        append-only forward log and scored against the market after its horizon. ~8 LLM calls, 30-60 s; one call
        per stock per day for the same question. question: what the user wants the team to focus on, in their words
        (e.g. "扣非亏损会不会持续"); the team answers it first. Use for "分析一下X", "X 能买吗", "给我一个观点". Not advice."""
        return tools.research_team(ticker, question, lang)

    @srv.tool()
    def paper_trading(action: str = "list", account: str | None = None, ticker: str | None = None,
                      shares: int | None = None, value: float | None = None, name: str | None = None,
                      cash: float | None = None, experiment_id: str | None = None, call_id: str | None = None,
                      lang: str | None = None) -> dict:
        """Paper trading (模拟盘), never real money. action: list (accounts vs the index), show (one account: holdings,
        orders, daily value vs CSI 300 / S&P 500), new (name, cash), buy / sell (account, ticker, shares or value),
        run (fill pending orders and queue strategy orders), forecast (hold the 6-month forecast's top 50, rebalanced
        quarterly: tests the forecaster live), strategy (experiment_id from the lab: follow that
        strategy on paper from today), gap (a strategy account: backtest rule vs actual paper fills, trade by trade),
        from_team (call_id of a research-team call -> one paper order). Orders fill at the next trading day's open
        with pessimistic rules: no buy at limit-up / sell at limit-down (waits up to 5 days), max 5% of the day's
        volume, slippage + impact, commission (min 5 yuan), stamp duty, T+1, lots of 100. Append-only record.
        Only place orders the user asked for."""
        return tools.paper_trading(action, account, ticker, shares, value, name, cash, experiment_id, call_id, lang)

    @srv.tool()
    def price_alerts(check: bool = True, lang: str | None = None) -> dict:
        """Alerts (提醒/盯盘): checks the watchlist, paper holdings and stocks with recent research-team calls against
        live prices (Sina, during the session) or the last close: support/resistance zone breaks, research-team plan
        levels reached, paper fills and cancellations. Each alert is recorded once. Alerts are not orders."""
        return tools.price_alerts(check, lang)

    @srv.tool()
    def ask(text: str, lang: str | None = None) -> dict:
        """One-sentence entry: map what the user said (e.g. "茅台能买吗", "国家队最近买了什么", "模拟买入10万宁德时代")
        to the right stockproof tool and its arguments (rules first, LLM only if no rule fits). Returns next_tool and
        next_args; call that tool next. Use when unsure which tool fits."""
        return tools.ask(text, lang)

    @srv.tool()
    def long_term_plan(profile: str = "balanced", monthly_amount: float = 3000.0, holdings: dict | None = None,
                       lang: str | None = None) -> dict:
        """Long-term investment plan (长期投资/定投/资产配置): A-shares (CSI 300/500 ETFs), government bonds, gold and
        S&P 500, profiles conservative / balanced / growth. Returns each mix's history since 2005 from several start
        dates (incl. the 2007 and 2015 tops), worst year, max drawdown, monthly-buying returns with and without the
        valuation tilt, and this month's buys (A-share part scaled by how cheap A-shares are; rebalance warning
        from `holdings` = {asset: amount}, assets hs300/zz500/bond/gold/spx). No forecasting; not advice."""
        return tools.long_term_plan(profile, monthly_amount, holdings, lang)

    @srv.tool()
    def long_term_forecast(ticker: str | None = None, refresh: bool = False, lang: str | None = None) -> dict:
        """Medium/long-horizon forecast for A-shares: each stock's rank vs all stocks over the next 3, 6 and 12 months,
        from valuation, profitability, growth, trend and volatility, refit monthly on past data only (walk-forward),
        with the model's own out-of-sample record after costs and whether it passed. Use for "未来几个月 / 半年 /
        一年会涨吗", "长期走势", "预测". Not daily direction; not advice."""
        return tools.long_term_forecast(ticker, refresh, lang)

    @srv.tool()
    def national_team_research(refresh: bool = False, lang: str | None = None) -> dict:
        """"跟着国家队做能不能赚钱": tests 24 signals (national team / pensions / northbound / insurers / QFII / funds x
        new / add / reduce / exit) against other stocks disclosed the same month, with a multiple-testing bar and a
        locked holdout; the CSI 300 after ETF rescue and big-redemption days; and a walk-forward forecast of next
        quarter's national-team new entries (accuracy and whether buying ahead paid). Use for questions about
        following, copying, front-running or predicting the national team or other big holders."""
        return tools.national_team_research(refresh, lang)

    @srv.tool()
    def day_detail(ticker: str, date: str, lang: str | None = None) -> dict:
        """What happened to one stock on one day (YYYY-MM-DD; a non-trading day uses the one before): the bar,
        the move vs the market, volume vs normal, zones crossed or touched, MA20/MA60, signals that fired, news /
        announcements / reports around it, research-team calls and paper fills that day, and (labelled hindsight)
        returns 5 / 20 / 60 trading days later. Use for "那天怎么了", "3月5号发生了什么". For the cause, follow
        with why_did_it_move(ticker, date)."""
        return tools.day_detail(ticker, date, lang)

    @srv.tool()
    def share_card(kind: str, id: str, lang: str | None = None) -> dict:
        """Shareable result card (1200x675 image): kind=team with a research-team call_id, kind=paper with a paper
        account id or name, kind=lab with a lab experiment id. Every card carries its checkable id, the rules
        (fills / forward-log scoring / tries counted) and 'not advice'. Returns card_markdown (show it on its own
        line) and the saved SVG file."""
        return tools.share_card(kind, id, lang)

    @srv.tool()
    def team_track_record(lang: str | None = None) -> dict:
        """The research team's public track record: every past call from the append-only forward log, scored against
        the market once its horizon passed (hit rate overall and by confidence, decay flag). Use for "AI 团队准不准"."""
        return tools.team_track_record(lang)

    @srv.tool()
    def evidence_scorecard(ticker: str, refresh: bool = False, lang: str | None = None) -> dict:
        """Evidence scorecard (0-100 per dimension: fundamentals, trend, latest report, earnings quality, news,
        announcements) with cited sources, and for each dimension whether stockproof's history tests found it useful.
        refresh=True fetches fresh news/report/announcements first (~1 minute, a little LLM credit). Not advice."""
        return tools.evidence_scorecard(ticker, refresh, lang)

    @srv.tool()
    def lab_capabilities() -> dict:
        """The quant lab: what trading ideas can be backtested on this computer's point-in-time data (strategy
        types, filter fields, date ranges, the locked holdout period, how many variants were tried). Call first."""
        return tools.lab_capabilities()

    @srv.tool()
    def lab_backtest(spec: dict, open_report: bool = True, lang: str | None = None) -> dict:
        """Backtest a trading idea on history BEFORE the locked holdout, with costs and A-share price limits, and open
        an illustrated report. spec example: {"type": "earnings", "market": "cn", "filters": [{"field": "sue",
        "op": ">=", "value": 2}], "hold_days": 20, "entry_lag": 1}. Types: earnings, forecast (业绩预告), policy
        (新闻联播 signals, trades industry indices), factor (top-N rebalance; give "factors" and "top").
        Returns excess return, t, trades, years, a verdict corrected for the number of variants tried, a 2x cost
        stress test (`stress`) and a walk-forward check over the variants tried (`walk_forward`)."""
        return tools.lab_backtest(spec, open_report, lang)

    @srv.tool()
    def lab_confirm(experiment_id: str, open_report: bool = True, lang: str | None = None) -> dict:
        """Run an explored strategy ONCE on the locked recent years it has never seen (out-of-sample test).
        Can't be repeated for the same strategy. Use only after lab_backtest passes and the user agrees."""
        return tools.lab_confirm(experiment_id, open_report, lang)

    @srv.tool()
    def lab_similar(ticker: str, sue: float | None = None, lang: str | None = None) -> dict:
        """Base rates: past reports that looked like this stock's latest one (or a hypothetical SUE) and what the
        stock did over the next 2-61 trading days vs the market: mean, spread, beat rate, examples."""
        return tools.lab_similar(ticker, sue, lang)

    @srv.tool()
    def lab_screen(filters: list, sort_by: str = "rev_yoy", descending: bool = True, top: int = 30) -> dict:
        """Custom screen over ALL A-shares with any conditions, e.g. [{"field": "roe", "op": ">", "value": 20},
        {"field": "rev_yoy", "op": ">", "value": 30}, {"field": "pe", "op": "<", "value": 30},
        {"field": "cap", "op": ">=", "value": 100}]. Fields: sue, rev_yoy, np_yoy, roe, gm, pe, pb, cap (亿元),
        mom60, ytd, industry, name. Ops: >=, <=, >, <, ==, !=, in, not_in, contains, between."""
        return tools.lab_screen(filters, sort_by, descending, top)

    @srv.tool()
    def lab_policy_history(industry: str | None = None, keyword: str | None = None, stance: str | None = None,
                           kind: str | None = "new_measure", min_strength: int = 1, since: str | None = None) -> dict:
        """10 years of 新闻联播 industry-policy signals (Shenwan industry, stance, wording strength 1-4, quote) and
        how the industry did afterwards vs the other industries. Filter by industry and/or a keyword."""
        return tools.lab_policy_history(industry, keyword, stance, kind, min_strength, since)

    @srv.tool()
    def lab_experiments(new_question: bool = False) -> dict:
        """The lab notebook: experiments run so far with their verdicts. new_question=True starts a new research
        question, so earlier variants no longer raise the significance bar (they stay in the notebook)."""
        return tools.lab_experiments(new_question)

    @srv.tool()
    def portfolio_checkup(holdings: list, fx: dict | None = None, open_report: bool = True,
                          lang: str | None = None) -> dict:
        """Check up a portfolio on real price history: concentration (stocks, industries), holdings that move
        together, volatility and beta, where the risk comes from, and replays of past crashes (2015, 2018, 2020,
        2021-22, early 2024) on today's weights; opens an illustrated report. holdings: [{"ticker": "600519",
        "shares": 100, "cost": 1500}, {"ticker": "AAPL", "shares": 20}] (or "value" / "weight" instead of shares).
        fx: optional rates to CNY, e.g. {"USD": 7.1, "HKD": 0.91}. A-shares, Hong Kong and US stocks."""
        return tools.portfolio_checkup(holdings, fx, open_report, lang)

    @srv.tool()
    def open_dashboard(tab: str = "home") -> dict:
        """Open stockproof's local dashboard (a web page with clickable charts, tables and forms) in the user's
        browser, starting it in the background if needed. tab: home, stocks, digest, team (AI research team), screen, money (smart-money map), paper (paper trading and alerts), lab,
        portfolio or research. Use when the user asks for the dashboard / 网页看板 / 看板 / 网页版 / 仪表盘, or wants to browse results visually
        (e.g. tab="portfolio" after a check-up, tab="lab" after backtests)."""
        return tools.open_dashboard(tab)

    @srv.tool()
    def refresh_stock(ticker: str, lang: str | None = None) -> dict:
        """Start following a stock (adds it to the watchlist) and fetch its news, earnings, prices and
        announcements now; returns the stock brief. Takes about 30-60 seconds and a little LLM credit."""
        return tools.refresh_stock(ticker, lang)

    @srv.tool()
    def add_to_watchlist(tickers: list[str]) -> dict:
        """Add stocks to the watchlist (fetched at the next daily update or with refresh_stock)."""
        return tools.add_to_watchlist(tickers)

    @srv.tool()
    def remove_from_watchlist(tickers: list[str]) -> dict:
        """Remove stocks from the watchlist."""
        return tools.remove_from_watchlist(tickers)


    # ---------- prompts: ready-made requests that clients can show as slash commands ----------
    def _prompt(name, title, description, arg, template):
        try:
            deco = srv.prompt(name=name, title=title, description=description)
        except TypeError:                                   # SDK 1.x: no title
            deco = srv.prompt(name=name, description=f"{title} — {description}")
        fill = lambda x: template.replace("{x}", x)
        if arg is None:
            def f() -> str:
                return template
        elif arg == "conditions":                           # optional
            def f(conditions: str = "") -> str:
                return fill(conditions or "（没有给条件）")
        elif arg == "ticker":
            def f(ticker: str) -> str:
                return fill(ticker)
        elif arg == "holdings":
            def f(holdings: str) -> str:
                return fill(holdings)
        else:
            def f(idea: str) -> str:
                return fill(idea)
        return deco(f)

    for name, title, description, arg, template in PROMPTS:
        _prompt(name, title, description, arg, template)

    return srv


def _q(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def dsh_entry(data_dir: str, python: str | None = None, workdir: str | None = None) -> str:
    """The cordis patch item that starts stockproof's MCP server with THIS Python (found automatically,
    so it works on any computer: Mac, Windows, Linux, venv or not)."""
    python = python or sys.executable
    workdir = workdir or os.path.dirname(os.path.abspath(data_dir))
    return f"""- insert:
    - id: stockproof-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: stockproof
        transport: stdio
        command: {_q(python)}
        args: ['-m', 'stockproof', 'mcp', '--load-shell-env', '--data-dir', {_q(os.path.abspath(data_dir))}]
        cwd: {_q(workdir)}
        env:
          # DSH removes variables named like *KEY* / *TOKEN* before starting a server; pass these on
          DEEPSEEK_API_KEY: !!js process.env.DEEPSEEK_API_KEY ?? ''
          STOCKPROOF_SEC_CONTACT: !!js process.env.STOCKPROOF_SEC_CONTACT ?? ''
"""


def dsh_config(data_dir: str) -> str:
    """A standalone patch file (for `dsh web --patch FILE`)."""
    workdir = os.path.abspath(os.getcwd())
    return (f"# stockproof for DeepSeek Harness (generated for this computer)\n"
            f"# Easiest: `stockproof mcp --install-dsh` adds this to DSH for you (desktop app included).\n"
            f"# Web, once:  dsh web --patch \"{os.path.join(workdir, 'stockproof.cordis.yml')}\"\n"
            + dsh_entry(data_dir, workdir=workdir))


BEGIN, END = "# >>> stockproof (added by `stockproof mcp --install-dsh`; remove with --uninstall-dsh)", "# <<< stockproof"


def dsh_home() -> str:
    return os.environ.get("DSH_HOME") or os.path.join(os.path.expanduser("~"), ".dsh")


# the block written before the project was renamed (0.2, "marketmood")
OLD_BEGIN, OLD_END = "# >>> marketmood (added by `marketmood mcp --install-dsh`", "# <<< marketmood"


def _strip_block(text: str, begin: str = BEGIN, end: str = END) -> str:
    if begin not in text:
        return text
    a = text.index(begin)
    b = text.index(end, a) + len(end) if end in text[a:] else len(text)
    return (text[:a].rstrip("\n") + "\n" + text[b:].lstrip("\n")).strip("\n") + ("\n" if text.strip() else "")


def _strip_all(text: str) -> str:
    return _strip_block(_strip_block(text), OLD_BEGIN, OLD_END)


def install_dsh(data_dir: str, home: str | None = None, python: str | None = None) -> dict:
    """Add (or update) stockproof in DSH's home-level cordis.patch.yml, which every DSH profile reads —
    the desktop app included. The file is backed up first; other entries are left as they are."""
    import datetime as dt
    home = home or dsh_home()
    path = os.path.join(home, "cordis.patch.yml")
    existed = os.path.exists(home)
    os.makedirs(home, exist_ok=True)
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            text = f.read()
    rest = _strip_all(text)
    if "id: stockproof-mcp" in rest:
        return {"ok": False, "path": path,
                "error": "a stockproof entry you added by hand is already in this file; remove it, then run again"}
    body = [ln for ln in rest.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if body and not body[0].startswith("- "):
        return {"ok": False, "path": path,
                "error": "this file is not a list of patch items; add the entry from `stockproof mcp --dsh-config` by hand"}
    backup = None
    if text:
        backup = f"{path}.bak-{dt.datetime.now():%Y%m%d-%H%M%S}"
        with open(backup, "w", encoding="utf-8") as f:
            f.write(text)
    block = f"{BEGIN}\n{dsh_entry(data_dir, python=python)}{END}\n"
    new = (rest.rstrip("\n") + "\n" + block) if rest.strip() else block
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    skills = install_skills(home)
    return {"ok": True, "path": path, "backup": backup, "created_home": not existed,
            "updated": BEGIN in text or OLD_BEGIN in text, "skills": skills}


def uninstall_dsh(home: str | None = None) -> dict:
    uninstall_skills(home)
    path = os.path.join(home or dsh_home(), "cordis.patch.yml")
    if not os.path.exists(path):
        return {"ok": True, "path": path, "removed": False}
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if BEGIN not in text and OLD_BEGIN not in text:
        return {"ok": True, "path": path, "removed": False}
    with open(path, "w", encoding="utf-8") as f:
        f.write(_strip_all(text))
    return {"ok": True, "path": path, "removed": True}


def main(data_dir: str, provider: str, model: str | None, base_url: str | None, auto_dashboard: bool = False) -> int:
    tools = Tools(data_dir, provider, model, base_url)
    tools.auto_dashboard = auto_dashboard or os.environ.get("STOCKPROOF_AUTO_DASHBOARD", "0") == "1"   # opt-in
    tools.welcome = True                # first answer ever: introduce the features and suggest the dashboard
    srv = build_server(tools)
    tools.auto_open("startup")
    srv.run("stdio")
    return 0
