"""
Shareable result cards (1200 x 675 SVG, the size social sites preview): an AI research-team call, a paper
account's record, a lab backtest verdict.

Every card carries what makes it checkable — the forward-log id and when it will be scored, the append-only
paper record and its fill rules, the number of variants tried before a backtest — and "not advice". A card
never shows a better number than the tool itself does.
"""

from __future__ import annotations

import html
import json

import pandas as pd

W, H = 1200, 675
FONT = "PingFang SC, Hiragino Sans GB, Noto Sans CJK SC, Microsoft YaHei, Helvetica, Arial, sans-serif"
INK, MUTED, LINE, BG = "#1d1d1f", "#6e6e73", "#e5e5ea", "#ffffff"
UP, DOWN, NEUTRAL, ACCENT = "#d9363e", "#1f9d55", "#8e8e93", "#3a5bd9"     # zh colours: red up, green down


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _w(ch: str) -> float:
    return 1.0 if ord(ch) > 0x2E80 else 0.56


def wrap(text: str, size: float, width: float, max_lines: int = 3) -> list[str]:
    """Greedy wrap by estimated glyph width (CJK = 1 em, Latin ~0.56 em)."""
    lines, cur, cw = [], "", 0.0
    for ch in str(text or ""):
        if ch == "\n":
            lines.append(cur)
            cur, cw = "", 0.0
            continue
        cw += _w(ch) * size
        if cw > width and cur:
            lines.append(cur)
            cur, cw = ch, _w(ch) * size
        else:
            cur += ch
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
    return lines


def _text(x, y, s, size=20, fill=INK, weight=400, anchor="start") -> str:
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" font-weight="{weight}" '
            f'text-anchor="{anchor}">{_e(s)}</text>')


def _lines(x, y, lines, size=20, fill=INK, gap=1.45, weight=400) -> tuple[str, float]:
    out = "".join(_text(x, y + i * size * gap, ln, size, fill, weight) for i, ln in enumerate(lines))
    return out, y + len(lines) * size * gap


def _frame(body: str, footer: str, lang: str) -> str:
    zh = lang == "zh"
    brand = "stockproof · 有据" if zh else "stockproof"
    tag = "AI 读新闻、财报和公告，再用历史数据检验哪些真的有用" if zh else "AI reads the news; history decides what counts"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'font-family="{FONT}"><rect width="{W}" height="{H}" fill="{BG}"/>'
            f'<rect width="{W}" height="6" fill="{ACCENT}"/>'
            + _text(56, 58, brand, 22, ACCENT, 700) + _text(W - 56, 58, tag, 15, MUTED, 400, "end")
            + body
            + f'<line x1="56" y1="{H - 74}" x2="{W - 56}" y2="{H - 74}" stroke="{LINE}"/>'
            + "".join(_text(56, H - 46 + i * 22, ln, 14, MUTED) for i, ln in enumerate(footer.split("\n")[:2]))
            + "</svg>")


def _spark(series: list[tuple], x, y, w, h, levels: list[tuple] | None = None, second: list | None = None,
           color=INK) -> str:
    """A line chart of [(label, value)], optional second line (benchmark) and horizontal levels [(value, colour, label)]."""
    vals = [v for _, v in series if v is not None] + [v for _, v in (second or []) if v is not None]
    vals += [lv for lv, _, _ in (levels or [])]
    if len(series) < 2 or not vals:
        return ""
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or abs(hi) * 0.02 or 1
    lo, hi = lo - pad, hi + pad
    sx = lambda i, n: x + i * w / max(1, n - 1)
    sy = lambda v: y + h - (v - lo) / (hi - lo) * h
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#fafafa" rx="8"/>'
    for lv, col, lab in levels or []:
        out += (f'<line x1="{x}" y1="{sy(lv):.1f}" x2="{x + w}" y2="{sy(lv):.1f}" stroke="{col}" stroke-dasharray="6 5" '
                f'stroke-width="1.5"/>' + _text(x + w - 6, sy(lv) - 6, lab, 13, col, 600, "end"))

    def path(ser, col, width):
        pts = [(sx(i, len(ser)), sy(v)) for i, (_, v) in enumerate(ser) if v is not None]
        return (f'<polyline fill="none" stroke="{col}" stroke-width="{width}" stroke-linejoin="round" '
                f'points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}"/>') if len(pts) > 1 else ""
    if second:
        out += path(second, "#b0b0b5", 2)
    out += path(series, color, 3)
    out += _text(x, y + h + 22, series[0][0], 13, MUTED) + _text(x + w, y + h + 22, series[-1][0], 13, MUTED, 400, "end")
    return out


def _pct(v, digits=1) -> str:
    return "—" if v is None or (isinstance(v, float) and pd.isna(v)) else f"{100 * v:+.{digits}f}%"


# ---------------------------------------------------------------- team call
STANCE = {"zh": {"bullish": "偏多", "bearish": "偏空", "neutral": "中性", "no_view": "暂无观点"},
          "en": {"bullish": "Bullish", "bearish": "Bearish", "neutral": "Neutral", "no_view": "No view"}}
CONF = {"zh": {"low": "低", "medium": "中", "high": "高"}, "en": {"low": "low", "medium": "medium", "high": "high"}}


def team_card(store, data_dir: str, call_id: str, lang: str = "zh") -> str | None:
    from stockproof import quotes, team
    store.conn.executescript(team.SCHEMA)
    row = store.conn.execute("SELECT result FROM team_calls WHERE id=?", (call_id,)).fetchone()
    if not row:
        return None
    res = json.loads(row[0])
    sc = store.conn.execute("SELECT end_day, excess, hit FROM team_scores WHERE call_id=?", (call_id,)).fetchone()
    zh = lang == "zh"
    f = res.get("final") or {}
    stance = f.get("stance", "no_view")
    col = {"bullish": UP if zh else DOWN, "bearish": DOWN if zh else UP}.get(stance, NEUTRAL)
    name = res.get("name") or res["ticker"]
    body = _text(56, 128, f"{name}  {res['ticker']}", 40, INK, 700)
    body += _text(56, 162, (f"AI 投研团队 · {res['day']} · 当时价格 {res.get('price')}" if zh else
                            f"AI research team · {res['day']} · price then {res.get('price')}"), 17, MUTED)
    body += (f'<rect x="56" y="186" width="190" height="64" rx="12" fill="{col}"/>'
             + _text(151, 230, STANCE[lang if lang in STANCE else "en"].get(stance, stance), 32, "#fff", 700, "middle"))
    conf = CONF[lang if lang in CONF else "en"].get(f.get("confidence"), f.get("confidence"))
    body += _text(270, 212, (f"置信度：{conf}" if zh else f"Confidence: {conf}"), 20, INK, 600)
    body += _text(270, 242, (f"观察期：{f.get('horizon_days')} 个交易日" if zh else f"Horizon: {f.get('horizon_days')} trading days"), 18, MUTED)
    y = 296
    if res.get("question"):
        t, y = _lines(56, y, wrap(("问题：" if zh else "Question: ") + res["question"], 18, 560, 2), 18, ACCENT, weight=600)
        y += 6
    t2, y = _lines(56, y, wrap(f.get("summary", ""), 19, 560, 5), 19)
    body += (t if res.get("question") else "") + t2
    plan = [p for p in f.get("plan", []) if p.get("if")][:3]
    if plan:
        y += 8
        body += _text(56, y, "观察计划（不是指令）" if zh else "Watch plan (not orders)", 16, MUTED, 600)
        for p in plan:
            ln = wrap(f"· {p['if']} → {p.get('then', '')}", 16, 560, 1)[0]
            y += 26
            body += _text(56, y, ln, 16)
    if f.get("cap_note"):
        body += "".join(_text(56, min(y + 34, H - 100) + i * 20, ln, 14, MUTED)
                        for i, ln in enumerate(wrap(f["cap_note"], 14, 560, 2)))
    bars = quotes.load_bars(data_dir, res["ticker"]).dropna(subset=["close"])
    if len(bars) > 10:
        upto = bars[bars.index <= pd.Timestamp(res["day"])].iloc[-120:]
        after = bars[bars.index > pd.Timestamp(res["day"])]
        ser = [(d.date().isoformat(), float(v)) for d, v in pd.concat([upto["close"], after["close"]]).items()]
        levels = [(float(p["level"]), ACCENT, f"{p['level']:g}") for p in plan if isinstance(p.get("level"), (int, float))]
        body += _spark(ser, 660, 110, 484, 330, levels)
        if len(after):
            i = len(upto) - 1
            x = 660 + i * 484 / max(1, len(ser) - 1)
            body += (f'<line x1="{x:.1f}" y1="110" x2="{x:.1f}" y2="440" stroke="{col}" stroke-width="1.5"/>'
                     + _text(x - 6, 430, "判断日" if zh else "call", 13, col, 600, "end"))
    if sc:
        verdict = (("命中" if sc[2] else "未命中") if zh else ("hit" if sc[2] else "miss"))
        body += _text(660, 488, (f"{sc[0]} 到期：相对大盘 {_pct(sc[1])}，{verdict}" if zh else
                                 f"Scored {sc[0]}: {_pct(sc[1])} vs the market, {verdict}"), 20, INK, 700)
    else:
        body += _text(660, 488, (f"还没到期：{f.get('horizon_days')} 个交易日后按实际涨跌打分" if zh else
                                 f"Not scored yet: scored against the market after {f.get('horizon_days')} trading days"), 17, MUTED)
    try:
        s = team.track_record(store, lang, limit=1)["summary"]
        if s.get("scored"):
            body += _text(660, 518, (f"团队战绩：{s['scored']} 次到期，命中率 {100 * s['hit_rate']:.0f}%" if zh else
                                     f"Team record: {s['scored']} scored, hit rate {100 * s['hit_rate']:.0f}%"), 16, MUTED)
    except Exception:
        pass
    foot = ((f"前瞻日志编号 {call_id} · 记录不可修改，可随时核对 · 有出处的 AI 观点，不是投资建议\n"
             "每个论点都引用编号证据；没有通过历史检验的方面，置信度最高只能是“低”。") if zh else
            (f"Forward-log id {call_id} · append-only, checkable · a cited AI view, not advice\n"
             "Every point cites numbered evidence; confidence is capped at low unless a history-tested area supports it."))
    return _frame(body, foot, lang)


# ---------------------------------------------------------------- paper account
def paper_card(store, data_dir: str, aid: str, lang: str = "zh") -> str | None:
    from stockproof import paper
    if not paper.account(store, aid):
        return None
    s = paper.state(store, data_dir, aid)
    zh = lang == "zh"
    ac = s["account"]
    bench = ("沪深300" if zh else "CSI 300") if ac["market"] == "cn" else "S&P 500"
    body = _text(56, 128, ac["name"], 40, INK, 700)
    body += _text(56, 162, ((f"模拟盘 · {ac['start_day']} 至 {s['as_of']} · 起始资金 {ac['cash']:,.0f}") if zh else
                            f"Paper account · {ac['start_day']} to {s['as_of']} · start {ac['cash']:,.0f}"), 17, MUTED)
    if ac.get("note"):
        body += _text(56, 190, wrap(ac["note"], 15, 1080, 1)[0], 15, MUTED)
    r, ex = s["return"], s.get("excess")
    ret_col = (UP if r >= 0 else DOWN) if zh else (DOWN if r >= 0 else UP)
    kpis = [("收益" if zh else "Return", _pct(r, 2), ret_col),
            (bench, _pct(s.get("benchmark_return"), 2), INK),
            ("超额" if zh else "Excess", _pct(ex, 2), INK),
            ("最大回撤" if zh else "Max drawdown", _pct(s["max_drawdown"], 1), INK),
            ("已付成本" if zh else "Costs paid", f"{s['costs_paid']:,.0f}", INK)]
    for i, (k, v, c) in enumerate(kpis):
        x = 56 + i * 220
        body += _text(x, 236, k, 16, MUTED) + _text(x, 278, v, 32, c, 700)
    ser = [(d, v) for d, v, _ in s["nav"]]
    bm = [(d, b) for d, _, b in s["nav"]]
    body += _spark(ser, 56, 306, 1088, 200, None, bm, ACCENT)
    filled = sum(1 for o in s["orders"] if o.get("status") == "filled")
    body += _text(56, 548, (f"成交 {filled} 笔 · 取消 {s['cancelled']} 笔 · 待成交 {s['pending']} 笔 · "
                            f"蓝线：模拟盘  灰线：{bench}") if zh else
                  f"{filled} filled · {s['cancelled']} cancelled · {s['pending']} pending · blue: paper, grey: {bench}", 15, MUTED)
    foot = (("悲观成交：下一个交易日开盘成交，涨停不买、跌停不卖，每笔最多当天成交量 5%，含冲击成本、佣金、印花税，T+1\n"
             "订单和成交只能追加、不能修改。模拟盘，不是实盘，不构成投资建议。") if zh else
            ("Pessimistic fills: next open, no buys at limit-up / sells at limit-down, max 5% of volume, impact, costs, T+1\n"
             "Orders and fills are append-only. Paper trading, not real money, not advice."))
    return _frame(body, foot, lang)


# ---------------------------------------------------------------- lab verdict
VERDICT = {"zh": {"passes": "通过（多重检验后仍显著）", "confirmed": "样本外确认", "failed": "样本外失效",
                  "negative": "跑输大盘", "no_edge": "没有优势", "luck_risk": "可能是运气（试得太多）",
                  "no_trades": "没有交易"},
           "en": {"passes": "Passes (after multiple testing)", "confirmed": "Confirmed out of sample",
                  "failed": "Failed out of sample", "negative": "Underperforms", "no_edge": "No edge",
                  "luck_risk": "Could be luck (many tries)", "no_trades": "No trades"}}


def lab_card(data_dir: str, exp_id: str, lang: str = "zh") -> str | None:
    from stockproof import lab
    rows = lab.trials(data_dir)
    rec = next((r for r in reversed(rows) if r.get("id") == exp_id), None)
    if not rec:
        return None
    zh = lang == "zh"
    L = lang if lang in VERDICT else "en"
    good = rec.get("verdict") in ("passes", "confirmed")
    tries = len({r["hash"] for r in rows if r.get("phase") == "explore" and r.get("time", "") <= rec.get("time", "")})
    desc = lab.describe_spec(rec["spec"], lang)
    body = _text(56, 120, "量化实验室回测" if zh else "Quant lab backtest", 20, MUTED, 600)
    t, y = _lines(56, 162, wrap(desc, 30, 1088, 2), 30, INK, 1.35, 700)
    body += t
    col = "#1f9d55" if good else "#d9363e"
    body += (f'<rect x="56" y="{y + 8}" width="520" height="60" rx="12" fill="{col}"/>'
             + _text(76, y + 48, VERDICT[L].get(rec.get("verdict"), rec.get("verdict")), 26, "#fff", 700))
    y += 120
    kpis = [("年化超额（扣成本）" if zh else "Annual excess (after costs)", _pct(rec.get("ann"), 1)),
            ("t 值" if zh else "t-stat", "—" if rec.get("t") is None else f"{rec['t']:.1f}"),
            ("交易笔数" if zh else "Trades", f"{rec.get('n', 0)}"),
            ("成本翻倍" if zh else "2x costs", {"robust": "仍成立" if zh else "holds", "fragile": "失效" if zh else "dies",
                                                "weak": "变弱" if zh else "weaker", "no_edge": "无优势" if zh else "no edge"}
             .get(rec.get("stress"), "—")),
            ("滚动检验" if zh else "Walk-forward", {"holds": "站得住" if zh else "holds", "fades": "消失" if zh else "fades"}
             .get(rec.get("walk_forward"), "—"))]
    for i, (k, v) in enumerate(kpis):
        x = 56 + i * 220
        body += _text(x, y, k, 16, MUTED) + _text(x, y + 44, v, 32, INK, 700)
    y += 100
    phase = (("探索阶段：只用了锁定期之前的数据" if rec.get("phase") == "explore" else "样本外：锁定的近两年数据，只能跑一次") if zh else
             ("Exploration: data before the locked holdout only" if rec.get("phase") == "explore" else
              "Holdout: the locked recent years, run once"))
    body += _text(56, y, phase, 18, INK, 600)
    body += _text(56, y + 32, (f"到这次为止一共试过 {tries} 个不同的策略，门槛已经按试的次数提高。" if zh else
                               f"{tries} distinct strategies tried up to this one; the bar rises with every try."), 17, MUTED)
    foot = ((f"实验编号 {exp_id} · 时点数据（按公告日）、扣真实成本、近两年锁定、多重检验校正\n"
             "历史回测不代表未来，不构成投资建议。") if zh else
            (f"Experiment {exp_id} · point-in-time data, real costs, locked holdout, multiple-testing correction\n"
             "Past results don't predict the future. Not advice."))
    return _frame(body, foot, lang)


def render(kind: str, ref: str, store, data_dir: str, lang: str = "zh") -> str | None:
    if kind == "team":
        return team_card(store, data_dir, ref, lang)
    if kind == "paper":
        return paper_card(store, data_dir, ref, lang)
    if kind == "lab":
        return lab_card(data_dir, ref, lang)
    return None
