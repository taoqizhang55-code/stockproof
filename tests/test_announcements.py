"""Announcement rules on real A-share titles (collected from Eastmoney, CSI 300, 2025-2026)."""

import pytest

from stockproof import announcements as an
from stockproof.store import Store

CASES = [
    ("中微公司:大股东大宗交易减持股份计划公告", "insider_selling", 3),
    ("江波龙:关于董事、高级管理人员减持股份预披露公告", "insider_selling", 3),
    ("川投能源:四川川投能源股份有限公司关于控股股东增持股份计划公告", "insider_buying", 2),
    ("汇川技术:关于回购公司股份的进展公告", "buyback", 2),
    ("ST华通:关于公司相关人员收到浙江证监局警示函的公告", "regulatory_letter", 3),
    ("五粮液:关于董事长被留置的公告", "investigation", 3),
    ("拓荆科技:关于筹划发行股份及支付现金购买资产并募集配套资金事项的停牌公告", "trading_halt", 3),
    ("中金黄金:中金黄金股份有限公司2026年前三季度业绩预增公告", "earnings_warning", 3),
    ("中国能建:中国能源建设股份有限公司关于向特定对象发行A股股票限售股上市流通的公告", "lockup_expiry", 2),
    ("上海电气:上海电气关于重大诉讼的进展公告", "lawsuit", 2),
    ("中国电建:中国电力建设股份有限公司关于签署重大合同的公告", "big_contract", 2),
    ("山金国际:关于董事长、副董事长辞职的公告", "management_change", 2),
    # paperwork / routine / negations: not events
    ("五粮液:北京金杜(成都)律师事务所关于四川省宜宾五粮液集团有限公司增持宜宾五粮液股份有限公司股份之法律意见书", "other", 0),
    ("江波龙:关于最近五年未被证券监管部门和交易所采取监管措施或处罚情况的公告", "other", 1),
    ("保利发展:保利发展控股集团股份有限公司关于公司最近五年不存在被证券监管部门和交易所采取监管措施或处罚的公告", "other", 1),
    ("合盛硅业:关于合盛硅业股份有限公司向特定对象发行股票申请文件的审核问询函之回复报告", "other", 0),
    ("万科A:万科企业股份有限公司2021年面向合格投资者公开发行住房租赁专项公司债券(第一期)(品种二)停牌公告", "other", 1),
    ("宝信软件:关于限制性股票计划限制性股票回购注销实施公告", "incentive", 1),
    ("鹏鼎控股:鹏鼎控股(深圳)股份有限公司关于公司2024年限制性股票激励计划第二个解除限售期解除限售条件部分成就的公告", "incentive", 1),
    ("金龙鱼:关于召开广州益海一审刑事判决投资者说明会的公告", "other", 0),
    ("迈瑞医疗:关于控股股东部分股份解除质押的公告", "pledge_freeze", 1),
    ("东方证券:东方证券股份有限公司关于停牌前一个交易日前十大股东和前十大流通股股东持股情况的公告", "other", 0),
    ("泸州老窖:第十一届董事会二十一次会议决议公告", "other", 0),
]


@pytest.mark.parametrize("title,cat,imp", CASES)
def test_classify_real_titles(title, cat, imp):
    got = an.classify(title)
    assert got[:2] == (cat, imp), title


def test_fetch_read_and_recent(tmp_path, monkeypatch):
    from stockproof import cn
    items = [{"art_code": "AN1", "title": "中微公司:大股东大宗交易减持股份计划公告", "date": "2099-01-02", "column": "", "name": "中微公司"},
             {"art_code": "AN2", "title": "中微公司:第三届董事会会议决议公告", "date": "2099-01-02", "column": "", "name": "中微公司"},
             {"art_code": "AN3", "title": "中微公司:旧公告", "date": "2000-01-01", "column": "", "name": "中微公司"}]
    monkeypatch.setattr(cn, "announcements", lambda info, page_size=50, page_index=1: items)
    monkeypatch.setattr(cn, "announcement_text", lambda code: ("拟减持不超过 1% 股份", "https://pdf/x"))
    monkeypatch.setattr(an.dt, "date", type("D", (an.dt.date,), {"today": classmethod(lambda c: an.dt.date(2099, 1, 5))}))

    class FakeClient:
        model = "m"
        calls = 0
        def chat_json(self, prompt):
            FakeClient.calls += 1
            return {"summary": "大股东拟减持不超过1%。", "impact": -0.4, "why": "减持带来卖压"}

    store = Store(str(tmp_path))
    stats = an.refresh(store, FakeClient(), "p:m", ["688012", "AAPL"], {}, "zh", log=lambda m: None)
    assert stats["new"] == 2 and stats["read"] == 1                 # only the important one is read
    an.refresh(store, FakeClient(), "p:m", ["688012"], {}, "zh", log=lambda m: None)
    assert FakeClient.calls == 1                                    # never read twice
    rec = an.recent(store, ["688012.SH"], lang="zh")
    assert [r["art_code"] for r in rec] == ["AN1"]                  # paperwork (importance 0) hidden
    assert rec[0]["read"]["impact"] == -0.4 and rec[0]["category_name"] == "股东减持"
    assert rec[0]["url"].endswith("/688012/AN1.html")
