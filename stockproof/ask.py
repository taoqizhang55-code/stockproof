"""
One-sentence entry point: "茅台能买吗" / "国家队最近买了什么" / "模拟买入 10 万宁德时代" -> the right feature.

Routing is by rules first (free, instant, predictable); only when no rule matches and an LLM key is set is the
sentence classified by the model, into the same fixed list of intents. The route says how it was decided, so a
wrong guess is visible and the user can rephrase.
"""

from __future__ import annotations

import re

# Well-known short names that aren't a substring of the official name list (贵州茅台 -> 茅台).
ALIASES = {
    "茅台": "600519.SH", "宁德": "300750.SZ", "腾讯": "00700.HK", "阿里": "09988.HK", "小米": "01810.HK",
    "美团": "03690.HK", "平安": "601318.SH", "招行": "600036.SH", "英伟达": "NVDA", "苹果": "AAPL", "特斯拉": "TSLA",
    "微软": "MSFT", "谷歌": "GOOGL", "亚马逊": "AMZN", "脸书": "META", "台积电": "TSM", "讯飞": "002230.SZ",
}

CATEGORIES = {"国家队": "national", "汇金": "national", "社保": "social", "养老金": "social", "北向": "northbound",
              "外资": "northbound", "港资": "northbound", "险资": "insurance", "保险": "insurance", "QFII": "qfii",
              "公募": "fund", "基金": "fund", "national team": "national", "pension": "social", "northbound": "northbound"}

INTENTS = {
    "team": ("team", "AI 投研团队分析一只股票", "AI research team view on a stock"),
    "why": ("stocks", "为什么涨跌", "why a stock moved"),
    "technical": ("stocks", "K 线和支撑阻力", "chart, support and resistance"),
    "smart_money": ("money", "谁在持有这只股票", "who holds this stock"),
    "moneymap": ("money", "国家队 / 社保 / 北向在买什么", "what the national team / pensions / northbound bought"),
    "etf": ("money", "国家队 ETF 托底迹象", "national-team ETF buying"),
    "margin": ("money", "杠杆资金（融资余额）", "margin financing"),
    "breakouts": ("home", "全市场突破扫描", "whole-market breakouts"),
    "compare": ("stocks", "财报和上期比变了什么", "what changed in the latest report"),
    "calendar": ("stocks", "谁要发财报", "earnings calendar"),
    "digest": ("digest", "每日简报", "daily digest"),
    "portfolio": ("portfolio", "持仓体检", "portfolio check-up"),
    "screen": ("screen", "选股", "stock screen"),
    "scorecard": ("screen", "证据评分卡", "evidence scorecard"),
    "lab": ("lab", "量化实验室：检验一个交易想法", "quant lab: test a trading idea"),
    "paper_order": ("paper", "下一笔模拟单", "a paper order"),
    "paper": ("paper", "模拟盘", "paper trading"),
    "alerts": ("paper", "提醒", "alerts"),
    "team_record": ("team", "AI 团队过去准不准", "the team's track record"),
    "menu": ("home", "能做什么", "what stockproof can do"),
}

RULES = [   # (intent, pattern, needs a stock)
    ("paper_order", r"模拟(买|卖|下单)|paper (buy|sell)|(买|卖).{0,12}模拟", True),
    ("paper", r"模拟盘|模拟账户|paper (account|trading)|跑赢.*(沪深|大盘).*模拟", False),
    ("alerts", r"提醒|盯盘|到价|alert", False),
    ("team_record", r"(团队|AI).{0,8}(准不准|准确|胜率|战绩|命中)|track record", False),
    ("breakouts", r"(全市场|哪些|今天).{0,10}(突破|跌破)|breakouts?", False),
    ("etf", r"托底|ETF.{0,6}(申购|份额)|national team ETF", False),
    ("margin", r"融资|杠杆|两融|margin", False),
    ("smart_money", r"股东|主力|龙虎榜|谁(在)?(买|持有)|who holds", True),
    ("moneymap", "|".join(CATEGORIES), False),
    ("why", r"为什么.{0,4}(涨|跌|大涨|大跌|暴涨|暴跌)|为啥.{0,4}(涨|跌)|why .*(move|drop|fall|rise|up|down|jump)", True),
    ("technical", r"[kK] ?线|支撑|压力位|阻力|均线|技术面|图形|chart|support|resistance", True),
    ("compare", r"财报.{0,6}(变|比|对比)|上一期|上期|what changed", True),
    ("calendar", r"(谁|哪些).{0,6}(发|出|公布)财报|财报日历|earnings calendar|reports? (soon|next)", False),
    ("digest", r"简报|今天有什么|digest", False),
    ("portfolio", r"体检|我的持仓|持仓.{0,4}(风险|怎么样)|portfolio", False),
    ("scorecard", r"评分卡|scorecard", True),
    ("screen", r"选股|最强|筛选|找.{0,10}(ROE|市盈率|增长)|strongest|screen", False),
    ("lab", r"回测|历史上.{0,12}(赚|跑赢|有效)|能赚钱吗|策略|backtest|does .* work", False),
    ("menu", r"能做什么|怎么用|帮助|help|what can you do", False),
    ("team", r"分析|能买|能不能买|值得|怎么看|看法|观点|前景|买入|卖出|should i|view on|analy[sz]e", True),
]


def find_stock(app, text: str) -> str | None:
    from stockproof import team
    tk = team.resolve(app, text)
    if tk:
        return tk
    t = text.replace(" ", "")
    hits = [(len(k), v) for k, v in ALIASES.items() if k in t]
    return max(hits)[1] if hits else None


def _amount(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(万|w|千|k|元|块)?", text.replace(",", ""), re.I)
    if not m:
        return None
    n = float(m.group(1))
    unit = (m.group(2) or "").lower()
    return n * (10_000 if unit in ("万", "w") else 1_000 if unit in ("千", "k") else 1)


def holdings(text: str) -> list[dict]:
    """'600519 100股、00700 300股、AAPL 50' -> [{ticker, shares}]"""
    out = []
    for m in re.finditer(r"([A-Za-z]{1,5}|\d{4,6}(?:\.[A-Za-z]{2})?)\s*[:：x×]?\s*(\d+)\s*(股|shares)?", text):
        code, n = m.group(1), int(m.group(2))
        if code.isdigit() and len(code) == 6 and n < 10 and not m.group(3):
            continue
        out.append({"ticker": code.upper(), "shares": n})
    return out


def route(app, text: str, client=None) -> dict:
    """{intent, ticker, args, how, tab, label}. how: rules | llm | default."""
    t = str(text or "").strip()
    tk = find_stock(app, t)
    low = t.lower()
    intent, how = None, "rules"
    for name, pat, needs in RULES:
        if re.search(pat, low if pat.isascii() else t, re.I) and (tk or not needs):
            intent = name
            break
    if intent is None and client is not None:
        intent = _llm_intent(client, t, tk)
        how = "llm" if intent else how
    if intent is None:
        intent, how = ("team" if tk else "menu"), "default"
    args: dict = {}
    if intent == "moneymap":
        args["category"] = next((v for k, v in CATEGORIES.items() if k.lower() in low), "national")
        if tk:                                   # "国家队有没有买科大讯飞" -> the stock's holders
            intent = "smart_money"
    if intent == "paper_order":
        args["side"] = "sell" if re.search(r"卖|sell", low) else "buy"
        n = re.search(r"(\d+)\s*股", t)
        if n:
            args["shares"] = int(n.group(1))
        else:
            v = _amount(re.sub(r"\d{6}(\.\w\w)?", "", t))
            args["value"] = v if v and v >= 1000 else 100_000
    if intent == "portfolio":
        args["holdings"] = holdings(t)
    if intent == "team":
        rest = re.sub(r"\d{4,6}(\.\w\w)?|[A-Z]{1,5}", "", t)
        for nm in sorted(list(ALIASES) + [getattr(app, "name_of", lambda x: x)(tk) or ""], key=len, reverse=True):
            rest = rest.replace(nm, "")
        args["question"] = t if len(re.sub(r"[\s\W]", "", rest)) >= 2 else None
    if intent in ("breakouts",):
        args["direction"] = "down" if "跌破" in t else "up" if "突破" in t and "跌破" not in t else "both"
    tab, zh_label, en_label = INTENTS[intent]
    return {"text": t, "intent": intent, "ticker": tk, "args": args, "how": how, "tab": tab,
            "label": zh_label, "label_en": en_label}


def _llm_intent(client, text: str, tk: str | None) -> str | None:
    opts = ", ".join(INTENTS)
    try:
        r = client.chat_json(
            "Classify this request to a stock research tool into exactly one intent.\n"
            f"Intents: {opts}.\nStock mentioned: {tk or 'none'}. If none of them fits, answer menu.\n"
            f'Request: "{text[:300]}"\nReply as JSON: {{"intent": "..."}}')
        it = str((r or {}).get("intent", "")).strip()
        return it if it in INTENTS else None
    except Exception:
        return None


def cli_argv(r: dict) -> list[str] | None:
    """The equivalent stockproof command, so `ask` teaches the commands as it goes."""
    tk, a, i = r["ticker"], r["args"], r["intent"]
    if i == "team":
        return ["team", tk] + (["--ask", a["question"]] if a.get("question") else [])
    if i == "team_record":
        return ["team", "--record"]
    if i == "moneymap":
        return ["moneymap", "--category", a.get("category", "national")]
    if i == "smart_money":
        return ["moneymap", "--ticker", tk]
    if i == "etf":
        return ["moneymap", "--etf"]
    if i == "margin":
        return ["moneymap", "--margin"]
    if i == "breakouts":
        return ["breakouts"]
    if i == "portfolio" and a.get("holdings"):
        return ["portfolio", ", ".join(f"{h['ticker']} {h['shares']}" for h in a["holdings"])]
    if i == "paper":
        return ["paper", "list"]
    if i == "alerts":
        return ["alerts"]
    if i == "screen":
        return ["screen"]
    if i == "scorecard":
        return ["scorecard", tk]
    if i == "calendar":
        return ["calendar"]
    if i == "lab":
        return ["lab", "list"]
    return None
