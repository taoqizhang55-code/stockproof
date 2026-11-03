import numpy as np
import pandas as pd

from stockproof import quotes, ta


def make_bars(closes, vol=None):
    idx = pd.bdate_range("2025-01-01", periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"close": c, "open": c.shift().fillna(c), "high": c * 1.005, "low": c * 0.995,
                         "volume": vol if vol is not None else np.full(len(c), 1e6)}, index=idx)[quotes.COLS]


def ranging_then_breakout():
    # oscillate between ~10 and ~11 four times, then break out above 11 on big volume
    wave = np.concatenate([np.linspace(10, 11, 10), np.linspace(11, 10, 10)] * 4)
    up = np.linspace(10.2, 11.6, 8)
    closes = np.concatenate([wave, up])
    vol = np.full(len(closes), 1e6)
    vol[-3] = 3e6                                          # the day it closes above ~11.06
    return make_bars(closes, vol)


def test_indicators_and_trend():
    b = make_bars(np.linspace(10, 20, 120))
    ind = ta.indicators(b)
    assert abs(ind["ma5"].iloc[-1] - np.mean(np.linspace(10, 20, 120)[-5:])) < 1e-9
    assert ind["rsi"].iloc[-1] > 70 and ta.trend(ind)["state"] == "up"


def test_zones_find_support_and_resistance():
    b = ranging_then_breakout().iloc[:-8]                 # still inside the range
    zs = ta.zones(b)
    mids = sorted(z["mid"] for z in zs)
    assert any(abs(m - 10) < 0.15 for m in mids) and any(abs(m - 11) < 0.15 for m in mids)
    assert all(z["touches"] >= 2 for z in zs)


def test_breakout_signal_with_volume():
    b = ranging_then_breakout()
    sig = ta.signals(b, days=8)
    kinds = {s["kind"] for s in sig}
    assert "breakout" in kinds
    a = ta.analyze(b)
    assert a["signals"] and all("rule" in s for s in a["signals"])
    assert a["nearest_support"] is not None


def test_close_only_history_still_works():
    b = make_bars(np.linspace(10, 12, 80))
    b[["open", "high", "low", "volume"]] = np.nan
    a = ta.analyze(b)
    assert not a["has_ohlc"] and a["trend"]["state"] == "up"
    cd = ta.chart_data(b)
    assert len(cd["dates"]) == 80 and cd["high"][0] is None


def test_bars_parsing_and_upgrade_of_old_files(tmp_path, monkeypatch):
    df = pd.DataFrame({"日期": ["2026-10-29", "2026-10-30"], "开盘": [1, 2], "最高": [2, 3], "最低": [0.5, 1.5],
                       "收盘": [1.5, 2.5], "成交量": [100, 200]})
    b = quotes._std(df)
    assert list(b.columns) == quotes.COLS and b["high"].iloc[-1] == 3
    nas = pd.DataFrame({"date": pd.to_datetime(["2026-10-30"]), "close": ["$1,234.5"], "open": ["$1,200"],
                        "high": ["$1,240"], "low": ["$1,190"], "volume": ["1,000"]})
    assert quotes._std(nas)["close"].iloc[0] == 1234.5
    # an old close-only file is re-downloaded with full bars once
    p = tmp_path / "quotes"
    p.mkdir()
    pd.DataFrame({"close": [1.0, 2.0]}, index=pd.to_datetime(["2026-10-28", "2026-10-29"])).to_csv(p / "AAPL.csv")
    calls = []

    def fake(t, start):
        calls.append(start)
        return b
    monkeypatch.setattr(quotes, "download_bars", fake)
    quotes.update(str(tmp_path), "AAPL")
    saved = quotes.load_bars(str(tmp_path), "AAPL")
    assert saved["high"].notna().all() and len(calls) == 1
    assert quotes.load(str(tmp_path), "AAPL").iloc[-1] == 2.5


def test_crash_day_is_not_a_pullback_and_extremes_are_neutral():
    wave = np.concatenate([np.linspace(10, 11, 10), np.linspace(11, 10, 10)] * 4)
    closes = np.concatenate([wave, np.linspace(10.2, 11.8, 9), [10.6]])      # breakout, then a crash day
    sig = ta.signals(make_bars(closes), days=1)
    kinds = {s["kind"] for s in sig}
    assert "pullback" not in kinds
    assert all(s["direction"] == "neutral" for s in sig if s["kind"] in ("boll_low", "rsi_low", "volume_spike"))


def test_falling_price_below_ma20_is_not_called_uptrend():
    closes = np.concatenate([np.linspace(10, 20, 100), [17.5, 17.0]])
    ind = ta.indicators(make_bars(closes))
    assert ta.trend(ind)["state"] != "up"


def test_text_chart_draws_candles_zones_and_last_close():
    import datetime as dt
    import numpy as np
    import pandas as pd
    from stockproof import ta
    days = pd.bdate_range(end=dt.date.today(), periods=200)
    t = np.arange(200)
    c = 10.5 + 0.5 * np.sin(2 * np.pi * t / 24)
    c[-1] = 11.6
    b = pd.DataFrame({"close": c, "open": np.append(c[0], c[:-1]), "high": c * 1.01, "low": c * 0.99, "volume": 1e6},
                     index=days)
    txt = ta.text_chart(b, lang="zh")
    lines = txt.splitlines()
    assert "< 11.60" in lines[0]                       # the last close is the top of the chart here
    assert "#" in txt and "o" in txt and "-" in txt and "支撑" in txt
    body = "\n".join(l.split("  ")[0] for l in lines[:-2])   # the drawing itself, without labels
    assert all(ord(ch) < 128 for ch in body.replace("支撑", "").replace("阻力", ""))
    assert days[-1].date().isoformat() in txt
    assert "up day" in ta.text_chart(b, lang="en")
    assert ta.text_chart(b.iloc[:5]) == ""


def test_update_redownloads_when_volume_units_differ(tmp_path, monkeypatch):
    import datetime as dt
    import pandas as pd
    from stockproof import quotes
    days = pd.bdate_range(end=dt.date.today(), periods=30)
    old = pd.DataFrame({"close": 10.0, "open": 10.0, "high": 10.1, "low": 9.9, "volume": 1e6}, index=days)
    old.iloc[-3:, old.columns.get_loc("volume")] = 1e8          # last rows saved in shares by a fallback
    p = tmp_path / "quotes"
    p.mkdir()
    old.rename_axis("date").to_csv(p / "600000.SH.csv")
    calls = []

    def fake(tk, start):
        calls.append(start)
        return pd.DataFrame({"close": 10.0, "open": 10.0, "high": 10.1, "low": 9.9, "volume": 1e6},
                            index=days[days >= pd.Timestamp(start)] if len(calls) == 1 else days)
    monkeypatch.setattr(quotes, "download_bars", fake)
    quotes.update(str(tmp_path), "600000.SH")
    assert len(calls) == 2                                      # mismatch spotted -> full re-download
    assert quotes.load_bars(str(tmp_path), "600000.SH")["volume"].max() == 1e6
