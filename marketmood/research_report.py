"""
HTML report for `marketmood research` (one self-contained file, light/dark, phone-friendly).
Texts live here (not in i18n.py) because only this report uses them.
"""

from __future__ import annotations

import datetime as dt
import html
import math

import pandas as pd

from marketmood.report import CSS

EXTRA_CSS = """
.big { font-size:15px; margin:0 0 10px; }
.cmp { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px; }
.pct { font-variant-numeric:tabular-nums; white-space:nowrap; }
.t { color:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }
.sig { font-weight:700; }
.hbar { position:relative; height:10px; min-width:110px; background:var(--neu-bg); border-radius:5px; }
.hbar .mid { position:absolute; left:50%; top:-3px; bottom:-3px; width:1px; background:var(--muted); opacity:.6; }
.hbar .fill { position:absolute; top:0; bottom:0; border-radius:5px; }
.callout { border-left:3px solid var(--accent); padding:4px 12px; margin:12px 0; }
ul.caveats { margin:0; padding-left:18px; } ul.caveats li { margin:6px 0; }
td.row-total { font-weight:600; }
"""

TEXT = {
    "en": {
        "title": "marketmood · Research",
        "subtitle": "Does the news mood or the earnings surprise predict the stock's next moves?",
        "generated": "Generated {time}",
        "prices": "Prices: {n} stocks, {start} to {end}",
        "bench": "Market-adjusted returns: stock minus {bench}",
        "bench_ew": "the equal-weighted average of all stocks in the price file",
        "bench_spy": "SPY",
        # earnings
        "e_title": "1 · Earnings surprise (SUE) and returns",
        "e_none": "No earnings events (needs US stocks with SEC data and prices).",
        "e_intro": ("{n} quarterly announcements from {stocks} stocks. Reaction = market-adjusted return on "
                    "the announcement day and the next day. Drift = days 2 to 61 after it: what was still "
                    "there to earn after reading the news."),
        "e_dates_title": "Getting the date right matters",
        "e_dates": ("The same {n_8k} quarters, measured from two different dates. With the 8-K press-release "
                    "date the market's reaction is clear; with the 10-Q date (often weeks later) it has already "
                    "happened and seems to disappear. ({n} quarters in all; those without an 8-K are left out.)"),
        "e_sue_title": "By size of the surprise (announcement dates only)",
        "e_reg": "Regression on SUE (capped at ±5): reaction slope {b1} per 1 SUE (t = {t1}), drift slope {b2} (t = {t2}).",
        "e_halves": "Is it stable? Same table, first half vs second half of the sample",
        "tone_title": "2 · Does the LLM's reading add anything to SUE?",
        "tone_none": ("Not run yet: needs past press releases read by the LLM. Run "
                      "<code>marketmood research --backfill 8</code> to read the last 8 per stock "
                      "(saved, so each release is paid for once)."),
        "tone_intro": "{n} announcements with an LLM reading ({start} to {end}). Drift needs 61 trading days after the report, so the newest ones only count for the reaction.",
        "tone_by": "By the LLM's tone",
        "reg_title": "Reaction explained by SUE alone vs SUE + tone",
        "reg_cols": ["model", "n", "SUE slope (t)", "tone slope (t)", "R²"],
        "guid_title": "By guidance label",
        # news
        "b_title": "3 · Can the drift be traded? A backtest with costs",
        "b_intro": ("Buy every stock whose SUE is ≥ {long} at the close of the day after the announcement "
                    "(after the reaction) and hold it {hold} trading days. "
                    "Costs per side: commission {comm}, slippage {slip}{duty}. {rules}"),
        "b_duty": "; stamp duty on sales {duty}",
        "b_rules_cn": ("A-share rules: no buying on a day that closes at the limit-up, no selling at "
                       "limit-down, suspended days can't be traded; orders wait up to 5 days."),
        "b_rules_us": "",
        "b_rows": {"long_excess": "Long-only, minus the market", "long_excess_gross": "… same, before costs",
                   "long": "Long-only (total return)", "long_short_gross": "… same, before costs",
                   "bench": "The market (same stocks, same days)",
                   "long_short": "Long − short (hypothetical: also short SUE ≤ {short})"},
        "b_cols": ["", "per year", "volatility", "Sharpe", "t", "max drawdown"],
        "b_trades": ("Average trade after costs, compared with the market over the same days: long {lm} "
                     "(beat the market in {lw} of {ln} trades, t = {lt}); short {sm} (n = {sn}, t = {st})."),
        "b_curve": "Growth of 1 (long-only minus market, and long − short)",
        "b_years": "By year",
        "b_short": {"long_excess": "long − market", "long_short": "long − short"},
        "b_slots": ("Capital is split into {slots} slots; empty slots hold the market (like an index fund). "
                    "On average {pos:.0f} positions were open."),
        "b_sweep": "Other settings (is the result fragile?)",
        "b_sweep_cols": ["SUE cut-off", "hold (days)", "long trades", "long-only excess / yr", "t",
                         "per trade", "beat market", "long − short / yr"],
        "b_none": "Not enough events for a backtest.",
        "n_title": "4 · News mood and returns",
        "n_none": "No scored headlines with prices yet.",
        "n_intro": ("{n} relevant headlines ({stocks} stocks), published {start} to {end}. Day 0 = the publish "
                    "date (headlines have no time, so day 0 mixes cause and report). Day 1 onward is what "
                    "you could have traded."),
        "n_thin": ("Not enough history yet: only {n1} headlines have a next-day return and {n5} a full "
                   "5-day window. These numbers will mean something after a few weeks of daily scans."),
        # tables
        "bucket": "bucket", "n": "n", "reaction": "reaction (day 0–1)", "drift": "drift (day 2–61)",
        "d_1": "day −1", "d0": "day 0", "d1": "day 1", "d1_5": "days 1–5",
        "src_8k": "8-K date (press release)", "src_10q": "10-Q date (quarterly report)",
        "src_actual": "actual disclosure date", "src_deadline": "legal deadline",
        "e_dates_cn": ("The same {n_8k} quarters, measured from the actual disclosure date (or the earlier "
                       "preliminary results, 业绩快报) and from the legal deadline (Apr 30 / Aug 31 / Oct 31). "
                       "Backtests that only know the deadline miss the reaction."),
        "tone_cn": ("Not run yet: needs past reports read by the LLM. Run "
                    "marketmood research --market cn --backfill 4 to read the last 4 per stock."),
        "bench_csi": "the CSI 300 index",
        "guidance": "guidance",
        "t_note": "Small grey numbers are t-statistics; |t| ≥ 2 is shown in bold (roughly: unlikely to be luck).",
        "cav_title": "Read before drawing conclusions",
        "caveats": [
            "Survivorship bias: the stock list is today's large companies. Firms that shrank or disappeared are missing, which flatters long-run results.",
            "Same-day announcements move together (a market-wide day affects many at once), so true t-statistics are somewhat smaller than shown.",
            "LLM look-ahead: the model was trained on text from the internet, possibly including what happened after older releases. Its readings of releases from before its training cutoff may be better than they could have been at the time. Compare with releases after the cutoff.",
            "Market-adjusted, not risk-adjusted: a stock that simply moves more than the market (high beta) shows bigger abnormal returns on big market days.",
            "No trading costs. A difference of a few tenths of a percent can disappear after costs.",
        ],
        "files": "Event-level data saved to: {files}",
    },
    "zh": {
        "title": "marketmood · 研究",
        "subtitle": "新闻情绪或财报惊喜，能不能预测股票接下来的走势？",
        "generated": "生成于 {time}",
        "prices": "价格：{n} 只股票，{start} 至 {end}",
        "bench": "超额收益 = 个股收益 − {bench}",
        "bench_ew": "价格文件中所有股票的等权平均",
        "bench_spy": "SPY",
        "e_title": "1 · 财报惊喜（SUE）与股价",
        "e_none": "没有财报事件（需要有 SEC 数据和价格的美股）。",
        "e_intro": ("共 {n} 次季度财报发布，来自 {stocks} 只股票。反应 = 发布当天和第二天的超额收益；"
                    "漂移 = 发布后第 2 到第 61 个交易日的超额收益，即读到财报之后还能赚到的部分。"),
        "e_dates_title": "日期必须找对",
        "e_dates": ("同样这 {n_8k} 个季度，分别从两个日期算起。用 8-K 新闻稿日期，市场反应很明显；用 10-Q 日期"
                    "（往往晚几周），反应早已发生，看起来就消失了。（共 {n} 个季度，没有 8-K 的不计入。）"),
        "e_sue_title": "按惊喜大小分组（仅用真实发布日）",
        "e_reg": "对 SUE 回归（截断在 ±5）：反应斜率每 1 个 SUE {b1}（t = {t1}），漂移斜率 {b2}（t = {t2}）。",
        "e_halves": "稳定吗？同一张表，样本前半段 vs 后半段",
        "tone_title": "2 · LLM 的解读能在 SUE 之外提供新信息吗？",
        "tone_none": ("还没运行：需要 LLM 读过历史财报新闻稿。运行 <code>marketmood research --backfill 8</code>"
                      " 读每只股票最近 8 份（会保存，每份只花一次钱）。"),
        "tone_intro": "{n} 次有 LLM 解读的财报（{start} 至 {end}）。漂移需要发布后 61 个交易日，所以最新的几期只计入反应。",
        "tone_by": "按 LLM 语气分组",
        "reg_title": "只用 SUE 解释反应 vs SUE + 语气",
        "reg_cols": ["模型", "n", "SUE 斜率 (t)", "语气斜率 (t)", "R²"],
        "guid_title": "按指引标签分组",
        "b_title": "3 · 漂移能不能真的交易？考虑成本的回测",
        "b_intro": ("凡是 SUE ≥ {long} 的股票，在财报发布后第二天收盘买入（市场反应之后），持有 {hold} 个交易日。"
                    "每边成本：佣金 {comm}，滑点 {slip}{duty}。{rules}"),
        "b_duty": "；卖出印花税 {duty}",
        "b_rules_cn": "A 股规则：收盘涨停的日子买不进，跌停的日子卖不出，停牌日不能交易；订单最多等 5 天。",
        "b_rules_us": "",
        "b_rows": {"long_excess": "只做多，减去市场", "long_excess_gross": "……同上，扣成本前",
                   "long": "只做多（总收益）", "long_short_gross": "……同上，扣成本前",
                   "bench": "市场（同一批股票、同样的日子）",
                   "long_short": "多空（假设：同时做空 SUE ≤ {short} 的股票）"},
        "b_cols": ["", "年化", "波动率", "夏普", "t", "最大回撤"],
        "b_trades": ("扣除成本后，每笔交易相对同期市场的平均表现：做多 {lm}（{ln} 笔中 {lw} 跑赢市场，t = {lt}）；"
                     "做空 {sm}（{sn} 笔，t = {st}）。"),
        "b_curve": "1 元的增长（只做多减市场，以及多空）",
        "b_years": "分年度",
        "b_short": {"long_excess": "做多 − 市场", "long_short": "多空"},
        "b_slots": "资金分成 {slots} 份，没用上的份额持有市场（相当于指数基金）。平均同时持有 {pos:.0f} 只股票。",
        "b_sweep": "换一组参数（结果是否脆弱？）",
        "b_sweep_cols": ["SUE 门槛", "持有天数", "做多笔数", "做多超额/年", "t", "每笔", "跑赢比例", "多空/年"],
        "b_none": "事件太少，无法回测。",
        "n_title": "4 · 新闻情绪与股价",
        "n_none": "还没有带价格的已打分新闻。",
        "n_intro": ("{n} 条相关新闻（{stocks} 只股票），发布于 {start} 至 {end}。第 0 天 = 发布日期"
                    "（新闻没有具体时间，所以第 0 天既可能是新闻引起的涨跌，也可能是新闻在报道涨跌）。"
                    "第 1 天起才是能实际交易的部分。"),
        "n_thin": ("历史还不够：只有 {n1} 条新闻有第二天的收益，{n5} 条有完整的 5 天窗口。"
                   "每天扫描几周之后，这些数字才有意义。"),
        "bucket": "分组", "n": "数量", "reaction": "反应（第 0–1 天）", "drift": "漂移（第 2–61 天）",
        "d_1": "前 1 天", "d0": "第 0 天", "d1": "第 1 天", "d1_5": "第 1–5 天",
        "src_8k": "8-K 日期（新闻稿）", "src_10q": "10-Q 日期（季报）",
        "src_actual": "实际披露日", "src_deadline": "法定截止日",
        "e_dates_cn": ("同样这 {n_8k} 个季度，分别从实际披露日（如果业绩快报更早，用快报日）和法定截止日"
                       "（4/30、8/31、10/31）算起。只知道截止日的回测会错过市场反应。"),
        "tone_cn": "还没运行：需要 AI 读过历史财报。运行 marketmood research --market cn --backfill 4，读每只股票最近 4 期。",
        "bench_csi": "沪深 300 指数",
        "guidance": "指引",
        "t_note": "灰色小字是 t 统计量；|t| ≥ 2 加粗（大致表示不太可能是运气）。",
        "cav_title": "下结论之前请看",
        "caveats": [
            "幸存者偏差：股票名单是今天的大公司，后来缩水或消失的公司不在里面，会让长期结果看起来更好。",
            "同一天发布的财报会一起涨跌（大盘的影响），所以真实的 t 统计量比显示的小一些。",
            "LLM 的前视偏差：模型用互联网文本训练，可能见过旧财报发布之后发生的事，所以它对训练截止日之前的财报解读可能比当时能做到的更准。应与截止日之后的财报对比。",
            "只扣除了大盘，没有调整风险：本身波动比大盘大的股票（高 beta），在大盘大涨大跌的日子会显示更大的超额收益。",
            "没有计算交易成本。零点几个百分点的差异扣除成本后可能就没了。",
        ],
        "files": "事件明细已保存到：{files}",
    },
}

BUCKET_ZH = {"negative": "负面", "neutral": "中性", "positive": "正面", "top − bottom": "最高组 − 最低组",
             "bad (≤ −0.5)": "差（≤ −0.5）", "in line": "符合往常", "good (≥ 0.5)": "好（≥ 0.5）",
             "raised": "上调", "maintained": "维持", "provided": "给出", "lowered": "下调", "none": "无",
             "initiated": "首次给出", "withdrawn": "撤回"}


def _e(x) -> str:
    return html.escape(str(x))


def _pct(v) -> str:
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{100 * v:+.2f}%"


def _num(v, fmt="{:+.3f}") -> str:
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else fmt.format(v)


def _t(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    cls = "t sig" if abs(v) >= 2 else "t"
    return f' <span class="{cls}">t={v:.1f}</span>'


def _hbar(v, scale) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)) or not scale:
        return '<div class="hbar"><span class="mid"></span></div>'
    w = min(50.0, 50.0 * abs(v) / scale)
    left = 50.0 if v >= 0 else 50.0 - w
    color = "var(--pos)" if v >= 0 else "var(--neg)"
    return (f'<div class="hbar"><span class="mid"></span><span class="fill" '
            f'style="left:{left:.1f}%;width:{w:.1f}%;background:{color}"></span></div>')


def _label(lab: str, lang: str) -> str:
    return BUCKET_ZH.get(lab, lab) if lang == "zh" else lab


def _bucket_html(tab: pd.DataFrame, outcomes, lang: str, first_col: str = "bucket", bars: bool = True) -> str:
    T = TEXT[lang]
    if tab is None or not len(tab):
        return ""
    vals = [abs(v) for o in outcomes for v in tab[o].tolist() if isinstance(v, float) and not math.isnan(v)]
    scale = max(vals) if vals else 0
    bar_th = "<th class='hide-sm'></th>" if bars else ""
    head = "".join(f"<th>{_e(T.get(o, o))}</th>{bar_th}" for o in outcomes)
    rows = []
    for _, r in tab.iterrows():
        total = r[first_col] == "top − bottom"
        cells = "".join(
            f"<td class='pct'>{_pct(r[o])}{_t(r.get(o + '_t'))}</td>"
            + (f"<td class='hide-sm'>{_hbar(r[o], scale)}</td>" if bars else "")
            for o in outcomes)
        n = int(r.get(outcomes[0] + "_n", r.get("n", 0)) or 0)
        rows.append(f"<tr><td class='{'row-total' if total else ''}'>{_e(_label(r[first_col], lang))}</td>"
                    f"<td class='num'>{n}</td>{cells}</tr>")
    return (f"<div class='wide'><table><tr><th>{_e(T.get(first_col, first_col))}</th><th>{_e(T['n'])}</th>"
            f"{head}</tr>{''.join(rows)}</table></div>")



def _share(v) -> str:
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{100 * v:.0f}%"


def _line_chart(curve: dict, labels: dict) -> str:
    """Small inline SVG: growth of 1 for each series (weekly points)."""
    dates = curve.get("dates") or []
    series = [(k, curve[k]) for k in ("long_excess", "long_short") if curve.get(k)]
    if len(dates) < 2 or not series:
        return ""
    W, H, L, R, Tp, B = 720, 220, 44, 10, 10, 26
    vals = [v for _, ys in series for v in ys if v is not None]
    lo, hi = min(vals + [1.0]), max(vals + [1.0])
    pad = (hi - lo) * 0.05 or 0.05
    lo, hi = lo - pad, hi + pad
    x = lambda i: L + (W - L - R) * i / (len(dates) - 1)
    y = lambda v: Tp + (H - Tp - B) * (hi - v) / (hi - lo)
    colors = {"long_excess": "var(--accent)", "long_short": "var(--muted)"}
    out = [f"<svg viewBox='0 0 {W} {H}' class='chart' role='img' style='width:100%;height:auto;margin:6px 0'>"]
    ticks = [1.0] + [v for v in (lo + pad, hi - pad) if abs(v - 1.0) > (hi - lo) * 0.12]
    for v in ticks:
        grid_dash = " stroke-dasharray='3 3'" if v == 1.0 else ""
        out.append(f"<line x1='{L}' x2='{W - R}' y1='{y(v):.1f}' y2='{y(v):.1f}' stroke='var(--line)'{grid_dash}/>"
                   f"<text x='{L - 6}' y='{y(v) + 4:.1f}' text-anchor='end' font-size='11' fill='var(--muted)'>{v:.2f}</text>")
    for i in (0, len(dates) // 2, len(dates) - 1):
        anchor = "start" if i == 0 else ("end" if i == len(dates) - 1 else "middle")
        out.append(f"<text x='{x(i):.1f}' y='{H - 6}' text-anchor='{anchor}' font-size='11' fill='var(--muted)'>{dates[i][:7]}</text>")
    for k, ys in series:
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(ys) if v is not None)
        dash = " stroke-dasharray='5 4'" if k == "long_short" else ""
        out.append(f"<polyline points='{pts}' fill='none' stroke='{colors[k]}' stroke-width='2'{dash}/>")
    out.append("</svg>")
    legend = " ".join(f"<span style='color:{colors[k]}'>{'━━' if k == 'long_excess' else '╍╍'} {_e(labels[k])}</span>"
                      for k, _ in series)
    return "".join(out) + f"<p class='note'>{legend}</p>"


def _backtest_html(b: dict, T: dict, lang: str) -> str:
    if not b or not b.get("n_long"):
        return f"<p class='note'>{_e(T['b_none'])}</p>"
    p, c = b["params"], b["params"].get("costs", {})
    duty = ""
    if c.get("stamp_duty"):
        d = f"{100 * c['stamp_duty']:.2f}%"
        if c.get("stamp_duty_cut"):
            d += f" → {100 * c['stamp_duty_after']:.2f}% ({c['stamp_duty_cut']})"
        duty = T["b_duty"].format(duty=d)
    rules = T["b_rules_cn"] if p.get("market") == "cn" else T["b_rules_us"]
    intro = T["b_intro"].format(long=p["long_sue"], hold=p["hold"],
                                comm=f"{100 * c.get('commission', 0):.3f}%",
                                slip=f"{100 * c.get('slippage', 0):.2f}%", duty=duty, rules=rules)
    out = [f"<p class='big'>{_e(intro)}</p>"]
    cols = "".join(f"<th>{_e(x)}</th>" for x in T["b_cols"])
    rows = []
    for key in ("long_excess", "long_excess_gross", "long", "bench", "long_short", "long_short_gross"):
        st = b.get(key) or {}
        if "ann_return" not in st:
            continue
        label = T["b_rows"][key].format(short=p["short_sue"])
        strong = " class='row-total'" if key == "long_excess" else ""
        rows.append(f"<tr><td{strong}>{_e(label)}</td><td class='pct'>{_pct(st['ann_return'])}</td>"
                    f"<td class='num'>{100 * st['ann_vol']:.1f}%</td><td class='num'>{st['sharpe']:.2f}</td>"
                    f"<td class='num'>{_t(st['t']).replace('t=', '') or '—'}</td><td class='pct'>{_pct(st['max_dd'])}</td></tr>")
    out.append(f"<div class='wide'><table><tr>{cols}</tr>{''.join(rows)}</table></div>")
    if b.get("slots"):
        out.append(f"<p class='note'>{_e(T['b_slots'].format(slots=b['slots'], pos=b.get('avg_positions') or 0))}</p>")
    lt, sh = b.get("long_trade") or {}, b.get("short_trade") or {}
    if lt:
        out.append("<p class='callout'>" + _e(T["b_trades"].format(
            lm=_pct(lt.get("mean")), lw=f"{100 * lt.get('win', 0):.0f}%", ln=lt.get("n"), lt=_num(lt.get("t"), "{:.1f}"),
            sm=_pct(sh.get("mean")), sn=sh.get("n", 0), st=_num(sh.get("t"), "{:.1f}"))) + "</p>")
    if b.get("curve"):
        out.append(f"<h3>{_e(T['b_curve'])}</h3>")
        out.append(_line_chart(b["curve"], {"long_excess": T["b_rows"]["long_excess"],
                                            "long_short": T["b_rows"]["long_short"].format(short=p["short_sue"])}))
    if b.get("years"):
        yrs = b["years"]
        head = "".join(f"<th>{y['year']}</th>" for y in yrs)
        body = ""
        for key in ("long_excess", "long_short"):
            body += (f"<tr><td style='white-space:nowrap'>{_e(T['b_short'][key])}</td>"
                     + "".join(f"<td class='pct'>{_pct(y.get(key))}</td>" for y in yrs) + "</tr>")
        out.append(f"<h3>{_e(T['b_years'])}</h3><div class='wide'><table><tr><th></th>{head}</tr>{body}</table></div>")
    if b.get("sweep"):
        cols = "".join(f"<th>{_e(x)}</th>" for x in T["b_sweep_cols"])
        body = "".join(
            f"<tr><td>±{r['sue']:g}</td><td class='num'>{r['hold']}</td><td class='num'>{r['trades']}</td>"
            f"<td class='pct'>{_pct(r.get('ann_excess'))}</td><td class='num'>{_num(r.get('t'), '{:.1f}')}</td>"
            f"<td class='pct'>{_pct(r.get('per_trade'))}</td>"
            f"<td class='num'>{_share(r.get('win'))}</td>"
            f"<td class='pct'>{_pct(r.get('ls_ann'))}</td></tr>" for r in b["sweep"])
        out.append(f"<details><summary>{_e(T['b_sweep'])}</summary><div class='wide'><table><tr>{cols}</tr>{body}</table></div></details>")
    return "".join(out)

def build_research_report(res: dict, *, lang: str = "en", files: list[str] | None = None) -> str:
    T = TEXT.get(lang, TEXT["en"])
    lang = lang if lang in TEXT else "en"
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    p = res.get("prices", {})
    meta = [T["generated"].format(time=now)]
    if p:
        meta.append(T["prices"].format(n=p["n"], start=p["start"], end=p["end"]))
        bench = {"SPY": T["bench_spy"], "CSI300": T["bench_csi"]}.get(p.get("bench") or ("SPY" if p.get("spy") else ""),
                                                                     T["bench_ew"])
        meta.append(T["bench"].format(bench=bench))
    parts = [f"<header><h1>{_e(T['title'])}</h1><p>{_e(T['subtitle'])}</p>"
             f"<div class='meta'>{''.join(f'<span>{_e(m)}</span>' for m in meta)}</div></header>"]

    # ---- earnings
    e = res.get("earnings", {})
    sec = [f"<h2>{_e(T['e_title'])}</h2>"]
    if not e or not e.get("n"):
        sec.append(f"<p class='note'>{_e(T['e_none'])}</p>")
    else:
        sec.append(f"<p class='big'>{_e(T['e_intro'].format(n=e['n'], stocks=e.get('n_stocks', '?')))}</p>")
        sec.append(f"<h3>{_e(T['e_dates_title'])}</h3>")
        is_cn = e.get("market") == "cn"
        dates_txt = T["e_dates_cn"] if is_cn else T["e_dates"]
        sec.append(f"<p class='note'>{_e(dates_txt.format(n=e['n'], n_8k=e.get('n_8k', 0)))}</p>")
        sec.append("<div class='cmp'>")
        keys = (("8-K", "src_actual"), ("10-Q", "src_deadline")) if is_cn else (("8-K", "src_8k"), ("10-Q", "src_10q"))
        for src, key in keys:
            sec.append(f"<div><p><b>{_e(T[key])}</b></p>"
                       f"{_bucket_html(e['by_source'].get(src), ('reaction', 'drift'), lang, bars=False)}</div>")
        sec.append("</div>")
        sec.append(f"<h3>{_e(T['e_sue_title'])}</h3>")
        sec.append(_bucket_html(e.get("sue_table"), ("reaction", "drift"), lang))
        rg = e.get("reg_sue", {})
        if rg.get("reaction", {}).get("coef"):
            r1, r2 = rg["reaction"], rg["drift"]
            sec.append("<p class='callout'>" + _e(T["e_reg"].format(
                b1=_pct(r1["coef"].get("sue_c")), t1=_num(r1["t"].get("sue_c"), "{:.1f}"),
                b2=_pct(r2["coef"].get("sue_c")), t2=_num(r2["t"].get("sue_c"), "{:.1f}"))) + "</p>")
        if e.get("halves"):
            sec.append(f"<details><summary>{_e(T['e_halves'])}</summary><div class='cmp'>")
            for name, tab in e["halves"].items():
                sec.append(f"<div><p><b>{_e(name)}</b></p>{_bucket_html(tab, ('reaction', 'drift'), lang, bars=False)}</div>")
            sec.append("</div></details>")
    parts.append(f"<section class='card'>{''.join(sec)}</section>")

    # ---- LLM tone
    sec = [f"<h2>{_e(T['tone_title'])}</h2>"]
    if e.get("market") == "cn" and not e.get("n_tone"):
        sec.append(f"<p class='note'>{_e(T['tone_cn'])}</p>")
    elif not e.get("n_tone"):
        sec.append(f"<p class='note'>{T['tone_none']}</p>")
    else:
        a, b = e["tone_dates"]
        sec.append(f"<p class='big'>{_e(T['tone_intro'].format(n=e['n_tone'], start=a, end=b))}</p>")
        sec.append(f"<h3>{_e(T['tone_by'])}</h3>")
        sec.append(_bucket_html(e["tone_table"], ("reaction", "drift"), lang))
        sec.append(f"<h3>{_e(T['reg_title'])}</h3>")
        cols = "".join(f"<th>{_e(c)}</th>" for c in T["reg_cols"])
        rows = []
        for outcome in ("reaction", "drift"):
            for name, m in e["reg_tone"][outcome].items():
                c, tt = m["coef"], m["t"]
                rows.append(
                    f"<tr><td>{_e(T[outcome])}: {_e(name)}</td><td class='num'>{m['n']}</td>"
                    f"<td class='pct'>{_pct(c.get('sue_c'))}{_t(tt.get('sue_c'))}</td>"
                    f"<td class='pct'>{_pct(c.get('tone')) if 'tone' in c else ''}{_t(tt.get('tone'))}</td>"
                    f"<td class='num'>{_num(m['r2'], '{:.3f}')}</td></tr>")
        sec.append(f"<div class='wide'><table><tr>{cols}</tr>{''.join(rows)}</table></div>")
        if e.get("guidance_table") is not None and len(e["guidance_table"]):
            sec.append(f"<h3>{_e(T['guid_title'])}</h3>")
            sec.append(_bucket_html(e["guidance_table"].assign(), ("reaction", "drift"), lang, first_col="guidance"))
    parts.append(f"<section class='card'>{''.join(sec)}</section>")

    # ---- backtest
    if res.get("backtest") is not None or e.get("n"):
        parts.append(f"<section class='card'><h2>{_e(T['b_title'])}</h2>"
                     f"{_backtest_html(res.get('backtest') or {}, T, lang)}</section>")

    # ---- news
    n = res.get("news", {})
    sec = [f"<h2>{_e(T['n_title'])}</h2>"]
    if not n.get("n"):
        sec.append(f"<p class='note'>{_e(T['n_none'])}</p>")
    else:
        a, b = n["dates"]
        sec.append(f"<p class='big'>{_e(T['n_intro'].format(n=n['n'], stocks=n['n_stocks'], start=a, end=b))}</p>")
        if n["n_d1_5"] < 200:
            sec.append(f"<p class='callout'>{_e(T['n_thin'].format(n1=n['n_d1'], n5=n['n_d1_5']))}</p>")
        sec.append(_bucket_html(n["table"], ("d_1", "d0", "d1", "d1_5"), lang))
    parts.append(f"<section class='card'>{''.join(sec)}</section>")

    # ---- caveats
    cav = "".join(f"<li>{_e(c)}</li>" for c in T["caveats"])
    foot = f"<p class='note'>{_e(T['t_note'])}</p>"
    if files:
        foot += f"<p class='note'>{_e(T['files'].format(files=', '.join(files)))}</p>"
    parts.append(f"<section class='card'><h2>{_e(T['cav_title'])}</h2><ul class='caveats'>{cav}</ul>{foot}</section>")

    return (f"<!doctype html><html lang='{'zh-CN' if lang == 'zh' else 'en'}'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'><title>{_e(T['title'])}</title>"
            f"<style>{CSS}{EXTRA_CSS}h3{{font-size:14px;margin:18px 0 8px;}}</style></head>"
            f"<body><div class='wrap'>{''.join(parts)}</div></body></html>")
