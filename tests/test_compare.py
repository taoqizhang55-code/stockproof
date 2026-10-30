"""Report-to-report comparison: document picking, validation, caching. Fakes only."""

import pytest

from stockproof import cn, compare
from stockproof.store import Store


def test_cn_docs_pick_latest_two_results_documents(monkeypatch):
    items = [
        {"art_code": "Q3", "title": "宁德时代:2026年三季度报告", "date": "2026-10-21", "column": "", "name": ""},
        {"art_code": "X", "title": "宁德时代:关于召开2026年三季度业绩说明会的公告", "date": "2026-10-20", "column": "", "name": ""},
        {"art_code": "H1S", "title": "宁德时代:2026年半年度报告摘要", "date": "2026-07-30", "column": "", "name": ""},
        {"art_code": "H1", "title": "宁德时代:2026年半年度报告", "date": "2026-07-30", "column": "", "name": ""},
        {"art_code": "F", "title": "宁德时代:2026年前三季度业绩预告", "date": "2026-10-10", "column": "", "name": ""},
        {"art_code": "Q1", "title": "宁德时代:2026年一季度报告", "date": "2026-04-20", "column": "", "name": ""},
    ]
    monkeypatch.setattr(cn, "announcements", lambda info, page_size=50, page_index=1: items)
    docs = compare._cn_docs(cn.parse("300750"))
    assert [d["id"] for d in docs] == ["Q3", "H1S"]


def test_compare_validates_and_caches(tmp_path):
    calls = []

    class FakeClient:
        model = "m"
        def chat_json(self, prompt):
            calls.append(prompt)
            return {"headline": "毛利率回升", "tone_shift": 3,
                    "changes": [{"area": "results", "before": "毛利率 22%", "now": "毛利率 25%", "direction": "better"},
                                {"area": "weird", "before": "", "now": "x", "direction": "up"}],
                    "new_risks": ["海外关税"]}

    docs = lambda: [{"id": "B", "date": "2026-10-21", "title": "Q3", "fetch": lambda: ("本期毛利率25%", "https://b")},
                    {"id": "A", "date": "2026-07-30", "title": "H1", "fetch": lambda: ("上期毛利率22%", "https://a")}]
    store = Store(str(tmp_path))
    out = compare.compare(store, FakeClient(), "p:m", "300750.SZ", "宁德时代", "zh", docs=docs())
    assert out["tone_shift"] == 1.0                                  # clipped
    assert out["changes"][1] == {"area": "other", "before": "", "now": "x", "direction": "neutral"}
    assert out["prev"]["url"] == "https://a" and out["now"]["date"] == "2026-10-21"
    assert "PREVIOUS (2026-07-30" in calls[0] and "LATEST (2026-10-21" in calls[0]
    again = compare.compare(store, FakeClient(), "p:m", "300750.SZ", "宁德时代", "zh", docs=docs())
    assert len(calls) == 1 and again["headline"] == "毛利率回升"
    with pytest.raises(compare.NotEnough):
        compare.compare(store, FakeClient(), "p:m", "X", "x", "zh", docs=docs()[:1])
