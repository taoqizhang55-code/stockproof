import datetime as dt
import xml.dom.minidom

import numpy as np
import pandas as pd

from stockproof import chart_svg


def test_svg_chart_is_valid_and_complete():
    days = pd.bdate_range(end=dt.date.today(), periods=260)
    t = np.arange(260)
    c = 40 + 3 * np.sin(2 * np.pi * t / 50)
    o = np.append(c[0], c[:-1])
    b = pd.DataFrame({"close": c, "open": o, "high": np.maximum(o, c) * 1.01, "low": np.minimum(o, c) * 0.99,
                      "volume": 1e7}, index=days)
    svg = chart_svg.render(b, "002230.SZ", "科大讯飞", "zh")
    xml.dom.minidom.parseString(svg)                       # well-formed
    assert "科大讯飞 (002230.SZ)" in svg and "支撑" in svg and "MA20" in svg and "成交量" in svg
    assert "#d9363e" in svg and "#1f9d55" in svg            # red up / green down in Chinese
    assert "Support" in chart_svg.render(b, "002230.SZ", "", "en") or "Resistance" in chart_svg.render(b, "002230.SZ", "", "en")
    assert "not enough" in chart_svg.render(b.iloc[:5], "X", "", "en")
