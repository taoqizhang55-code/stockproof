"""Daily digest from saved data; the LLM only writes the opening, from the listed items."""

import datetime as dt
import json

import test_moves as tm
from stockproof import announcements, digest
from stockproof.dashboard import Dashboard


def test_digest_sections_and_opening(tmp_path):
    days = tm.setup_prices(tmp_path, jump_day=-1)                  # unusual move today
    d = str(tmp_path)
    app = Dashboard(d, "deepseek", None, None)
    app.set_watchlist(["300750"])
    store = app._store()
    announcements.ensure_schema(store)
    today = dt.date.today().isoformat()
    store.conn.execute("INSERT INTO announcements VALUES (?,?,?,?,?,?,?,?,?)",
                       ("A1", "300750.SZ", today, "宁德时代:关于收到深圳证券交易所问询函的公告", "regulatory_letter",
                        3, -1, "https://x/A1", "x"))
    store.conn.commit()
    seen = []

    class FakeClient:
        model = "m"
        def chat_json(self, prompt):
            seen.append(prompt)
            if "daily digest" in prompt:
                return {"text": "宁德时代异动 [1]，并收到问询函 [2]。"}
            return {"summary": "原因不明。", "causes": [], "confidence": "low", "explained": False}

    out = digest.build(app, "zh", FakeClient(), "p:m")
    data = out["data"]
    assert [m["ticker"] for m in data["moves"]] == ["300750.SZ"] and data["moves"][0]["why"] == "原因不明。"
    assert [a["art_code"] for a in data["anns"]] == ["A1"]
    assert "问询函" in seen[-1] and "ONLY facts" in seen[-1]
    page = open(out["path"], encoding="utf-8").read()
    assert "今日要点" in page and "问询函" in page and "异动" in page
    assert out["summary"].startswith("1 只异动")
    assert digest.list_dates(d) == [today]
    # without an LLM key it still works, just without the opening and explanations
    out2 = digest.build(app, "en", None, None)
    assert out2["text"] is None and "Unusual moves" in open(out2["path"], encoding="utf-8").read()
