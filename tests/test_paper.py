import datetime as dt
import sqlite3

import numpy as np
import pandas as pd
import pytest

from stockproof import paper
from stockproof.store import Store

DAYS = pd.bdate_range("2026-03-02", periods=40)


def _write(d, tk, opens, closes=None, volume=1e6):
    closes = opens if closes is None else closes
    df = pd.DataFrame({"open": opens, "high": np.maximum(opens, closes) * 1.01, "low": np.minimum(opens, closes) * 0.99,
                       "close": closes, "volume": volume}, index=DAYS[:len(opens)])
    (d / "quotes").mkdir(exist_ok=True)
    df.rename_axis("date").to_csv(d / "quotes" / (tk.replace("^", "_") + ".csv"))


@pytest.fixture
def env(tmp_path):
    flat = np.full(40, 10.0)
    _write(tmp_path, "600000.SH", flat)
    _write(tmp_path, "^CSI300", np.linspace(4000, 4400, 40))
    store = Store(str(tmp_path))
    aid = paper.create_account(store, "t", 100_000, start_day="2026-03-02")
    return tmp_path, store, aid


def at(day, hour=20):        # 20:00 Shanghai time on that day (after the close)
    return dt.datetime.fromisoformat(f"{day}T{hour:02d}:00:00+08:00")


def test_fills_next_open_with_costs(env):
    d, store, aid = env
    paper.place(store, aid, "600000.SH", "buy", shares=1050, now=at("2026-03-02"))
    r = paper.process(store, str(d), fetch=False)
    assert r["filled"] == 1
    o = paper.orders(store, aid).iloc[0]
    assert o["fill_day"] == "2026-03-03" and o["filled"] == 1000          # rounded down to a lot
    assert o["price"] > 10.0                                              # slippage against us
    assert o["cost"] == pytest.approx(5.0)                                # minimum commission


def test_limit_up_open_waits_then_cancels(tmp_path):
    opens = np.array([10.0] + [10.0 * 1.1 ** i for i in range(1, 40)])
    _write(tmp_path, "600000.SH", opens)                                  # opens at limit-up every day
    _write(tmp_path, "^CSI300", np.linspace(4000, 4400, 40))
    store = Store(str(tmp_path))
    aid = paper.create_account(store, "t", 1e9, start_day="2026-03-02")
    paper.place(store, aid, "600000.SH", "buy", shares=100, now=at("2026-03-02"))
    paper.process(store, str(tmp_path), fetch=False)
    o = paper.orders(store, aid).iloc[0]
    assert o["status"] == "cancelled" and "5" in o["reason"]


def test_volume_cap_and_t_plus_one(env):
    d, store, aid = env
    _write(d, "600000.SH", np.full(40, 10.0), volume=1000)               # 1000 lots = 100,000 shares a day
    paper.place(store, aid, "600000.SH", "buy", shares=8000, now=at("2026-03-02"))
    paper.place(store, aid, "600000.SH", "sell", shares=0, now=at("2026-03-02"))      # same day: nothing held yet
    paper.process(store, str(d), fetch=False)
    od = paper.orders(store, aid)
    buy, sell = od.iloc[0], od.iloc[1]
    assert buy["filled"] == 5000 and "volume cap" in buy["reason"]          # 5% of the day
    assert sell["status"] == "cancelled"


def test_append_only(env):
    d, store, aid = env
    paper.place(store, aid, "600000.SH", "buy", shares=100, now=at("2026-03-02"))
    for sql in ("UPDATE paper_orders SET shares=1", "DELETE FROM paper_orders", "UPDATE paper_accounts SET cash=1"):
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            store.conn.execute(sql)


def test_state_tracks_value_and_benchmark(env):
    d, store, aid = env
    paper.place(store, aid, "600000.SH", "buy", shares=1000, now=at("2026-03-02"))
    paper.process(store, str(d), fetch=False)
    s = paper.state(store, str(d), aid)
    assert s["holdings"][0]["shares"] == 1000
    assert s["return"] < 0                                                # flat price: costs only
    assert s["benchmark_return"] == pytest.approx(0.1, abs=1e-6)
    assert s["excess"] < -0.09 and s["nav"][0][0] == "2026-03-02"


def test_market_day_uses_exchange_time():
    # 20:00 in California on Mar 2 is already Mar 3 in Shanghai
    t = dt.datetime(2026, 3, 3, 4, 0, tzinfo=dt.timezone.utc)
    assert paper.market_day("600000.SH", t) == "2026-03-03"
    assert paper.market_day("AAPL", t) == "2026-03-02"


def test_strategy_account_enters_exits_and_reports_gap(env, monkeypatch):
    d, store, aid = env
    monkeypatch.setattr("stockproof.paper.strategy_events", lambda *a, **k: None)
    spec = {"type": "smart_money", "filters": [], "hold_days": 5, "slots": 2}
    sid = paper.create_account(store, "s", 100_000, "cn", "strategy", paper_spec(spec), start_day="2026-03-02")
    ev = pd.DataFrame({"ticker": ["600000.SH", "600000.SH"], "day0": pd.to_datetime(["2026-03-02", "2026-02-01"])})
    q = paper.step_strategy(store, str(d), sid, events=ev, now=at("2026-03-02"))
    assert q["buy"] == 1                                                  # the event before the start is ignored
    assert paper.step_strategy(store, str(d), sid, events=ev, now=at("2026-03-02"))["buy"] == 0   # no duplicates
    paper.process(store, str(d), fetch=False)
    q = paper.step_strategy(store, str(d), sid, events=ev, now=at("2026-03-11"))
    assert q["sell"] == 1
    paper.process(store, str(d), fetch=False)
    g = paper.gap(store, str(d), sid)
    assert g["round_trips"] == 1 and g["avg_gap"] < 0                      # paper fills cost more than the backtest rule


def paper_spec(spec):
    from stockproof import lab
    return lab.validate(spec)
