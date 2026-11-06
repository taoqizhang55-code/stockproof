import json

import numpy as np
import pandas as pd

from stockproof import lab, peers


def _setup(tmp_path):
    d = tmp_path / "data"
    (d / "cn").mkdir(parents=True)
    (d / "research").mkdir()
    days = pd.bdate_range("2026-09-01", "2026-10-30")
    cols = ["600519.SH", "000858.SZ", "000568.SZ", "600809.SH", "000001.SZ"]
    px = pd.DataFrame(100.0, index=days, columns=cols)
    last = {"600519.SH": -0.05, "000858.SZ": -0.04, "000568.SZ": -0.03, "600809.SH": 0.01, "000001.SZ": 0.02}
    for c, r in last.items():
        px.loc[days[-1], c] = 100 * (1 + r)
    px.to_csv(d / "prices_cn.csv")
    (d / "research" / "cn_meta.json").write_text(json.dumps({"prices_path": str(d / "prices_cn.csv")}))
    rows = [{"code": "600519", "name": "贵州茅台", "industry": "酿酒行业"},
            {"code": "000858", "name": "五粮液", "industry": "酿酒行业"},
            {"code": "000568", "name": "泸州老窖", "industry": "酿酒行业"},
            {"code": "600809", "name": "山西汾酒", "industry": "酿酒行业"},
            {"code": "000001", "name": "平安银行", "industry": "银行"}]
    (d / "cn" / "research_yjbb2_20260930.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    lab._CACHE.clear()
    return str(d), days[-1].date().isoformat()


def test_peers_offline_from_research_prices(tmp_path):
    d, day = _setup(tmp_path)
    p = peers.compare(d, "600519.SH", day, -0.05, fetch=False)
    assert p["industry"] == "酿酒行业" and p["n"] == 3
    assert [x["name"] for x in p["peers"]] == ["山西汾酒", "泸州老窖", "五粮液"]      # best first, no bank, no self
    assert abs(p["median"] - (-0.03)) < 1e-9 and p["down"] == 2 and p["up"] == 1
    assert p["rank"] == 4                                                            # worst of 4
    line = peers.prompt_line(p)
    assert "median -3.00%" in line or "median −3.00%" in line or "-3.0" in line
    assert peers.compare(d, "AAPL", day, 0.01, fetch=False) is None


def test_board_cache_orders_by_market_cap(tmp_path):
    d, day = _setup(tmp_path)
    board = [{"ticker": "000568.SZ", "name": "泸州老窖", "mcap": 2e11}, {"ticker": "600809.SH", "name": "山西汾酒", "mcap": 3e11},
             {"ticker": "000858.SZ", "name": "五粮液", "mcap": 5e11}]
    with open(f"{d}/cn/peers_酿酒行业.json", "w", encoding="utf-8") as f:
        json.dump(sorted(board, key=lambda x: -x["mcap"]), f, ensure_ascii=False)
    p = peers.compare(d, "600519.SH", day, -0.05, n=2, fetch=False)
    assert {x["name"] for x in p["peers"]} == {"五粮液", "山西汾酒"}


def test_explain_includes_peers_in_prompt():
    from stockproof import explain
    p = {"industry": "酿酒行业", "peers": [{"ticker": "000858.SZ", "name": "五粮液", "ret": -0.04}], "median": -0.04,
         "up": 0, "down": 1, "n": 1, "rank": 2}
    txt = explain.build_prompt("贵州茅台", "600519.SH", "2026-10-30", {"ret": -0.05, "market": -0.01, "excess": -0.04},
                               [], "zh", None, p)
    assert "Peers (酿酒行业" in txt and "五粮液" in txt and "ranks 2 of 2" in txt
