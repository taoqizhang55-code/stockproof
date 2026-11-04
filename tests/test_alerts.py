import json

import numpy as np
import pandas as pd
import pytest

from stockproof import alerts, ta, team
from stockproof.store import Store


@pytest.fixture
def env(tmp_path):
    days = pd.bdate_range(end=pd.Timestamp.today().normalize() - pd.Timedelta(days=3), periods=200)
    c = 10 + np.sin(np.arange(200) / 6)
    df = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1e6}, index=days)
    (tmp_path / "quotes").mkdir()
    df.rename_axis("date").to_csv(tmp_path / "quotes" / "600000.SH.csv")
    return tmp_path, Store(str(tmp_path)), df


def test_zone_break_alert_once(env):
    d, store, df = env
    zs = [z for z in ta.zones(df) if z["kind"] == "resistance"] or ta.zones(df)
    top = max(z["high"] for z in zs)
    live = {"600000.SH": {"price": top * 1.05, "prev_close": float(df["close"].iloc[-1])}}
    new = alerts.check(store, str(d), ["600000.SH"], live)
    assert any(a["kind"] == "zone_up" for a in new)
    assert alerts.check(store, str(d), ["600000.SH"], live) == []            # recorded once
    with pytest.raises(Exception, match="append-only"):
        store.conn.execute("DELETE FROM alerts")


def test_team_plan_level(env):
    d, store, df = env
    store.conn.executescript(team.SCHEMA)
    res = {"final": {"plan": [{"if": "跌破支撑", "level": 8.5, "then": "看空成立"}]}}
    store.conn.execute("INSERT INTO team_calls VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       ("c1", "600000.SH", pd.Timestamp.now().isoformat(), pd.Timestamp.today().date().isoformat(), 10,
                        "bearish", "low", 20, "m", "zh", json.dumps(res, ensure_ascii=False)))
    live = {"600000.SH": {"price": 8.4, "prev_close": 9.0}}
    new = alerts.check(store, str(d), ["600000.SH"], live)
    assert any(a["kind"] == "team_level" and "8.5" in a["text"] for a in new)


def test_parse_sina():
    text = ('var hq_str_sh600000="浦发银行,10.0,9.9,10.2,10.3,9.8,10.2,10.21,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,'
            '2026-11-04,10:30:00,00";\nvar hq_str_gb_aapl="苹果,230.5,1.2,2026-11-04 10:30:00' + ",0" * 22 + ',227.8";')
    out = alerts.parse_sina(text, {"sh600000": "600000.SH", "gb_aapl": "AAPL"})
    assert out["600000.SH"]["price"] == 10.2 and out["600000.SH"]["prev_close"] == 9.9
    assert out["AAPL"]["price"] == 230.5 and out["AAPL"]["prev_close"] == 227.8


def test_market_open():
    import datetime as dt
    t = dt.datetime(2026, 11, 4, 2, 0, tzinfo=dt.timezone.utc)                # 10:00 Shanghai, Wednesday
    assert alerts.market_open(t) == {"cn": True, "us": False}
