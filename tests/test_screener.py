import numpy as np
import pandas as pd

from marketmood import screener as sc


def _tables(codes, years=range(2018, 2024), growth=None):
    """Fake 业绩报表 / 预约披露 / 快报 tables: YTD EPS that grows by `growth[code]` per quarter."""
    rng = np.random.default_rng(0)
    tables = {}
    for y in years:
        for m, md, pub in ((3, "0331", "04-25"), (6, "0630", "08-25"), (9, "0930", "10-25"), (12, "1231", "04-20")):
            date = f"{y}{md}"
            pub_year = y + 1 if m == 12 else y
            full, actual = [], []
            for i, c in enumerate(codes):
                g = (growth or {}).get(c, 0.0)
                q_eps = 0.2 + g * ((y - 2018) * 4 + m // 3) + rng.normal(0, 0.01)
                ytd = q_eps * (m // 3)
                full.append({"code": c, "name": f"股票{i}", "eps": ytd, "rev_yoy": 10 * g * 100 + i,
                             "np_yoy": 20 * g * 100 + i, "roe": 2.0 * (m // 3) + g * 100, "gm": 30.0,
                             "industry": "测试", "date": f"{pub_year}-{pub}"})
                actual.append({"code": c, "date": f"{pub_year}-{pub}"})
            tables[("yjbb2", date)] = full
            tables[("yysj", date)] = actual
            tables[("yjkb", date)] = []
    return tables


def test_panel_decumulates_and_sue():
    codes = ["600001", "600002"]
    pan = sc.panel(None, "2018-01-01", log=lambda *a: None, tables=_tables(codes, growth={"600001": 0.01}))
    a = pan[pan["code"] == "600001"].set_index("end")
    # single-quarter EPS is recovered from YTD figures
    q2 = a.loc[pd.Timestamp("2019-06-30"), "eps_q"]
    assert abs(q2 - (0.2 + 0.01 * 6)) < 0.05
    # steady growth -> positive changes and a SUE once enough history exists
    assert a["sue"].dropna().gt(0).mean() > 0.8
    assert pd.isna(a.loc[pd.Timestamp("2018-03-31"), "sue"])
    # Q4 becomes public in April of the next year
    assert a.loc[pd.Timestamp("2019-12-31"), "public"] == pd.Timestamp("2020-04-20")


def test_latest_known_is_point_in_time():
    pan = sc.panel(None, "2018-01-01", log=lambda *a: None, tables=_tables(["600001"]))
    k = sc.latest_known(pan, "2021-08-01")
    assert k.iloc[0]["end"] == pd.Timestamp("2021-03-31")       # H1 not public until Aug 25
    k = sc.latest_known(pan, "2021-09-01")
    assert k.iloc[0]["end"] == pd.Timestamp("2021-06-30")


def test_screen_filters_and_ranks():
    codes = [f"6000{i:02d}" for i in range(20)]
    growth = {c: 0.002 * i for i, c in enumerate(codes)}
    pan = sc.panel(None, "2018-01-01", log=lambda *a: None, tables=_tables(codes, growth=growth))
    snap = pd.DataFrame({"code": codes, "name": [f"股票{i}" for i in range(20)], "price": 10.0,
                         "mom60": np.linspace(-0.1, 0.3, 20), "ytd": 0.0, "cap": 100.0, "pe": 20.0, "pb": 2.0})
    snap.loc[3, "name"] = "*ST测试"
    snap.loc[4, "cap"] = 10.0
    out = sc.screen(pan, snap, as_of="2023-11-06", top=5)
    assert len(out) == 5
    assert "600003" not in set(out["code"]) and "600004" not in set(out["code"])
    assert out.iloc[0]["code"] in {"600018", "600019"}            # best on (almost) every factor
    assert out["score"].is_monotonic_decreasing
    assert out.iloc[0]["ticker"] == out.iloc[0]["code"] + ".SH"
    rs = sc.reasons(out.iloc[0], "zh")
    assert rs and "前" in rs[0]
    recs = sc.to_records(out)
    assert recs[0]["reasons"] and isinstance(recs[0]["score"], float)


def test_single_factor_score_keeps_rows():
    df = pd.DataFrame({"sue": np.arange(20.0), "mom60": np.nan})
    out = sc.score(df, ["sue"])
    assert len(out) == 20 and out["score"].max() == 100


def test_backtest_finds_a_planted_signal():
    codes = [f"6000{i:02d}" for i in range(40)]
    growth = {c: 0.002 * i for i, c in enumerate(codes)}
    pan = sc.panel(None, "2018-01-01", log=lambda *a: None, tables=_tables(codes, growth=growth))
    days = pd.bdate_range("2018-06-01", "2023-12-29")
    rng = np.random.default_rng(1)
    # stocks with faster earnings growth also rise faster
    drift = np.array([0.0002 * i for i in range(40)])
    rets = rng.normal(0, 0.01, (len(days), 40)) + drift
    px = pd.DataFrame(100 * np.cumprod(1 + rets, axis=0), index=days, columns=[c + ".SH" for c in codes])
    r = sc.backtest(pan, px, top=10, start="2019-01-01")
    assert r["n"] >= 10
    assert r["ann_excess"] > 0.05 and r["t"] > 2
    assert 0 <= r["hit_rate"] <= 1 and r["max_dd"] <= 0
    tests = sc.factor_test(pan, px, top=10)
    assert len(tests) == 1 + len(sc.FACTORS)


def test_checkpoints():
    pts = sc.checkpoints("2020-01-01", "2020-12-31")
    assert [p.month for p in pts] == [5, 9, 11]



def test_cli_screen_offline(tmp_path, monkeypatch, capsys):
    from marketmood import cli
    codes = [f"6000{i:02d}" for i in range(20)]
    pan = sc.panel(None, "2018-01-01", log=lambda *a: None,
                   tables=_tables(codes, years=range(2022, 2027), growth={c: 0.002 * i for i, c in enumerate(codes)}))
    snap = pd.DataFrame({"code": codes, "name": [f"股票{i}" for i in range(20)], "price": 10.0,
                         "mom60": np.linspace(-0.1, 0.3, 20), "ytd": 0.0, "cap": 100.0, "pe": 20.0, "pb": 2.0})
    real_screen = sc.screen
    monkeypatch.setattr(sc, "panel", lambda cache, since: pan)
    monkeypatch.setattr(sc, "snapshot", lambda cache: snap)
    monkeypatch.setattr(sc, "screen", lambda p, s, top, min_cap, **kw: real_screen(p, s, "2026-11-06", top, min_cap, **kw))

    try:
        cli.main(["screen", "--top", "5", "--per-industry", "0", "--data-dir", str(tmp_path)])
    except SystemExit as e:
        assert e.code == 0
    assert "不是买卖建议" in capsys.readouterr().out
    (tmp_path / "screens" / "cn_backtest.json").write_text("{}")     # must not be taken for a screen
    saved = sc.load_latest(str(tmp_path))
    assert len(saved["results"]) == 5 and saved["results"][0]["reasons"]
    assert len(saved["all"]) >= 19
    hit = sc.lookup(str(tmp_path), "600010")
    assert hit["covered"] and 1 <= hit["rank"] <= hit["of"]
    assert not sc.lookup(str(tmp_path), "00700.HK")["covered"]
    assert not sc.lookup(str(tmp_path), "AAPL")["covered"]
    assert not sc.lookup(str(tmp_path), "601999")["covered"]



class _R:
    def __init__(self, d):
        self.d = d
        self.text = "null" if d is None else "x"

    def json(self):
        return self.d


def test_snapshot_pages(tmp_path, monkeypatch):
    from marketmood import cn
    pages = {1: [{"f12": "600519", "f14": "贵州茅台", "f2": 1500.0, "f24": 5.0, "f25": -2.0, "f20": 1.9e12,
                  "f9": 22.0, "f23": 7.0}],
             2: [{"f12": "000001", "f14": "平安银行", "f2": "-", "f24": "-", "f25": "-", "f20": "-",
                  "f9": "-", "f23": "-"}]}
    calls = []

    def fake(url, params, headers, tries=3, gap=0.6):
        calls.append((url.split("/")[2], params["pn"]))
        if "82." not in url:
            raise ConnectionError("502 Bad Gateway")              # first host down -> next host
        return _R({"data": {"total": 2, "diff": pages.get(params["pn"], [])}})

    monkeypatch.setattr(sc, "_get", fake)
    df = sc.snapshot(cn.CNCache(str(tmp_path)), log=lambda *a: None)
    assert calls[0][0] == "push2.eastmoney.com" and calls[-1] == ("82.push2.eastmoney.com", 2)
    assert list(df["code"]) == ["600519"]                      # suspended stock (no price) dropped
    r = df.iloc[0]
    assert abs(r["mom60"] - 0.05) < 1e-9 and abs(r["cap"] - 19000) < 1e-6


def test_snapshot_falls_back_to_sina(tmp_path, monkeypatch):
    from marketmood import cn
    boards = {"sh_a": [{"code": "600519", "name": "贵州茅台", "trade": "1500.00", "per": 22.1, "pb": 7.0, "mktcap": 1.9e8},
                       {"code": "600000", "name": "浦发银行", "trade": "0.000", "per": 5, "pb": 0.5, "mktcap": 3e7}],
              "sz_a": [{"code": "000001", "name": "平安银行", "trade": "11.0", "per": 5, "pb": 0.5, "mktcap": 2e7}],
              "bj_a": []}
    hiccup = {"n": 0}

    def fake(url, params, headers, tries=3, gap=0.6):
        if "eastmoney" in url:
            raise ConnectionError("down")
        rows = boards[params["node"]]
        if "Count" in url:
            return _R(str(len(rows)))
        if params["node"] == "sz_a" and hiccup["n"] == 0:      # Sina throttles once: wait and retry
            hiccup["n"] += 1
            return _R(None)
        return _R(rows if params["page"] == 1 else [])

    monkeypatch.setattr(sc, "_get", fake)
    monkeypatch.setattr(sc.time, "sleep", lambda s: None)
    df = sc.snapshot(cn.CNCache(str(tmp_path)), log=lambda *a: None)
    assert sorted(df["code"]) == ["000001", "600519"]          # price 0 = suspended; SZ kept after the retry
    m = df.set_index("code").loc["600519"]
    assert abs(m["cap"] - 19000) < 1e-6 and pd.isna(m["mom60"])


def test_sina_gives_up_instead_of_returning_half(monkeypatch):
    def fake(url, params, headers, tries=3, gap=0.6):
        if "Count" in url:
            return _R("500")
        return _R(None)

    monkeypatch.setattr(sc, "_get", fake)
    monkeypatch.setattr(sc.time, "sleep", lambda s: None)
    import pytest
    with pytest.raises(sc.Incomplete):
        sc._sina_pages(log=lambda *a: None)


def test_growth_from_a_loss_is_ignored():
    df = pd.DataFrame({"code": ["1", "1"], "end": pd.to_datetime(["2025-09-30", "2026-09-30"]),
                       "eps": [-0.5, -0.1], "roe": [-3.0, -1.0], "np_yoy": [None, 80.0]})
    out = sc.add_sue(df)
    assert out["np_yoy"].isna().all() and out["roe_ann"].isna().all()


def test_screen_skips_new_listings_and_caps_industries():
    codes = [f"6000{i:02d}" for i in range(20)]
    growth = {c: 0.002 * i for i, c in enumerate(codes)}
    t = _tables(codes, growth=growth)
    for (kind, date), rows in t.items():                 # 600019 listed only in 2023: older periods come
        if kind == "yysj" and date < "20230101":         # from its prospectus, outside the disclosure schedule
            t[(kind, date)] = [r for r in rows if r["code"] != "600019"]
    for (kind, date), rows in t.items():                 # two industries
        if kind == "yjbb2":
            for r in rows:
                r["industry"] = "半导体" if int(r["code"]) % 2 else "银行"
    pan = sc.panel(None, "2018-01-01", log=lambda *a: None, tables=t)
    snap = pd.DataFrame({"code": codes, "name": [f"股票{i}" for i in range(20)], "price": 10.0,
                         "mom60": np.linspace(-0.1, 0.3, 20), "ytd": 0.0, "cap": 100.0, "pe": 20.0, "pb": 2.0})
    full = sc.screen(pan, snap, as_of="2023-11-06", top=None)
    assert "600019" not in set(full["code"])             # 4 reports < 8
    out = sc.screen(pan, snap, as_of="2023-11-06", top=6, per_industry=2)
    assert len(out) == 4 and out["industry"].value_counts().max() == 2
    assert out["rank"].iloc[0] == 1


def test_huge_growth_is_shown_capped():
    row = pd.Series({"np_yoy": 71529.0, "p_np_yoy": 100.0, "rev_yoy": 50.0, "p_rev_yoy": 90.0})
    assert "超过 +1000%" in sc.reasons(row, "zh")[0]
