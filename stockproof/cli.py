"""
Command line interface.

  stockproof scan AAPL MSFT NVDA
  stockproof scan --watchlist my_stocks.txt --lang zh --open
  stockproof scan T=AT&T C=Citigroup --provider openai --model gpt-4o-mini
  stockproof earnings AAPL MSFT --lang zh --open
  stockproof earnings --watchlist my_stocks.txt --csv eps_history.csv
  stockproof dashboard --watchlist watchlist_research.txt
  stockproof research --market cn --lang zh --open
  stockproof daily                       # one refresh of the dashboard watchlist
  stockproof schedule --time 21:00       # ... every day at 21:00 (macOS)
  stockproof calendar                    # who reports earnings in the next 14 days
  stockproof mcp                         # MCP server for AI agents (DeepSeek Harness, Claude...)
  stockproof providers
"""

from __future__ import annotations

import argparse
import os
import datetime as dt
import sys
import webbrowser
from pathlib import Path

import pandas as pd

from stockproof import __version__, cn, core
from stockproof.companies import company_name, display_name
from stockproof.llm import PROVIDERS, LLMClient, LLMError
from stockproof.report import build_report
from stockproof.store import Store
from stockproof.summary import summarize


def parse_tickers(args) -> tuple[list[str], dict]:
    """Tickers from the command line and/or a watchlist file.
    Accepts 'AAPL' or 'T=AT&T' (ticker=company name)."""
    entries = list(args.tickers)
    if args.watchlist:
        with open(args.watchlist, encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if not line or line.lower().startswith("ticker"):
                    continue
                if "," in line and "=" not in line:          # CSV: ticker,name
                    tk, name = [x.strip() for x in line.split(",", 1)]
                    line = f"{tk}={name}" if name else tk
                entries.append(line)
    tickers, names = [], {}
    for e in entries:
        tk, _, name = e.partition("=")
        tk = cn.canonical(tk.strip().upper())           # 600519 -> 600519.SH, 700 -> 00700.HK
        if tk and tk not in tickers:
            tickers.append(tk)
        if name.strip():
            names[tk] = name.strip()
    return tickers, names


def cmd_scan(args) -> int:
    tickers, overrides = parse_tickers(args)
    if not tickers:
        print("No tickers given. Example: stockproof scan AAPL MSFT NVDA", file=sys.stderr)
        return 2
    try:
        client = LLMClient.from_provider(args.provider, args.model, args.base_url)
    except LLMError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    model_id = f"{args.provider}:{client.model}"
    store = Store(args.data_dir)
    names = {tk: company_name(tk, overrides) for tk in tickers}

    print(f"stockproof {__version__} · {model_id} · {len(tickers)} stocks · lang={args.lang}")
    new_scores = 0
    for tk in tickers:
        res = core.scan_ticker(store, client, model_id, tk, names[tk], args.per_ticker, args.lang)
        if res["error"]:
            print(f"  {tk:6s} {res['error']}")
            if res["fatal"]:
                return 1
            continue
        new_scores += res["scored"]
        print(f"  {tk:6s} {res['headlines']:2d} headlines, {res['new']:2d} newly scored")

    names = {tk: display_name(tk, overrides, args.data_dir) for tk in tickers}
    since = (dt.date.today() - dt.timedelta(days=args.days)).isoformat()
    details = store.scored(tickers, model_id, args.lang, since=since)
    summary = summarize(details, tickers, args.min_relevance, args.min_sample)

    print(f"\n{'Stock':8s}{'Mood':>8s}  {'Relevant/All':>12s}  {'Good/Bad':>9s}")
    for _, r in summary.iterrows():
        mood = "   —" if r["mood"] is None or r["mood"] != r["mood"] else f"{r['mood']:+.2f}"
        flag = "  * few relevant headlines" if r["few"] else ""
        print(f"{r['ticker']:8s}{mood:>8s}  {r['relevant']:>5d}/{r['headlines']:<6d}  "
              f"{r['positive']:>4d}/{r['negative']:<4d}{flag}")

    if args.csv:
        details.to_csv(args.csv, index=False, encoding="utf-8-sig")
        print(f"\nSaved headline data to {args.csv}")
    if not args.no_report:
        html_text = build_report(summary, details, names, lang=args.lang, model=model_id,
                                 days=args.days, min_relevance=args.min_relevance,
                                 min_sample=args.min_sample)
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(html_text)
        print(f"Saved report to {args.report}")
        if args.open:
            # as_uri() percent-encodes the path, so folders with Chinese or other
            # non-ASCII names (e.g. ~/Desktop/股票项目) open correctly
            webbrowser.open(Path(args.report).resolve().as_uri())
    print(f"({new_scores} new LLM scores; data kept in {store.path})")
    return 0


def cmd_earnings(args) -> int:
    from stockproof.earnings_report import build_earnings_report
    from stockproof.sec import SECCache, SECError, contact

    tickers, overrides = parse_tickers(args)
    if not tickers:
        print("No tickers given. Example: stockproof earnings AAPL MSFT 600519", file=sys.stderr)
        return 2
    us = [t for t in tickers if not cn.is_cn(t)]
    try:
        if us:
            contact()                                  # SEC rule, only needed for US stocks
        client = None if args.no_llm else LLMClient.from_provider(args.provider, args.model, args.base_url)
    except (SECError, LLMError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    model_id = "none" if client is None else f"{args.provider}:{client.model}"
    store = Store(args.data_dir)
    sec = None
    if us:
        cache = SECCache(args.data_dir)
        try:
            sec = (cache, cache.ticker_map())
        except Exception as e:
            print(f"Error: could not load SEC ticker list ({e})", file=sys.stderr)
            return 1

    print(f"stockproof {__version__} earnings · {model_id} · {len(tickers)} stocks · lang={args.lang}")
    rows, histories = [], []
    for tk in tickers:
        name = display_name(tk, overrides, args.data_dir)
        row = core.earnings_any(store, args.data_dir, client, model_id, tk, args.lang,
                                name=name if name != tk else None, sec=sec)
        for msg in row["errors"]:
            print(f"  {tk:9s} {msg}")
        if row["fatal"]:
            return 1
        if row["read"] is None and row["history"] is None:
            continue
        rows.append(row)
        hist = row["history"]
        if hist is not None and len(hist):
            h = hist.copy()
            h.insert(0, "ticker", tk)
            histories.append(h)

        read, fc = row["read"], row.get("forecast")
        sue = hist["sue"].dropna() if hist is not None else pd.Series(dtype=float)
        sue_txt = f"SUE {sue.iloc[-1]:+.1f}" if len(sue) else "SUE —"
        fc_txt = f"  预告 {fc['type']} {fc['change_pct']:+.0f}%" if fc and fc.get("change_pct") is not None else ""
        if read:
            print(f"  {tk:9s} {read['filed']}  tone {read['tone']:+.2f}  guidance {read['guidance']:10s} {sue_txt}{fc_txt}")
        else:
            print(f"  {tk:9s} no report read            {sue_txt}{fc_txt}")

    if args.csv and histories:
        pd.concat(histories, ignore_index=True).to_csv(args.csv, index=False, encoding="utf-8-sig")
        print(f"\nSaved EPS / SUE history to {args.csv}")
    if not args.no_report and rows:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(build_earnings_report(rows, lang=args.lang, model=model_id))
        print(f"Saved report to {args.report}")
        if args.open:
            webbrowser.open(Path(args.report).resolve().as_uri())
    return 0


def cmd_dashboard(args) -> int:
    from stockproof.dashboard import Dashboard, serve
    app = Dashboard(args.data_dir, args.provider, args.model, args.base_url,
                    per_ticker=args.per_ticker, days=args.days)
    app.echo = True
    if args.watchlist or args.tickers:
        tickers, names = parse_tickers(args)
        if not app.settings["watchlist"] or args.replace:
            app.set_watchlist([f"{t}={names[t]}" if t in names else t for t in tickers])
            print(f"Watchlist set to {len(tickers)} stocks.")
        else:
            print("Keeping the saved watchlist (use --replace to overwrite it).")
    try:
        serve(app, args.port, open_browser=not args.no_browser)
    except OSError as e:
        print(f"Could not start on port {args.port} ({e}). Try --port 8766.", file=sys.stderr)
        return 1
    return 0


def _research_prices(args, tickers):
    """Load or download the price file. Returns (prices, error_code)."""
    import os
    from stockproof import research as rs
    cn_mode = args.market == "cn"
    path = args.prices or os.path.join(args.data_dir, "prices_cn.csv" if cn_mode else "prices.csv")
    if not args.download and os.path.exists(path):
        return rs.load_prices(path), 0
    if not args.download and not cn_mode:
        print(f"No price file at {path}. Use --download (needs: pip install yfinance) "
              f"or --prices your_prices.csv", file=sys.stderr)
        return None, 2
    if cn_mode:
        from stockproof import research_cn as rc
        print(f"Downloading back-adjusted prices for {len(tickers)} A-shares + CSI 300 since {args.since} "
              f"(about 1-2 s per stock) ...")
        rc.download_prices_cn(tickers, args.since, path)
        return rs.load_prices(path), 0
    if not tickers:
        print("Give tickers or --watchlist to download prices for.", file=sys.stderr)
        return None, 2
    print(f"Downloading prices for {len(tickers)} stocks + SPY since {args.since} ...")
    return rs.download_prices([t for t in tickers if not cn.is_cn(t)], args.since, path), 0


def cmd_research(args) -> int:
    import os
    from stockproof import research as rs
    from stockproof.research_report import build_research_report
    from stockproof.sec import SECCache, SECError, contact

    cn_mode = args.market == "cn"
    tickers, overrides = parse_tickers(args)
    if cn_mode:
        from stockproof import research_cn as rc
        tickers = [t for t in tickers if cn.is_cn(t) and not t.endswith(".HK")]
        if not tickers:
            try:
                print(f"Universe: current members of index {args.index} ...")
                tickers = [cn.canonical(c) for c in rc.index_members(args.index)]
            except Exception as e:
                print(f"Error: could not load index members ({e})", file=sys.stderr)
                return 1
    try:
        prices, code = _research_prices(args, tickers)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if prices is None:
        return code
    ar = rs.abnormal_returns(prices, use_index=args.benchmark == "index")
    if not tickers:
        tickers = list(ar.columns)
    tickers = [t for t in tickers if t in ar.columns]
    print(f"stockproof {__version__} research ({args.market}) · {len(tickers)} stocks with prices · "
          f"{prices.index[0].date()} to {prices.index[-1].date()}")

    store = Store(args.data_dir)
    bench = next((c for c in rs.BENCHMARKS if c in prices.columns), "") if args.benchmark == "index" else ""
    res = {"prices": {"n": len(ar.columns), "start": prices.index[0].date().isoformat(),
                      "end": prices.index[-1].date().isoformat(), "bench": bench, "benchmark": args.benchmark}}
    events = pd.DataFrame()

    if cn_mode and not args.skip_earnings:
        print(f"Earnings: report periods since {args.since} (EPS, disclosure dates, preliminary results) ...")
        try:
            quarters = rc.build_quarters_cn(cn.CNCache(args.data_dir),
                                            [cn.parse(t)["code"] for t in tickers], args.since)
        except Exception as e:
            print(f"Earnings study skipped: {e}", file=sys.stderr)
            quarters = pd.DataFrame()
        if len(quarters):
            events = rc.summarize_by_actual(rs.earnings_events(quarters, ar))
        cn_cache = cn.CNCache(args.data_dir)
        if len(events) and args.backfill:
            try:
                client = LLMClient.from_provider(args.provider, args.model, args.base_url)
            except LLMError as e:
                print(f"Error: {e}", file=sys.stderr)
                return 2
            model_id = f"{args.provider}:{client.model}"
            print(f"Reading past reports with {model_id} (up to {args.backfill} per stock) ...")
            try:
                stats = rc.backfill_reads_cn(store, client, model_id, events[events["date_source"] == "8-K"],
                                             cn_cache, args.backfill)
            except Exception as e:
                print(f"Stopped: {e}", file=sys.stderr)
                return 1
            print(f"  {stats['read']} read, {stats['cached']} already saved, "
                  f"{stats['no_document']} without a document, {stats['failed']} failed")
        if len(events):
            from stockproof import earnings as er
            model = args.model or PROVIDERS[args.provider]["model"]
            events = rs.attach_reads(rc.attach_docs(events, cn_cache), store,
                                     f"{args.provider}:{model}#v{er.READ_VERSION}")
            summ = rs.summarize_earnings(events)
            summ.update(n_stocks=int(events["ticker"].nunique()), market="cn")
            res["earnings"] = summ
            print(f"  {len(events)} quarters, {summ.get('n_8k', 0)} with an actual disclosure date, "
                  f"{summ.get('n_tone', 0)} with an LLM reading")

    us = [t for t in tickers if not cn.is_cn(t)]
    if us and not cn_mode and not args.skip_earnings:
        fetch = not args.offline
        try:
            if fetch:
                contact()
            cache = SECCache(args.data_dir)
            tmap = cache.ticker_map() if fetch else {
                str(r["ticker"]).upper().replace(".", "-"): {"cik": int(r["cik_str"]), "name": r["title"]}
                for r in (cache.cached("company_tickers.json") or {}).values()}
        except SECError as e:
            print(f"Earnings study skipped: {e}\n(or use --offline to use only saved SEC files)", file=sys.stderr)
            tmap = None
        if tmap is not None:
            print(f"Earnings: collecting quarters and announcement dates since {args.since} ...")
            quarters = rs.build_quarters(cache, tmap, us, args.since, fetch)
            events = rs.earnings_events(quarters, ar) if len(quarters) else pd.DataFrame()
            if len(events) and args.backfill:
                try:
                    client = LLMClient.from_provider(args.provider, args.model, args.base_url)
                except LLMError as e:
                    print(f"Error: {e}", file=sys.stderr)
                    return 2
                model_id = f"{args.provider}:{client.model}"
                names = {t: display_name(t, overrides, args.data_dir) for t in us}
                print(f"Reading past press releases with {model_id} (up to {args.backfill} per stock) ...")
                try:
                    stats = rs.backfill_reads(store, client, model_id, events, names, args.backfill)
                except Exception as e:
                    print(f"Stopped: {e}", file=sys.stderr)
                    return 1
                print(f"  {stats['read']} read, {stats['cached']} already saved, {stats['failed']} failed")
            if len(events):
                from stockproof import earnings as er
                model = args.model or PROVIDERS[args.provider]["model"]
                events = rs.attach_reads(events, store, f"{args.provider}:{model}#v{er.READ_VERSION}")
                summ = rs.summarize_earnings(events)
                summ.update(n_stocks=int(events["ticker"].nunique()), market="us")
                res["earnings"] = summ
                print(f"  {len(events)} quarters, {summ.get('n_8k', 0)} with an 8-K date, "
                      f"{summ.get('n_tone', 0)} with an LLM reading")

    # ---- backtest: can the drift be traded after costs?
    if len(events) and not args.skip_backtest:
        from stockproof import backtest as bt
        main = events[events["date_source"] == "8-K"]
        print(f"Backtest: SUE >= {args.long_sue:g} long / <= {-args.long_sue:g} short, "
              f"hold {args.hold} days, with costs ...")
        try:
            res["backtest"] = bt.full(main, prices, args.market, args.long_sue, args.hold)
            le = res["backtest"].get("long_excess", {})
            if le.get("ann_return") is not None:
                print(f"  {res['backtest']['n_long']} long trades; long-only vs the market "
                      f"{100 * le['ann_return']:+.1f}% a year (t = {le['t']:.1f})")
        except Exception as e:
            print(f"  backtest skipped: {type(e).__name__}: {e}", file=sys.stderr)

    # ---- news (any market: whatever stocks the price file has)
    nv = rs.news_events(store, ar, args.min_relevance)
    res["news"] = rs.summarize_news(nv)
    print(f"News: {len(nv)} relevant headlines, {res['news'].get('n_d1_5', 0)} with a full 5-day window")

    # ---- outputs
    report = args.report or ("stockproof_research_cn.html" if cn_mode else "stockproof_research.html")
    files = []
    base = os.path.splitext(report)[0]
    if len(events):
        events.drop(columns=[c for c in ("primary",) if c in events.columns]).to_csv(
            base + "_earnings_events.csv", index=False, encoding="utf-8-sig")
        files.append(base + "_earnings_events.csv")
    if len(nv):
        nv.to_csv(base + "_news_events.csv", index=False, encoding="utf-8-sig")
        files.append(base + "_news_events.csv")
    with open(report, "w", encoding="utf-8") as f:
        f.write(build_research_report(res, lang=args.lang, files=files))
    prices_path = args.prices or os.path.join(args.data_dir, "prices_cn.csv" if cn_mode else "prices.csv")
    rs.save_results(args.data_dir, args.market, events, nv, res["prices"], prices_path,
                    res.get("backtest"))   # for the dashboard
    print(f"Saved report to {report}" + (f" (+ {', '.join(files)})" if files else ""))
    if args.open:
        webbrowser.open(Path(report).resolve().as_uri())
    return 0


def cmd_daily(args) -> int:
    from stockproof import schedule
    if args.load_shell_env:
        schedule.load_shell_env()
    return schedule.daily(args.data_dir, args.provider, args.model, args.base_url, args.lang,
                          skip_earnings=args.skip_earnings)


def cmd_schedule(args) -> int:
    from stockproof import schedule
    if args.remove:
        print(schedule.remove())
    elif args.run_now:
        print(schedule.run_now())
    elif args.time:
        try:
            h, m = (int(x) for x in args.time.split(":"))
            assert 0 <= h < 24 and 0 <= m < 60
        except (ValueError, AssertionError):
            print("Give the time as HH:MM, e.g. --time 21:00", file=sys.stderr)
            return 2
        extra = ["--provider", args.provider] + (["--skip-earnings"] if args.skip_earnings else [])
        print(schedule.install(f"{h:02d}:{m:02d}", args.data_dir, extra))
    else:
        print(schedule.status(args.data_dir))
    return 0


def cmd_calendar(args) -> int:
    import json as _json
    from stockproof import earnings_calendar as cal
    if args.watchlist or args.tickers:
        tickers, _ = parse_tickers(args)
    else:
        try:
            with open(os.path.join(args.data_dir, "dashboard.json"), encoding="utf-8") as f:
                tickers = _json.load(f).get("watchlist", [])
        except (OSError, ValueError):
            tickers = []
    if not tickers:
        print("No stocks: give tickers, --watchlist, or add stocks in the dashboard.", file=sys.stderr)
        return 2
    if not args.offline:
        cal.refresh(args.data_dir, tickers, days=args.days)
    items = cal.upcoming(args.data_dir, tickers, args.days)
    if not items:
        print(f"No reports found in the next {args.days} days for these {len(tickers)} stocks.")
    labels = {"before_open": "before open", "after_close": "after close"}
    for i in items:
        extra = []
        if i.get("time"):
            extra.append(labels.get(i["time"], i["time"]))
        if i.get("eps_forecast") is not None:
            extra.append(f"consensus EPS {i['eps_forecast']:.2f}")
        if i.get("source") == "estimate":
            extra.append("estimated from last year")
        print(f"  {i['date']}  {i['ticker']:10s} {display_name(i['ticker'], {}, args.data_dir):24s} {', '.join(extra)}")
    return 0


def cmd_mcp(args) -> int:
    from stockproof import mcp_server
    data_dir = os.path.abspath(args.data_dir)
    if args.install_dsh or args.uninstall_dsh:
        res = mcp_server.uninstall_dsh() if args.uninstall_dsh else mcp_server.install_dsh(data_dir)
        if not res["ok"]:
            print(f"Error: {res['error']}\n  ({res['path']})", file=sys.stderr)
            return 1
        if args.uninstall_dsh:
            print(f"Removed stockproof from {res['path']}" if res["removed"] else "stockproof was not installed in DSH.")
            return 0
        print(f"{'Updated' if res['updated'] else 'Added'} stockproof in {res['path']}")
        if res["backup"]:
            print(f"  previous file saved as {res['backup']}")
        if res["created_home"]:
            print("  (that folder did not exist: if your DSH keeps its settings elsewhere, set DSH_HOME and run again)")
        print(f"  Python: {sys.executable}\n  Data:   {data_dir}")
        if res.get("skills"):
            print(f"  / commands: {len(res['skills'])} skills (type /stockproof in DSH): " + ", ".join(res["skills"]))
        print("Restart DeepSeek Harness (desktop app or `dsh web`), then ask e.g. “我关注的股票今天有什么重要的事？”")
        return 0
    if args.dsh_config:
        text = mcp_server.dsh_config(data_dir)
        with open("stockproof.cordis.yml", "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        print(f"Saved to {os.path.abspath('stockproof.cordis.yml')}", file=sys.stderr)
        return 0
    if args.load_shell_env:
        from stockproof.schedule import load_shell_env
        load_shell_env()                      # keys from the user's shell, this process only (never saved)
    return mcp_server.main(data_dir, args.provider, args.model, args.base_url, args.auto_dashboard)


def cmd_screen(args) -> int:
    """Whole-market A-share screen (stage 1, no LLM), optionally tested on history."""
    from stockproof import research as rs
    from stockproof import screener as sc
    zh = args.lang == "zh"
    cache = cn.CNCache(args.data_dir)
    since = args.since or (f"{dt.date.today().year - 4}-01-01" if not args.backtest else "2015-01-01")
    print(f"stockproof {__version__} screen · A-shares · reports since {since}")
    print("1/3 业绩报表 (all A-shares, every report period; cached after the first run) ..."
          if zh else "1/3 Earnings tables (all A-shares, every report period; cached after the first run) ...")
    try:
        pan = sc.panel(cache, since)
    except cn.Blocked as e:
        print(f"Stopped: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: could not load earnings tables ({type(e).__name__}: {e})", file=sys.stderr)
        return 1
    if not len(pan):
        print("Error: no earnings data.", file=sys.stderr)
        return 1
    print(f"  {pan['code'].nunique()} stocks, {len(pan)} reports")

    if args.backtest:
        meta = rs.saved_meta(args.data_dir, "cn") or {}
        path = args.prices or meta.get("prices_path")
        if not path or not os.path.exists(path):
            print("Backtest needs China prices: run `stockproof research --market cn` once first "
                  "(it downloads CSI300 prices), or pass --prices.", file=sys.stderr)
            return 2
        prices = rs.load_prices(path)
        print(f"Backtest on {prices.shape[1]} stocks with prices ({prices.index[0].date()} to "
              f"{prices.index[-1].date()}), top {args.top}, rebalanced early May / Sep / Nov ...")
        tests = sc.factor_test(pan, prices, args.top)
        full = sc.backtest(pan, prices, args.top)
        names = sc.FACTOR_NAMES["zh" if zh else "en"]
        print(f"\n  {'factors':28s} {'periods':>7s} {'excess/yr':>10s} {'t':>6s} {'beat mkt':>9s} {'max DD':>8s}")
        for r in tests:
            label = "all (composite)" if len(r["factors"]) > 1 else names[r["factors"][0]]
            if not r.get("n"):
                print(f"  {label:28s} {'-':>7s}")
                continue
            print(f"  {label:28s} {r['n']:7d} {100 * r['ann_excess']:+9.2f}% {r['t']:6.2f} "
                  f"{100 * r['hit_rate']:8.0f}% {100 * r['max_dd']:7.1f}%")
        if full.get("n"):
            print(f"\n  composite: {100 * full['ann_return']:+.1f}%/yr vs universe {100 * full['ann_market']:+.1f}%/yr, "
                  f"after ~{2 * 0.15:.1f}% round-trip costs; avg turnover {100 * full['avg_turnover']:.0f}% per rebalance")
            print("  Caveat: the universe is today's CSI300 members (survivorship), so only the excess over the "
                  "same universe is meaningful.")
        import json as _json
        with open(os.path.join(sc.screens_dir(args.data_dir), "cn_backtest.json"), "w", encoding="utf-8") as f:
            _json.dump({"composite": full, "factors": tests, "top": args.top,
                        "updated": dt.datetime.now().isoformat(timespec="seconds")}, f, default=str)
        if args.skip_screen:
            return 0

    print("2/3 市场快照 (price, momentum, market value for every A-share) ..."
          if zh else "2/3 Market snapshot (price, momentum, market value for every A-share) ...")
    try:
        snap = sc.snapshot(cache)
    except cn.Blocked as e:
        print(f"Stopped: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        import traceback
        where = traceback.extract_tb(e.__traceback__)[-1]
        print(f"Error: could not load the market snapshot ({type(e).__name__}: {e}) "
              f"[{os.path.basename(where.filename)}:{where.lineno}]", file=sys.stderr)
        return 1
    print(f"  {len(snap)} A-shares")
    if len(snap) < 4500:
        print(f"  警告：只拿到 {len(snap)} 只（全市场约 5000 只），名单不完整" if zh else
              f"  Warning: only {len(snap)} stocks (the market has ~5000); the list is incomplete")
    if snap["mom60"].isna().all():
        print("  （这次快照来自新浪，没有近 60 日涨跌，走势这一项不计分）" if zh else
              "  (snapshot from Sina has no 60-day return; momentum is left out this time)")
    print("3/3 Scoring ...")
    full = sc.screen(pan, snap, top=None, min_cap=args.min_cap)
    out = sc.screen(pan, snap, top=args.top, min_cap=args.min_cap, per_industry=args.per_industry or None)
    recs = sc.to_records(out, args.lang)
    meta = {"as_of": dt.date.today().isoformat(), "universe": int(len(snap)), "min_cap": args.min_cap,
            "top": args.top, "per_industry": args.per_industry, "since": since, "factors": sc.FACTORS,
            "screened": int(len(full)), "momentum": bool(snap["mom60"].notna().any())}
    path = sc.save(args.data_dir, recs, meta, sc.compact_all(full))
    print(f"\n  {'#':>4s} {'ticker':10s} {'name':10s} {'score':>5s}  {'industry':10s} reasons")
    for r in recs:
        print(f"  {r['rank']:4d} {r['ticker']:10s} {str(r['name'])[:8]:10s} {r['score']:5.0f}  "
              f"{str(r.get('industry') or '')[:8]:10s} {'; '.join(r['reasons'])}")
    print(f"\n{len(full)} stocks scored; any of them can be looked up later. Saved {path}")
    print("这是按公开数据排序的候选名单，不是买卖建议；请结合研究结论（财报漂移扣费后几乎无超额）自行判断。"
          if zh else "A ranked list from public data, not buy/sell advice. See the backtest (--backtest) before trusting it.")
    return 0


def cmd_scorecard(args) -> int:
    """Evidence scorecards for given stocks, or for the top of the latest screen."""
    from stockproof import scorecard as scd
    from stockproof import screener as sc
    from stockproof.dashboard import Dashboard
    zh = args.lang == "zh"
    app = Dashboard(args.data_dir, args.provider, args.model, args.base_url)
    tickers, _ = parse_tickers(args)
    if not tickers:
        saved = sc.load_latest(args.data_dir)
        if not saved:
            print("No stocks: give tickers, or run `stockproof screen` first." if not zh else
                  "没有股票：请写股票代码，或先运行 stockproof screen。", file=sys.stderr)
            return 2
        tickers = [r["ticker"] for r in saved["results"][:args.top]]
        print((f"选股名单前 {len(tickers)} 只（{saved['meta'].get('as_of')}）" if zh else
               f"Top {len(tickers)} of the screen from {saved['meta'].get('as_of')}"))
    try:
        client = LLMClient.from_provider(args.provider, args.model, args.base_url)
    except LLMError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    model_id = f"{args.provider}:{client.model}"
    store = Store(args.data_dir)
    cards = []
    for k, tk in enumerate(tickers, 1):
        tk = cn.canonical(tk)
        if not args.no_refresh:
            print(f"[{k}/{len(tickers)}] {tk}: {'更新新闻、财报、公告' if zh else 'refreshing news, report, announcements'} ...",
                  flush=True)
            try:
                for p in scd.refresh_data(app, store, client, model_id, tk, args.lang):
                    print(f"    {p}")
            except RuntimeError as e:
                print(f"Stopped: {e}", file=sys.stderr)
                return 2
        try:
            card = scd.build(app, store, client, model_id, tk, args.lang, force=args.force)
        except Exception as e:
            from stockproof.core import is_fatal
            if is_fatal(e):
                print(f"Stopped: {e}", file=sys.stderr)
                return 2
            print(f"    {tk}: {type(e).__name__}: {str(e)[:120]}")
            continue
        cards.append(card)
        print(scd.text(card, args.lang) + "\n", flush=True)
    if cards:
        path = scd.save_batch(args.data_dir, cards)
        ranked = sorted((c for c in cards if c["overall"].get("score") is not None),
                        key=lambda c: -c["overall"]["score"])
        print("—" * 60)
        print("汇总（按证据分）：" if zh else "Summary (by evidence score):")
        for c in ranked:
            print(f"  {c['overall']['score']:5.1f}  {c['ticker']:10s} {str(c.get('name') or '')[:10]:12s} "
                  f"{c['overall']['label_text']}")
        print(f"\nSaved {path}")
        print("✓ = 历史检验有效  · = 检验过但不显著  ? = 尚未检验" if zh else
              "✓ = useful in history tests  · = tested, not significant  ? = not tested yet")
        print(scd.DISCLAIMER["zh" if zh else "en"])
    return 0


def cmd_policy(args) -> int:
    """Policy-signal study: 新闻联播 -> LLM reading -> Shenwan industry returns."""
    from stockproof import policy as pl
    zh = args.lang == "zh"
    since = args.since
    print(f"stockproof {__version__} policy study · 新闻联播 since {since}")
    if not args.skip_download:
        print("1/4 新闻联播 transcripts (cached per day; resumable — Ctrl+C is safe) ...")
        try:
            st = pl.download(args.data_dir, since, workers=args.workers)
        except KeyboardInterrupt:
            print("\nStopped; finished days are kept. Run the same command to continue.")
            return 1
        print(f"  {st['days']} days · {st['todo']} were missing · {st['ok']} downloaded · {st['empty']} empty · "
              f"{st['failed']} failed (run again to retry)")
    days = pl.days_between(since, dt.date.today().isoformat())
    have = [d for d in days if pl.load_day(args.data_dir, d) is not None]
    print(f"  {len(have)} days with transcripts")
    store = Store(args.data_dir)
    model = args.model or PROVIDERS[args.provider]["model"]
    model_id = f"{args.provider}:{model}"
    if not args.skip_read:
        try:
            client = LLMClient.from_provider(args.provider, args.model, args.base_url)
        except LLMError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2
        todo = have if not args.max_days else have[-args.max_days:]
        print(f"2/4 Reading policy wording with {model_id} ({len(todo)} days; cached) ...")
        try:
            st = pl.read_days(store, client, model_id, args.data_dir, todo, workers=args.workers)
        except KeyboardInterrupt:
            print("\nStopped; finished days are kept. Run the same command to continue.")
            return 1
        except LLMError as e:
            print(f"Stopped: {e}", file=sys.stderr)
            return 2
        print(f"  {st['read']} days read · {st['no_candidates']} without policy items · {st['failed']} failed · "
              f"{st['signals']} new signals")
    print("3/4 Shenwan industry indices ...")
    px = pl.load_prices(args.data_dir)
    if px is None or args.refresh_prices or (dt.date.today() - px.index[-1].date()).days > 3:
        try:
            px = pl.download_prices(args.data_dir)
        except Exception as e:
            if px is None:
                print(f"Error: {e}", file=sys.stderr)
                return 1
            print(f"  update failed ({e}); using saved prices to {px.index[-1].date()}")
    print("4/4 Event study ...")
    sig = pl.signals_frame(store, model_id)
    if not len(sig):
        print("No signals yet: run without --skip-read first.")
        return 1
    names = {"pre20": "20d before", "gap": "overnight gap", "react": "entry day", "d2_20": "day 2-20",
             "d21_60": "day 21-60"}
    labels = {"all": "all", "support": "support (all)", "restrict": "restrict (all)",
              "support_escalation_3plus": "support escalation ≥3", "restrict_escalation_3plus": "restrict escalation ≥3",
              "first_half": "  first half", "second_half": "  second half", "since_2025": "  since 2025"}
    for k in (1, 2, 3, 4):
        labels[f"support_{k}"] = f"support strength {k}"
        labels[f"restrict_{k}"] = f"restrict strength {k}"

    def line(key, row):
        cells = ""
        for c in names:
            m = row[c]
            t = m["t"] if m["t"] is not None else float("nan")
            cells += f"{'-':>16s}" if m["mean"] is None else f"{100 * m['mean']:+8.2f}% t={t:5.1f}"
        print(f"  {labels.get(key, key):28s}{row['events']:7d}{cells}")

    order = ["all", "support", "support_1", "support_2", "support_3", "support_4", "support_escalation_3plus",
             "restrict", "restrict_2", "restrict_3", "restrict_4", "restrict_escalation_3plus"]
    variants = {"new_measure": ("new_measure",), "leader_directive": ("leader_directive",), "all_kinds": None}
    titles = {"new_measure": "NEW central measures (documents, funds, regulations announced that day)",
              "leader_directive": "Leaders' speeches / directions (no concrete new measure)",
              "all_kinds": "Everything the LLM tagged (incl. progress reports)"}
    results, backtests = {}, {}
    for v, kinds in variants.items():
        ev = pl.attach_returns(pl.events(sig, kinds=kinds), px)
        res = pl.study(ev)
        results[v] = res
        if not res.get("n"):
            print(f"\n== {titles[v]}: no events")
            continue
        backtests[v] = {h: pl.backtest(ev, px, hold=h) for h in (20, 60)}
        print(f"\n== {titles[v]} · {res['n']} industry-days · {res['start']} to {res['end']}")
        print("  " + f"{'group':28s}{'events':>7s}" + "".join(f"{names[c]:>16s}" for c in names))
        for k in (order if v == "new_measure" else ["all", "support", "support_4", "support_escalation_3plus",
                                                     "restrict"]):
            if k in res["tables"] and res["tables"][k]["events"]:
                line(k, res["tables"][k])
        if v == "new_measure" and res.get("halves"):
            print("  strong support escalations by period:")
            for k, row in res["halves"].items():
                line(k, row)
        for h, b in backtests[v].items():
            if b.get("ann_excess") is not None:
                print(f"  backtest hold {h}d after strong-support escalations (next open, 0.1%/side): "
                      f"{100 * b['ann_excess']:+.2f}%/yr vs equal-weighted industries (t={b['t']:.1f}, {b['signals']} signals)")
    print("\n  returns = industry minus the average of 31 Shenwan industries; t averages per date first.")
    res, bt = results.get("new_measure", {}), backtests.get("new_measure", {})
    path = pl.save_results(args.data_dir, {"study": res, "backtest": bt, "variants": results, "variant_backtests": backtests,
                                           "model": model_id, "since": since,
                                           "signals": int(len(sig))})
    print(f"\nSaved {path}")
    print("政策信号只有在这里检验有效，才会进入评分卡的总分。" if zh else
          "Policy signals enter the scorecard total only if this test finds them useful.")
    return 0


def cmd_demo(args) -> int:
    from stockproof import demo
    return demo.run(args.port, args.lang, not args.no_browser)


def cmd_lab(args) -> int:
    """The quant lab from the terminal (the same engine the AI agent uses)."""
    import json as _json
    from stockproof import lab
    d, lang = args.data_dir, args.lang
    try:
        if args.action == "caps":
            print(_json.dumps(lab.capabilities(d), ensure_ascii=False, indent=1, default=str))
        elif args.action in ("run", "confirm"):
            if not args.arg:
                print("Usage: stockproof lab run SPEC.json | '{json}'   ·   stockproof lab confirm ID", file=sys.stderr)
                return 2
            if args.action == "run":
                raw = args.arg
                spec = _json.load(open(raw, encoding="utf-8")) if os.path.exists(raw) else _json.loads(raw)
                r = lab.explore(d, spec, lang)
            else:
                r = lab.confirm(d, args.arg, lang)
            print(f"{r['description']}\n  {r['universe']} · {r['period']} · {r['trades']} trades")
            ann, t = r.get("ann_excess"), r.get("t")
            if ann is not None:
                print(f"  excess {100 * ann:+.2f}%/yr · t={t:.2f}")
            print(f"  {r['verdict']['text']}\n  id {r['id']}\n  report: {r['report']}")
            if args.open:
                webbrowser.open("file://" + os.path.abspath(r["report"]))
        elif args.action == "list":
            for e in lab.list_experiments(d):
                t = e.get("t")
                print(f"  {e['id']:28s} {e['phase']:8s} {('%.2f' % t) if t is not None else '—':>6s}  {e['verdict']:10s} {e['description']}")
        elif args.action == "similar":
            print(_json.dumps(lab.similar(d, args.arg or "", lang=lang), ensure_ascii=False, indent=1, default=str))
        elif args.action == "reset":
            lab.reset(d)
            print("New research question: earlier variants no longer raise the bar (they stay in the log).")
    except lab.SpecError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    return 0


def cmd_portfolio(args) -> int:
    """Portfolio check-up: python -m stockproof portfolio "600519 100, AAPL 20" (or a CSV/JSON file)."""
    import json as _json
    from stockproof import portfolio
    raw = args.holdings
    if os.path.exists(raw):
        if raw.endswith(".json"):
            holdings = _json.load(open(raw, encoding="utf-8"))
        else:
            df = pd.read_csv(raw)
            holdings = df.to_dict("records")
    else:
        holdings = raw
    try:
        client = LLMClient.from_provider(args.provider, None, None)
    except LLMError:
        client = None
    try:
        r = portfolio.checkup(args.data_dir, holdings, lang=args.lang, client=client)
    except portfolio.HoldingsError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    for h in r["holdings"]:
        print(f"  {h['ticker']:10s} {str(h.get('name') or '')[:10]:12s} {100 * h['weight']:5.1f}%  risk {100 * h['risk_share']:4.0f}%  "
              f"{h.get('industry') or ''}")
    print()
    for f in r["findings"]:
        print(f"  • {f['text']}")
    for s in r["stress"]:
        print(f"  {s['name']:24s} {100 * s['portfolio']:+6.1f}%")
    print(f"\nReport: {r['report']}")
    if not args.no_open:
        webbrowser.open("file://" + os.path.abspath(r["report"]))
    return 0


def cmd_providers(args) -> int:
    print("Built-in providers (any OpenAI-compatible server also works with --base-url):\n")
    for name, p in PROVIDERS.items():
        key = p["key_env"] or "(no key needed)"
        print(f"  {name:9s} model={p['model']:14s} key env: {key}")
    return 0


def default_data_dir() -> str:
    """stockproof_data, or the folder used before the rename (marketmood_data) if that is the one that exists."""
    if not os.path.exists("stockproof_data") and os.path.isdir("marketmood_data"):
        return "marketmood_data"
    return "stockproof_data"


DATA_DIR = default_data_dir()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stockproof",
                                     description="Stock news read by a large language model.")
    parser.add_argument("--version", action="version", version=f"stockproof {__version__}")
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="fetch news, score it with an LLM, write a report")
    scan.add_argument("tickers", nargs="*", help="e.g. AAPL MSFT, or T=AT&T to give a company name")
    scan.add_argument("--watchlist", help="text file: one ticker per line (or ticker,name)")
    scan.add_argument("--provider", default="deepseek", choices=sorted(PROVIDERS))
    scan.add_argument("--model", help="model name (default: the provider's preset)")
    scan.add_argument("--base-url", help="custom OpenAI-compatible API address")
    scan.add_argument("--lang", default="en", choices=["en", "zh"], help="report and reason language")
    scan.add_argument("--per-ticker", type=int, default=20, help="headlines to fetch per stock")
    scan.add_argument("--days", type=int, default=7, help="only use news from the last N days")
    scan.add_argument("--min-relevance", type=float, default=0.5,
                      help="headlines below this relevance are shown but not counted")
    scan.add_argument("--min-sample", type=int, default=5,
                      help="flag moods based on fewer relevant headlines than this")
    scan.add_argument("--data-dir", default=DATA_DIR, help="where the database is kept")
    scan.add_argument("--report", default="stockproof_report.html", help="HTML report path")
    scan.add_argument("--no-report", action="store_true", help="skip the HTML report")
    scan.add_argument("--csv", help="also save headline-level data to this CSV file")
    scan.add_argument("--open", action="store_true", help="open the report in a browser")
    scan.set_defaults(func=cmd_scan)

    earn = sub.add_parser("earnings", help="read the latest earnings releases from SEC EDGAR")
    earn.add_argument("tickers", nargs="*", help="e.g. AAPL MSFT")
    earn.add_argument("--watchlist", help="text file: one ticker per line (or ticker,name)")
    earn.add_argument("--provider", default="deepseek", choices=sorted(PROVIDERS))
    earn.add_argument("--model", help="model name (default: the provider's preset)")
    earn.add_argument("--base-url", help="custom OpenAI-compatible API address")
    earn.add_argument("--lang", default="en", choices=["en", "zh"])
    earn.add_argument("--no-llm", action="store_true", help="only EPS history and SUE, no AI reading")
    earn.add_argument("--data-dir", default=DATA_DIR)
    earn.add_argument("--report", default="stockproof_earnings.html")
    earn.add_argument("--no-report", action="store_true")
    earn.add_argument("--csv", help="save quarterly EPS and SUE history to this CSV")
    earn.add_argument("--open", action="store_true", help="open the report in a browser")
    earn.set_defaults(func=cmd_earnings)

    dash = sub.add_parser("dashboard", help="open the interactive dashboard in your browser")
    dash.add_argument("tickers", nargs="*", help="stocks to start with (only if no saved watchlist)")
    dash.add_argument("--watchlist", help="text file to start the watchlist from")
    dash.add_argument("--replace", action="store_true", help="replace the saved watchlist")
    dash.add_argument("--provider", default="deepseek", choices=sorted(PROVIDERS))
    dash.add_argument("--model", help="model name (default: the provider's preset)")
    dash.add_argument("--base-url", help="custom OpenAI-compatible API address")
    dash.add_argument("--per-ticker", type=int, default=20)
    dash.add_argument("--days", type=int, default=7, help="news window for the mood")
    dash.add_argument("--data-dir", default=DATA_DIR)
    dash.add_argument("--port", type=int, default=8765)
    dash.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    dash.set_defaults(func=cmd_dashboard)

    res = sub.add_parser("research", help="test whether news mood / earnings surprise predict returns")
    res.add_argument("tickers", nargs="*", help="default: every stock in the price file")
    res.add_argument("--watchlist", help="text file: one ticker per line (or ticker,name)")
    res.add_argument("--prices", help="CSV of adjusted closes (Date + one column per ticker); "
                                      "default: <data-dir>/prices.csv (cn: prices_cn.csv)")
    res.add_argument("--download", action="store_true",
                     help="download prices first (US: yfinance; cn: AKShare, also done automatically if missing)")
    res.add_argument("--since", default="2016-01-01", help="first date of the earnings study")
    res.add_argument("--backfill", type=int, default=0, metavar="N",
                     help="read the last N past earnings releases / reports per stock with the LLM "
                          "(costs API credit; each document is read once)")
    res.add_argument("--offline", action="store_true", help="use only saved SEC files, no downloads")
    res.add_argument("--skip-earnings", action="store_true")
    res.add_argument("--skip-backtest", action="store_true")
    res.add_argument("--long-sue", type=float, default=2.0,
                     help="backtest: buy when SUE >= this (and short when <= minus this)")
    res.add_argument("--hold", type=int, default=60, help="backtest: trading days to hold")
    res.add_argument("--min-relevance", type=float, default=0.5)
    res.add_argument("--provider", default="deepseek", choices=sorted(PROVIDERS))
    res.add_argument("--model", help="model name (default: the provider's preset)")
    res.add_argument("--base-url", help="custom OpenAI-compatible API address")
    res.add_argument("--lang", default="en", choices=["en", "zh"])
    res.add_argument("--data-dir", default=DATA_DIR)
    res.add_argument("--benchmark", default="ew", choices=["ew", "index"],
                     help="ew: average of the stocks studied (default); index: SPY / CSI 300 column if present")
    res.add_argument("--market", default="us", choices=["us", "cn"],
                     help="us: SEC earnings study; cn: A-share study via AKShare")
    res.add_argument("--index", default="000300", help="with --market cn and no tickers: study this CSI index's members")
    res.add_argument("--report", help="default: stockproof_research.html (cn: stockproof_research_cn.html)")
    res.add_argument("--open", action="store_true", help="open the report in a browser")
    res.set_defaults(func=cmd_research)

    day = sub.add_parser("daily", help="one refresh of the dashboard watchlist (news + earnings)")
    day.add_argument("--provider", default="deepseek", choices=sorted(PROVIDERS))
    day.add_argument("--model", help="model name (default: the provider's preset)")
    day.add_argument("--base-url", help="custom OpenAI-compatible API address")
    day.add_argument("--lang", choices=["en", "zh"], help="default: the dashboard's language")
    day.add_argument("--skip-earnings", action="store_true")
    day.add_argument("--load-shell-env", action="store_true",
                     help="read API keys from your login shell (used by the scheduled job)")
    day.add_argument("--data-dir", default=DATA_DIR)
    day.set_defaults(func=cmd_daily)

    sch = sub.add_parser("schedule", help="run `daily` automatically every day (macOS)")
    sch.add_argument("--time", help="install the daily job at HH:MM (your computer's time)")
    sch.add_argument("--remove", action="store_true", help="remove the daily job")
    sch.add_argument("--run-now", action="store_true", help="start the installed job once, now")
    sch.add_argument("--provider", default="deepseek", choices=sorted(PROVIDERS))
    sch.add_argument("--skip-earnings", action="store_true")
    sch.add_argument("--data-dir", default=DATA_DIR)
    sch.set_defaults(func=cmd_schedule)

    calp = sub.add_parser("calendar", help="who reports earnings in the coming days")
    calp.add_argument("tickers", nargs="*", help="default: the dashboard watchlist")
    calp.add_argument("--watchlist", help="text file: one ticker per line")
    calp.add_argument("--days", type=int, default=14)
    calp.add_argument("--offline", action="store_true", help="show the saved calendar, no downloads")
    calp.add_argument("--data-dir", default=DATA_DIR)
    calp.set_defaults(func=cmd_calendar)

    mcpp = sub.add_parser("mcp", help="run as an MCP server for AI agents (DeepSeek Harness, Claude, Cursor...)")
    mcpp.add_argument("--dsh-config", action="store_true",
                      help="print (and save as stockproof.cordis.yml) a DeepSeek Harness entry for this computer")
    mcpp.add_argument("--install-dsh", action="store_true",
                      help="add stockproof to DeepSeek Harness on this computer (desktop app included)")
    mcpp.add_argument("--uninstall-dsh", action="store_true", help="remove it again")
    mcpp.add_argument("--load-shell-env", action="store_true",
                      help="read API keys from your login shell (for apps started from the Dock)")
    mcpp.add_argument("--auto-dashboard", action="store_true",
                      help="open the dashboard by itself the first time (or set STOCKPROOF_AUTO_DASHBOARD=1)")
    mcpp.add_argument("--provider", default="deepseek", choices=sorted(PROVIDERS))
    mcpp.add_argument("--model", help="model name (default: the provider's preset)")
    mcpp.add_argument("--base-url", help="custom OpenAI-compatible API address")
    mcpp.add_argument("--data-dir", default=DATA_DIR)
    mcpp.set_defaults(func=cmd_mcp)

    scr = sub.add_parser("screen", help="rank every A-share by earnings surprise, growth, ROE and momentum")
    scr.add_argument("--top", type=int, default=30)
    scr.add_argument("--min-cap", type=float, default=50.0, help="minimum market value, 亿元 (default 50)")
    scr.add_argument("--per-industry", type=int, default=3,
                     help="at most this many names per industry in the list (default 3; 0 = no limit)")
    scr.add_argument("--since", help="first report period to load (default: 4 years ago; 2015 with --backtest)")
    scr.add_argument("--backtest", action="store_true",
                     help="test the rule on history (CSI300 prices from `research --market cn`)")
    scr.add_argument("--skip-screen", action="store_true", help="with --backtest: only the backtest")
    scr.add_argument("--prices", help="CSV of adjusted closes for the backtest")
    scr.add_argument("--lang", default="zh", choices=["en", "zh"])
    scr.add_argument("--data-dir", default=DATA_DIR)
    scr.set_defaults(func=cmd_screen)

    scd = sub.add_parser("scorecard", help="evidence scorecard (0-100, with sources) for stocks or the screen's top")
    scd.add_argument("tickers", nargs="*", help="default: the top of the latest `stockproof screen`")
    scd.add_argument("--watchlist", help="text file: one ticker per line")
    scd.add_argument("--top", type=int, default=10, help="how many of the screen's list (default 10)")
    scd.add_argument("--no-refresh", action="store_true", help="use saved news / reports only (faster, cheaper)")
    scd.add_argument("--force", action="store_true", help="redo today's cards even if saved")
    scd.add_argument("--lang", default="zh", choices=["en", "zh"])
    scd.add_argument("--provider", default="deepseek", choices=sorted(PROVIDERS))
    scd.add_argument("--model", help="model name (default: the provider's preset)")
    scd.add_argument("--base-url", help="custom OpenAI-compatible API address")
    scd.add_argument("--data-dir", default=DATA_DIR)
    scd.set_defaults(func=cmd_scorecard)

    pol = sub.add_parser("policy", help="test whether 新闻联播 policy wording predicts industry returns")
    pol.add_argument("--since", default="2016-03-01")
    pol.add_argument("--workers", type=int, default=4)
    pol.add_argument("--max-days", type=int, help="read only the latest N days (a cheap trial)")
    pol.add_argument("--skip-download", action="store_true")
    pol.add_argument("--skip-read", action="store_true", help="use saved LLM readings only")
    pol.add_argument("--refresh-prices", action="store_true")
    pol.add_argument("--lang", default="zh", choices=["en", "zh"])
    pol.add_argument("--provider", default="deepseek", choices=sorted(PROVIDERS))
    pol.add_argument("--model", help="model name (default: the provider's preset)")
    pol.add_argument("--base-url", help="custom OpenAI-compatible API address")
    pol.add_argument("--data-dir", default=DATA_DIR)
    pol.set_defaults(func=cmd_policy)

    dem = sub.add_parser("demo", help="try the dashboard on bundled real data (offline, no API key)")
    dem.add_argument("--port", type=int, default=8765)
    dem.add_argument("--lang", choices=["en", "zh"], help="interface language (default: the demo's)")
    dem.add_argument("--no-browser", action="store_true")
    dem.set_defaults(func=cmd_demo)

    labp = sub.add_parser("lab", help="quant lab: backtest any idea with a locked holdout and multiple-testing guard")
    labp.add_argument("action", choices=["caps", "run", "confirm", "list", "similar", "reset"])
    labp.add_argument("arg", nargs="?", help="run: spec JSON or file · confirm: experiment id · similar: ticker")
    labp.add_argument("--open", action="store_true", help="open the report in the browser")
    labp.add_argument("--lang", default="zh", choices=["en", "zh"])
    labp.add_argument("--data-dir", default=DATA_DIR)
    labp.set_defaults(func=cmd_lab)

    pf = sub.add_parser("portfolio", help="portfolio check-up: concentration, overlap, risk, crash replays")
    pf.add_argument("holdings", help='"600519 100, AAPL 20" or a CSV / JSON file (ticker, shares|value|weight, cost)')
    pf.add_argument("--lang", default="zh", choices=["en", "zh"])
    pf.add_argument("--provider", default="deepseek", choices=sorted(PROVIDERS))
    pf.add_argument("--no-open", action="store_true")
    pf.add_argument("--data-dir", default=DATA_DIR)
    pf.set_defaults(func=cmd_portfolio)

    prov = sub.add_parser("providers", help="list built-in LLM providers")
    prov.set_defaults(func=cmd_providers)
    return parser


MENU = {
    "zh": [
        ("先试试", [("demo", "离线演示，内置真实数据，不需要 API key"),
                  ("dashboard", "打开网页看板：所有功能都在里面（首页有例子可以点）")]),
        ("日常看盘", [("scan AAPL 600519", "新闻情绪：AI 判断相关性和利好利空"),
                    ("earnings AAPL 600519", "财报解读 + 业绩惊喜 SUE"),
                    ("daily", "更新关注列表并生成每日简报"),
                    ("calendar", "未来两周谁发财报"),
                    ("schedule --time 21:00", "每晚自动更新（macOS）")]),
        ("选股与评分卡", [("screen", "全市场 A 股选股名单和理由"),
                      ("scorecard 600519", "证据评分卡：每个维度附出处和检验记录")]),
        ("研究与量化实验室", [("research --market cn", "财报事件研究和扣费回测"),
                        ("policy", "新闻联播政策信号研究"),
                        ("lab caps", "实验室：能检验哪些想法"),
                        ("lab run '<JSON>' --open", "回测任何想法（近两年锁定，多试会提高门槛）"),
                        ("lab list", "实验记录")]),
        ("持仓体检", [("portfolio \"600519 100, 00700 300\"", "集中度、同涨同跌、风险来源、大跌重演")]),
        ("AI 智能体", [("mcp --install-dsh", "装进 DeepSeek Harness，用中文直接问；输入 /stockproof 可选现成的问题")]),
    ],
    "en": [
        ("Start here", [("demo", "offline demo on bundled real data, no API key"),
                        ("dashboard", "the local web page with everything (the home tab has clickable examples)")]),
        ("Daily watching", [("scan AAPL 600519", "news mood: relevance and sentiment"),
                            ("earnings AAPL 600519", "earnings read by the LLM, with SUE"),
                            ("daily", "refresh the watchlist and write the daily digest"),
                            ("calendar", "who reports in the next two weeks"),
                            ("schedule --time 21:00", "run daily every evening (macOS)")]),
        ("Screen and scorecards", [("screen", "whole-market A-share shortlist with reasons"),
                                   ("scorecard 600519", "evidence scorecard with sources and track record")]),
        ("Research and the quant lab", [("research --market cn", "earnings event study and backtest"),
                                        ("policy", "新闻联播 policy-signal study"),
                                        ("lab caps", "what the lab can test"),
                                        ("lab run '<spec JSON>' --open", "backtest any idea (holdout locked, tries raise the bar)"),
                                        ("lab list", "the lab notebook")]),
        ("Portfolio check-up", [("portfolio \"AAPL 50, 00700 300\"", "concentration, overlap, risk sources, crash replays")]),
        ("AI agents", [("mcp --install-dsh", "add to DeepSeek Harness; ask in plain words, or type / for ready-made prompts")]),
    ],
}


def menu_lang(env=None) -> str:
    env = os.environ if env is None else env
    v = (env.get("STOCKPROOF_LANG") or env.get("LC_ALL") or env.get("LC_MESSAGES") or env.get("LANG") or "").lower()
    return "zh" if v.startswith("zh") else "en"


def menu_text(lang: str = "en") -> str:
    zh = lang == "zh"
    out = [f"stockproof {__version__}" + (" · 有据 — AI 读新闻、财报、公告，并用历史数据检验" if zh else " — "
                                            "LLM-read news, earnings and filings, checked against history"), ""]
    for group, rows in MENU["zh" if zh else "en"]:
        out.append(group)
        w = max(len(c) for c, _ in rows)
        out += [f"  stockproof {c.ljust(w)}  {d}" for c, d in rows]
        out.append("")
    out.append("每个命令加 -h 查看参数，例如 stockproof lab -h。全部命令：stockproof -h" if zh else
               "Add -h to any command for its options, e.g. stockproof lab -h. All commands: stockproof -h")
    return "\n".join(out)


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        print(menu_text(menu_lang()))
        sys.exit(0)
    sys.exit(args.func(args))
