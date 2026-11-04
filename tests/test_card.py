import datetime as dt
import json

import numpy as np
import pandas as pd

from stockproof import card, lab, paper, team
from stockproof.store import Store


def _seed(d):
    (d / "quotes").mkdir()
    days = pd.bdate_range(end="2026-11-03", periods=120)
    for tk, base in (("002230.SZ", 10), ("_CSI300", 4000)):
        c = base + np.linspace(0, base * 0.05, 120)
        pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": 1e6}, index=days).rename_axis("date").to_csv(d / "quotes" / f"{tk}.csv")


def test_cards_render_with_checkable_ids(tmp_path):
    _seed(tmp_path)
    st = Store(str(tmp_path))
    st.conn.executescript(team.SCHEMA)
    res = {"ticker": "002230.SZ", "name": "科大讯飞", "day": "2026-10-01", "price": 10.3, "question": "<b>x</b>",
           "final": {"stance": "bearish", "confidence": "low", "horizon_days": 20, "summary": "摘要" * 80,
                     "plan": [{"if": "跌破", "level": 9.9, "then": "成立"}]}}
    st.conn.execute("INSERT INTO team_calls VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    ("c-1", "002230.SZ", "2026-10-01T10:00", "2026-10-01", 10.3, "bearish", "low", 20, "m", "zh",
                     json.dumps(res, ensure_ascii=False)))
    svg = card.team_card(st, str(tmp_path), "c-1")
    assert svg.startswith("<svg") and "c-1" in svg and "偏空" in svg and "<b>" not in svg and "不是投资建议" in svg
    aid = paper.create_account(st, "我的", 100000, start_day="2026-09-01")
    paper.place(st, aid, "002230.SZ", "buy", value=50000, now=dt.datetime(2026, 9, 1, 13, tzinfo=dt.timezone.utc))
    paper.process(st, str(tmp_path), fetch=False)
    svg = card.paper_card(st, str(tmp_path), aid)
    assert "沪深300" in svg and "只能追加" in svg
    (tmp_path / "lab").mkdir(exist_ok=True)
    lab._append(str(tmp_path), {"id": "e1", "hash": "h", "phase": "explore", "time": "2026-11-01T00:00",
                                "spec": lab.validate({"type": "earnings", "market": "cn", "filters": []}),
                                "t": 0.5, "ann": 0.01, "n": 10, "verdict": "no_edge"})
    assert "没有优势" in card.lab_card(str(tmp_path), "e1")
    assert card.render("team", "missing", st, str(tmp_path)) is None


def test_wrap_limits_lines():
    lines = card.wrap("很长" * 200, 20, 400, 3)
    assert len(lines) == 3 and lines[-1].endswith("…")
