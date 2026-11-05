import numpy as np
import pandas as pd

from stockproof import dayinfo
from stockproof.store import Store


def test_day_info(tmp_path):
    (tmp_path / "quotes").mkdir()
    days = pd.bdate_range("2026-01-05", periods=120)
    c = np.full(120, 10.0)
    c[80:] = 12.0                                               # a jump on day 80
    v = np.full(120, 1e6)
    v[80] = 5e6
    pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": v}, index=days) \
        .rename_axis("date").to_csv(tmp_path / "quotes" / "600000.SH.csv")
    b = np.full(120, 4000.0)
    pd.DataFrame({"open": b, "high": b, "low": b, "close": b, "volume": 1e6}, index=days) \
        .rename_axis("date").to_csv(tmp_path / "quotes" / "_CSI300.csv")
    r = dayinfo.day_info(Store(str(tmp_path)), str(tmp_path), "600000.SH", days[80].date().isoformat())
    assert r["ret"] == 0.2 and r["excess"] == 0.2 and r["unusual"]
    assert r["vol_ratio"] == 5.0 and any("放量" in f for f in r["facts"])
    assert r["after"]["5"] == 0.0 and "20" in r["after"]
    sat = (days[80] + pd.Timedelta(days=(5 - days[80].weekday()) % 7 or 7)).date().isoformat()
    assert dayinfo.day_info(Store(str(tmp_path)), str(tmp_path), "600000.SH", sat)["date"] <= sat
    assert "error" in dayinfo.day_info(Store(str(tmp_path)), str(tmp_path), "600000.SH", "2020-01-01")
