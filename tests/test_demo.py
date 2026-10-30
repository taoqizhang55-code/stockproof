import datetime as dt
import importlib.util
import json
import os

import pandas as pd

from stockproof import screener
from stockproof.store import Store

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _make_demo_module():
    spec = importlib.util.spec_from_file_location("make_demo", os.path.join(ROOT, "tools", "make_demo.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _source(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    store = Store(str(src))
    day = "2026-10-29"
    store.add_headlines("AAPL", [{"title": "Apple beats", "link": "https://x/a", "published": day, "source": "yahoo"}])
    store.add_headlines("MSFT", [{"title": "Not in the demo", "link": "https://x/m", "published": day, "source": "yahoo"}])
    hid = store.conn.execute("SELECT id FROM headlines WHERE ticker='AAPL'").fetchone()[0]
    store.save_score(hid, "deepseek:deepseek-chat", "zh", {"relevance": 0.9, "score": 0.5, "reason": "好"})
    screener.save(str(src), [{"ticker": "301308.SZ", "name": "江波龙", "rank": 1, "score": 99, "reasons": ["x"]}],
                  {"as_of": day, "screened": 2809, "top": 30, "per_industry": 3},
                  {"301308.SZ": {"rank": 1, "score": 99}, "600000.SH": {"rank": 2000, "score": 10}})
    (src / "screens" / "cn_backtest.json").write_text("{}")
    card = {"ticker": "301308.SZ", "name": "江波龙", "day": day, "overall": {"score": 90, "label": "positive",
            "label_text": "证据偏正面"}, "dimensions": [], "evidence": []}
    (src / "screens" / f"scorecards_{day}.json").write_text(json.dumps([card, {**card, "ticker": "TSLA"}]))
    (src / "quotes").mkdir()
    pd.DataFrame({"close": [1.0, 2.0]}, index=pd.to_datetime(["2026-10-28", "2026-10-29"])).to_csv(src / "quotes" / "AAPL.csv")
    (src / "policy").mkdir()
    (src / "policy" / "results.json").write_text("{}")
    return src


def test_make_demo_and_run(tmp_path, monkeypatch):
    src = _source(tmp_path)
    out = tmp_path / "bundle"
    _make_demo_module().main(["--data-dir", str(src), "--tickers", "AAPL", "000898", "--out", str(out)])
    meta = json.loads((out / "demo.json").read_text(encoding="utf-8"))
    assert meta["watchlist"] == ["AAPL", "000898.SZ"]
    assert (out / "quotes" / "AAPL.csv").exists() and (out / "policy" / "results.json").exists()
    # only the chosen stocks' rows are copied
    import sqlite3
    con = sqlite3.connect(out / "stockproof.db")
    assert [r[0] for r in con.execute("SELECT ticker FROM headlines")] == ["AAPL"]
    assert con.execute("SELECT COUNT(*) FROM scores").fetchone()[0] == 1
    cards = json.loads(next((out / "screens").glob("scorecards_*.json")).read_text(encoding="utf-8"))
    assert [c["ticker"] for c in cards] == ["301308.SZ"]          # screen's list kept, unrelated cards dropped
    screen = json.loads(next((out / "screens").glob("cn_2*.json")).read_text(encoding="utf-8"))
    assert set(screen["all"]) == {"301308.SZ"}

    from stockproof import demo
    monkeypatch.setattr(demo, "BUNDLE", str(out))
    monkeypatch.delenv("STOCKPROOF_TODAY", raising=False)
    app = demo.make_app("zh", target=str(tmp_path / "run"))
    try:
        from stockproof import clock
        assert clock.today() == dt.date.fromisoformat(meta["as_of"])
        st = app.state()
        assert st["demo"]["as_of"] == meta["as_of"] and st["watchlist"] == ["AAPL", "000898.SZ"]
        assert app.start_refresh("news") == (False, "demo")
        assert app.screen_page("zh")["cards"]["301308.SZ"]["score"] == 90     # saved cards, any date
        assert app.scorecard("301308.SZ", "zh")["name"] == "江波龙"
        assert app.compare_reports("AAPL", "zh") == {"error": "demo"}
        # the bundle itself is untouched by edits in the running demo
        app.set_watchlist(["AAPL"])
        assert json.loads((out / "dashboard.json").read_text(encoding="utf-8"))["watchlist"] == ["AAPL", "000898.SZ"]
    finally:
        os.environ.pop("STOCKPROOF_TODAY", None)
