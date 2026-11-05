"""
Paper trading with deliberately pessimistic fills, and a record that can't be edited.

Fills (A-shares; US the same minus limits, T+1 and lots):
  * an order placed on day D executes at the OPEN of the next trading day, never at the price seen
    when it was placed;
  * no buy when the stock opens at its limit-up, no sell when it opens at limit-down; the order waits
    up to 5 trading days (suspended days count too), then is cancelled with the reason;
  * at most 5% of that day's volume; the rest is cancelled;
  * slippage 0.1% plus market impact that grows with the order's share of the day's turnover;
  * commission (minimum 5 yuan), stamp duty on sales (halved from 2023-08-28), lots of 100, T+1.

Orders, fills and accounts are append-only: database triggers refuse UPDATE and DELETE, so the
public track record can't be tidied up afterwards.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import uuid

import numpy as np
import pandas as pd

from stockproof import cn, quotes
from stockproof.backtest import COSTS, price_limit

MAX_WAIT = 5            # trading days an order waits for a fillable open
VOLUME_CAP = 0.05       # share of the day's volume one order may take
MIN_COMMISSION = 5.0    # yuan, A-shares

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_accounts (
    id TEXT PRIMARY KEY, name TEXT, created_at TEXT, start_day TEXT, cash REAL, market TEXT, kind TEXT,
    spec TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS paper_orders (
    id TEXT PRIMARY KEY, account TEXT, ticker TEXT, side TEXT, shares INTEGER, value REAL, created_at TEXT,
    created_day TEXT, source TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS paper_fills (
    order_id TEXT PRIMARY KEY, day TEXT, status TEXT, price REAL, shares INTEGER, gross REAL, cost REAL,
    reason TEXT, recorded_at TEXT);
"""
SCHEMA += "CREATE TABLE IF NOT EXISTS paper_marks (account TEXT, day TEXT, kind TEXT, detail TEXT);\n"
for _t in ("paper_accounts", "paper_orders", "paper_fills", "paper_marks"):
    SCHEMA += (f"CREATE TRIGGER IF NOT EXISTS {_t}_no_update BEFORE UPDATE ON {_t} "
               f"BEGIN SELECT RAISE(ABORT, 'paper records are append-only'); END;\n"
               f"CREATE TRIGGER IF NOT EXISTS {_t}_no_delete BEFORE DELETE ON {_t} "
               f"BEGIN SELECT RAISE(ABORT, 'paper records are append-only'); END;\n")


def _init(store):
    store.conn.executescript(SCHEMA)


def market_day(ticker: str, now: dt.datetime | None = None) -> str:
    """Today's date where the stock trades (an order placed in California at 20:00 is already the next
    morning in Shanghai)."""
    from zoneinfo import ZoneInfo
    tz = "Asia/Shanghai" if cn.is_cn(ticker) else "America/New_York"
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    return now.astimezone(ZoneInfo(tz)).date().isoformat()


def lot(ticker: str) -> int:
    return 100 if cn.is_cn(ticker) else 1


# ---------------------------------------------------------------- accounts and orders
def create_account(store, name: str, cash: float = 1_000_000.0, market: str = "cn", kind: str = "manual",
                   spec: dict | None = None, note: str = "", start_day: str | None = None) -> str:
    _init(store)
    aid = uuid.uuid4().hex[:8]
    start_day = start_day or market_day("600000.SH" if market == "cn" else "AAPL")
    store.conn.execute("INSERT INTO paper_accounts VALUES (?,?,?,?,?,?,?,?,?)",
                       (aid, str(name)[:60], dt.datetime.now().isoformat(timespec="seconds"), start_day, float(cash),
                        market, kind, json.dumps(spec, ensure_ascii=False) if spec else None, str(note)[:300]))
    store.conn.commit()
    return aid


def accounts(store) -> list[dict]:
    _init(store)
    cur = store.conn.execute("SELECT id, name, created_at, start_day, cash, market, kind, spec, note FROM paper_accounts "
                             "ORDER BY created_at")
    cols = [c[0] for c in cur.description]
    out = [dict(zip(cols, r)) for r in cur.fetchall()]
    for a in out:
        a["spec"] = json.loads(a["spec"]) if a["spec"] else None
    return out


def account(store, aid: str) -> dict | None:
    return next((a for a in accounts(store) if a["id"] == aid), None)


def place(store, aid: str, ticker: str, side: str, shares: int = 0, value: float = 0.0, source: str = "manual",
          note: str = "", now: dt.datetime | None = None) -> str:
    """Queue an order; it fills (or not) at a later open. Give `shares` (rounded down to a lot) or `value`."""
    _init(store)
    if side not in ("buy", "sell"):
        raise ValueError("side must be buy or sell")
    if not account(store, aid):
        raise ValueError("no such paper account")
    if cn.is_cn(ticker) and cn.parse(ticker)["market"] == "HK":
        raise ValueError("Hong Kong stocks are not supported in paper trading yet")
    lt = lot(ticker)
    shares = int(shares) // lt * lt if shares else 0
    if not shares and not value and side == "buy":
        raise ValueError("give shares or value")
    oid = uuid.uuid4().hex[:10]
    store.conn.execute("INSERT INTO paper_orders VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (oid, aid, ticker, side, shares, float(value or 0), (now or dt.datetime.now()).isoformat(timespec="seconds"),
                        market_day(ticker, now), source, str(note)[:200]))
    store.conn.commit()
    return oid


def orders(store, aid: str) -> pd.DataFrame:
    _init(store)
    return pd.read_sql_query(
        "SELECT o.*, f.day AS fill_day, f.status, f.price, f.shares AS filled, f.gross, f.cost, f.reason "
        "FROM paper_orders o LEFT JOIN paper_fills f ON f.order_id = o.id WHERE o.account = ? ORDER BY o.created_at",
        store.conn, params=(aid,))


# ---------------------------------------------------------------- filling
def _bars(data_dir: str, ticker: str, fetch: bool) -> pd.DataFrame:
    b = quotes.load_bars(data_dir, ticker)
    if fetch:
        try:
            quotes.update(data_dir, ticker)
            b = quotes.load_bars(data_dir, ticker)
        except Exception:
            pass
    return b


def _calendar(data_dir: str, market: str, fetch: bool) -> pd.DatetimeIndex:
    bm = quotes.BENCH["A" if market == "cn" else "US"]
    s = quotes.load(data_dir, bm)
    if fetch:
        try:
            quotes.update(data_dir, bm)
            s = quotes.load(data_dir, bm)
        except Exception:
            pass
    if len(s):
        return pd.DatetimeIndex(s.index)
    return pd.bdate_range(dt.date.today() - dt.timedelta(days=400), dt.date.today())   # no index file yet: weekdays


def _holdings_before(fills: pd.DataFrame, ticker: str, day: pd.Timestamp) -> int:
    """Shares held at the open of `day`: fills strictly before it (T+1: today's buys can't be sold today)."""
    f = fills[(fills["ticker"] == ticker) & (fills["status"] == "filled") & (pd.to_datetime(fills["day"]) < day)]
    return int((f["shares"] * np.where(f["side"] == "buy", 1, -1)).sum()) if len(f) else 0


def _cash_before(acct: dict, fills: pd.DataFrame, day: pd.Timestamp) -> float:
    f = fills[(fills["status"] == "filled") & (pd.to_datetime(fills["day"]) <= day)]
    flow = np.where(f["side"] == "buy", -(f["gross"] + f["cost"]), f["gross"] - f["cost"])
    return float(acct["cash"] + flow.sum())


def _fills_frame(store, aid: str) -> pd.DataFrame:
    return pd.read_sql_query("SELECT f.*, o.ticker, o.side FROM paper_fills f JOIN paper_orders o ON o.id = f.order_id "
                             "WHERE o.account = ?", store.conn, params=(aid,))


def _record(store, oid: str, day, status: str, price=None, shares=0, gross=0.0, cost=0.0, reason=""):
    store.conn.execute("INSERT INTO paper_fills VALUES (?,?,?,?,?,?,?,?,?)",
                       (oid, None if day is None else pd.Timestamp(day).date().isoformat(), status, price, int(shares),
                        float(gross), float(cost), reason, dt.datetime.now().isoformat(timespec="seconds")))


def process(store, data_dir: str, fetch: bool = True, log=print) -> dict:
    """Try every pending order against the opens that have happened since it was placed."""
    _init(store)
    pend = pd.read_sql_query("SELECT o.* FROM paper_orders o WHERE o.id NOT IN (SELECT order_id FROM paper_fills) "
                             "ORDER BY o.created_at", store.conn)
    done = {"filled": 0, "cancelled": 0, "waiting": 0}
    cals: dict[str, pd.DatetimeIndex] = {}
    bars_cache: dict[str, pd.DataFrame] = {}
    for o in pend.itertuples():
        acct = account(store, o.account)
        mkt = acct["market"]
        cal = cals.setdefault(mkt, _calendar(data_dir, mkt, fetch))
        b = bars_cache.get(o.ticker)
        if b is None:
            b = bars_cache[o.ticker] = _bars(data_dir, o.ticker, fetch)
        placed = pd.Timestamp(o.created_day)
        window = cal[cal > placed][:MAX_WAIT]                      # the trading days it may fill on
        costs = COSTS["cn" if cn.is_cn(o.ticker) else "us"]
        outcome = None
        last_bar = b.index.max() if len(b) else None
        window = window[window <= last_bar] if last_bar is not None else window[:0]   # days we have data for
        for d in window:
            if d not in b.index or pd.isna(b.at[d, "open"]):
                continue                                           # suspended that day
            prev = b["close"].loc[:d].iloc[:-1].dropna()
            prev_close = float(prev.iloc[-1]) if len(prev) else None
            op = float(b.at[d, "open"])
            lim = price_limit(o.ticker, d)
            if lim and prev_close:
                if o.side == "buy" and op >= prev_close * (1 + lim) * 0.997:
                    continue                                       # opened at limit-up: can't buy
                if o.side == "sell" and op <= prev_close * (1 - lim) * 1.003:
                    continue                                       # opened at limit-down: can't sell
            vol = b.at[d, "volume"] if "volume" in b and pd.notna(b.at[d, "volume"]) else None
            vol_shares = None if vol is None else float(vol) * (100 if cn.is_cn(o.ticker) else 1)   # lots -> shares
            fills = _fills_frame(store, o.account)
            lt = lot(o.ticker)
            if o.side == "sell":
                have = _holdings_before(fills, o.ticker, d)
                want = min(int(o.shares) if o.shares else have, have)
            else:
                want = int(o.shares) if o.shares else int(o.value / (op * 1.002) // lt * lt)
            cap = int(vol_shares * VOLUME_CAP // lt * lt) if vol_shares else want
            n = min(want, cap)
            reason = "" if n == want else f"volume cap: {VOLUME_CAP:.0%} of the day's volume"
            turnover = (vol_shares or 0) * op
            impact = 0.5 * (n * op / turnover) if turnover else 0.0
            px = op * (1 + costs.slippage + impact) if o.side == "buy" else op * (1 - costs.slippage - impact)
            if o.side == "buy":
                cash = _cash_before(acct, fills, d)
                fee = lambda k: max(MIN_COMMISSION if cn.is_cn(o.ticker) else 0.0, k * px * costs.commission)
                while n > 0 and n * px + fee(n) > cash:
                    n -= lt
                if n < int(o.shares or want):
                    reason = reason or "not enough cash"
            if n <= 0:
                why = ("nothing to sell (T+1: shares bought today can't be sold today)" if o.side == "sell"
                       else reason or "order smaller than one lot")
                outcome = ("cancelled", d, None, 0, 0.0, 0.0, why)
                break
            gross = n * px
            commission = max(MIN_COMMISSION if cn.is_cn(o.ticker) else 0.0, gross * costs.commission)
            duty = gross * (costs.sell(d) - costs.commission - costs.slippage) if o.side == "sell" else 0.0
            outcome = ("filled", d, round(px, 4), n, gross, commission + max(duty, 0.0), reason)
            break
        if outcome is None:
            if len(window) >= MAX_WAIT:
                outcome = ("cancelled", window[-1], None, 0, 0.0, 0.0,
                           f"no fillable open in {MAX_WAIT} trading days (limit or suspended)")
            else:
                done["waiting"] += 1
                continue
        _record(store, o.id, outcome[1], outcome[0], outcome[2], outcome[3], outcome[4], outcome[5], outcome[6])
        store.conn.commit()
        done["filled" if outcome[0] == "filled" else "cancelled"] += 1
    return done


# ---------------------------------------------------------------- the record
def state(store, data_dir: str, aid: str, fetch: bool = False) -> dict:
    """Positions, cash, daily value vs the market, and every order with its outcome."""
    acct = account(store, aid)
    if not acct:
        return {"error": "no such account"}
    od = orders(store, aid)
    f = od[od["status"] == "filled"].copy()
    cal = _calendar(data_dir, acct["market"], fetch)
    start = pd.Timestamp(acct["start_day"])
    days = cal[cal >= start]
    if not len(days):
        days = pd.DatetimeIndex([start])
    tickers = sorted(set(f["ticker"])) if len(f) else []
    closes = pd.DataFrame({t: quotes.load(data_dir, t) for t in tickers}).reindex(days).ffill() if tickers else pd.DataFrame(index=days)
    pos = pd.DataFrame(0.0, index=days, columns=tickers)
    cash = pd.Series(acct["cash"], index=days, dtype=float)
    for r in f.itertuples():
        d = pd.Timestamp(r.fill_day)
        sign = 1 if r.side == "buy" else -1
        if tickers:
            pos.loc[pos.index >= d, r.ticker] += sign * r.filled
        cash.loc[cash.index >= d] += -(r.gross + r.cost) if r.side == "buy" else (r.gross - r.cost)
    value = cash + (pos * closes).sum(axis=1) if tickers else cash
    bm = quotes.load(data_dir, quotes.BENCH["A" if acct["market"] == "cn" else "US"])
    bm = bm[~bm.index.duplicated()].reindex(days).ffill() if len(bm) else pd.Series(np.nan, index=days)
    nav = value / acct["cash"]
    bnav = bm / bm.dropna().iloc[0] if bm.notna().any() else pd.Series(np.nan, index=days)
    last = pos.iloc[-1] if tickers else pd.Series(dtype=float)
    holdings = [{"ticker": t, "shares": int(last[t]), "price": round(float(closes[t].iloc[-1]), 3) if pd.notna(closes[t].iloc[-1]) else None,
                 "value": float(last[t] * closes[t].iloc[-1]) if pd.notna(closes[t].iloc[-1]) else None}
                for t in tickers if last[t]]
    dd = float((nav / nav.cummax() - 1).min()) if len(nav) else 0.0
    out = {"account": {k: acct[k] for k in ("id", "name", "created_at", "start_day", "cash", "market", "kind", "spec", "note")},
           "as_of": days[-1].date().isoformat(), "value": float(value.iloc[-1]), "cash": float(cash.iloc[-1]),
           "return": float(nav.iloc[-1] - 1), "benchmark_return": float(bnav.iloc[-1] - 1) if pd.notna(bnav.iloc[-1]) else None,
           "max_drawdown": dd, "holdings": holdings,
           "nav": [[d.date().isoformat(), round(float(v), 5), None if pd.isna(b) else round(float(b), 5)]
                   for d, v, b in zip(days, nav, bnav)],
           "orders": json.loads(od.to_json(orient="records", force_ascii=False)),
           "costs_paid": float(f["cost"].sum()) if len(f) else 0.0,
           "cancelled": int((od["status"] == "cancelled").sum()), "pending": int(od["status"].isna().sum()),
           "rules": ("成交规则：下一个交易日开盘成交；开盘涨停不买、跌停不卖，最多等 5 个交易日；每笔最多当天成交量的 5%；"
                     "滑点 0.1% 加冲击成本；佣金最低 5 元、卖出印花税；100 股一手；T+1。记录只能追加，不能修改。")}
    if out["benchmark_return"] is not None:
        out["excess"] = out["return"] - out["benchmark_return"]
    return out


# ---------------------------------------------------------------- strategy accounts
EVENT_TYPES = ("earnings", "forecast", "smart_money")


def strategy_events(data_dir: str, spec: dict, log=print) -> pd.DataFrame:
    """The lab's event table for an event strategy, with its filters applied (ticker, day0, ...)."""
    from stockproof import lab
    spec = lab.validate(spec)
    t = spec["type"]
    if t not in EVENT_TYPES:
        raise lab.SpecError("paper strategy accounts support earnings, forecast and smart_money strategies")
    if t == "earnings":
        ev = lab.earnings_events(data_dir, spec["market"])
    elif t == "smart_money":
        from stockproof import flows
        ev = flows.events(data_dir, log=log)
    else:
        ev = lab.forecast_events(data_dir, log=log)
    if ev is None or not len(ev):
        return pd.DataFrame(columns=["ticker", "day0"])
    return lab.apply_filters(ev, spec["filters"])


def spec_from_experiment(data_dir: str, exp_id: str) -> dict:
    """The spec of a lab experiment, plus what its backtest said (to compare with the paper result later)."""
    from stockproof import lab
    for r in reversed(lab.trials(data_dir)):
        if r.get("id") == exp_id and "spec" in r:
            return {**r["spec"], "exp_id": exp_id, "backtest_ann": r.get("ann"), "backtest_t": r.get("t")}
    raise lab.SpecError(f"no lab experiment {exp_id}: see `stockproof lab list`")


def find_account(store, ref: str) -> dict | None:
    """By id, or by name (the latest account with that name)."""
    acc = accounts(store)
    return next((a for a in acc if a["id"] == ref), None) or next((a for a in reversed(acc) if a["name"] == ref), None)


def create_strategy_account(store, data_dir: str, spec: dict, cash: float = 1_000_000.0, name: str | None = None,
                            lang: str = "zh") -> str:
    """A paper account that follows a lab strategy from today on: every new matching event is bought at the
    next open (cash / slots each), and sold `hold_days` trading days after the fill."""
    from stockproof import lab
    extra = {k: spec[k] for k in ("exp_id", "backtest_ann", "backtest_t") if k in spec}
    spec = {**lab.validate(spec), **extra}
    if spec["type"] not in EVENT_TYPES:
        raise lab.SpecError("paper strategy accounts support earnings, forecast and smart_money strategies")
    return create_account(store, name or spec.get("name") or lab.describe_spec(spec, lang)[:60], cash, spec["market"],
                          "strategy", spec, note=lab.describe_spec(spec, lang))


def step_strategy(store, data_dir: str, aid: str, events: pd.DataFrame | None = None, now: dt.datetime | None = None,
                  fetch: bool = False, log=print) -> dict:
    """Queue today's entries and exits for a strategy account. Events are only acted on once they are known
    (day0 on or after the account's start, never in the future), and the order is dated when it is placed."""
    acct = account(store, aid)
    spec = acct["spec"]
    ev = strategy_events(data_dir, spec, log) if events is None else events
    od = orders(store, aid)
    seen = set(od["source"])
    today = market_day("600000.SH" if acct["market"] == "cn" else "AAPL", now)
    ev = ev[(pd.to_datetime(ev["day0"]) >= pd.Timestamp(acct["start_day"])) & (pd.to_datetime(ev["day0"]) <= pd.Timestamp(today))]
    filled = od[(od["status"] == "filled")]
    buys = filled[filled["side"] == "buy"]
    exits_placed = {s.split(":", 1)[1] for s in seen if isinstance(s, str) and s.startswith("exit:")}
    open_lots = [r for r in buys.itertuples() if r.id not in exits_placed]
    pending_buys = int(((od["side"] == "buy") & od["status"].isna()).sum())
    placed = {"buy": 0, "sell": 0, "skipped_full": 0}
    cal = _calendar(data_dir, acct["market"], fetch)
    for r in open_lots:                                            # exits first
        held = int(((cal > pd.Timestamp(r.fill_day)) & (cal <= pd.Timestamp(today))).sum())
        if held >= spec["hold_days"]:
            place(store, aid, r.ticker, "sell", shares=int(r.filled), source=f"exit:{r.id}",
                  note=f"held {held} trading days", now=now)
            placed["sell"] += 1
    slots_used = len(open_lots) - placed["sell"] + pending_buys
    for e in ev.sort_values("day0").itertuples():
        key = f"strategy:{e.ticker}:{pd.Timestamp(e.day0).date().isoformat()}"
        if key in seen:
            continue
        if slots_used >= spec["slots"]:
            placed["skipped_full"] += 1
            continue
        if cn.is_cn(e.ticker) and cn.parse(e.ticker)["market"] == "HK":
            continue
        place(store, aid, e.ticker, "buy", value=acct["cash"] / spec["slots"], source=key, now=now)
        seen.add(key)
        slots_used += 1
        placed["buy"] += 1
    return placed


def gap(store, data_dir: str, aid: str) -> dict:
    """Backtest vs paper, trade by trade: what the backtest's fill rule (close of the day after the signal, standard
    costs) would have earned on the same signals, against what the paper fills actually got."""
    acct = account(store, aid)
    od = orders(store, aid)
    if acct is None:
        return {"error": "no such account"}
    spec = acct["spec"] or {}
    lag = int(spec.get("entry_lag", 1))
    costs = COSTS[acct["market"]]
    rows, missed = [], 0
    by_id = od.set_index("id")
    for b in od[(od["side"] == "buy")].itertuples():
        if b.status == "cancelled":
            missed += 1
            continue
        if b.status != "filled":
            continue
        ex = od[(od["source"] == f"exit:{b.id}") & (od["status"] == "filled")]
        if not len(ex):
            continue
        s = ex.iloc[0]
        paper = (s["gross"] - s["cost"]) / (b.gross + b.cost) - 1
        px = quotes.load(data_dir, b.ticker).dropna()
        sig = pd.Timestamp(str(b.source).split(":")[-1]) if str(b.source).startswith("strategy:") else pd.Timestamp(b.created_day)
        after = px[px.index >= sig]
        exit_day = pd.Timestamp(s["fill_day"])
        if len(after) <= lag or exit_day not in px.index:
            continue
        ideal = (px.loc[exit_day] * (1 - costs.sell(exit_day))) / (after.iloc[lag] * (1 + costs.buy(sig))) - 1
        rows.append({"ticker": b.ticker, "signal": sig.date().isoformat(), "entry": b.fill_day, "exit": s["fill_day"],
                     "backtest_rule": float(ideal), "paper": float(paper), "gap": float(paper - ideal)})
    df = pd.DataFrame(rows)
    out = {"trades": rows, "round_trips": len(rows), "missed_entries": missed,
           "note": ("回测规则：信号后第 1 个交易日收盘买、标准成本；模拟盘：下一个交易日开盘、涨跌停不成交、量能上限、冲击成本。"
                    "差距就是回测里“看起来能赚”和实际能成交之间的距离。")}
    if spec.get("backtest_ann") is not None:
        out["lab_backtest_ann_excess"] = spec["backtest_ann"]
    if len(df):
        out.update(avg_backtest_rule=float(df["backtest_rule"].mean()), avg_paper=float(df["paper"].mean()),
                   avg_gap=float(df["gap"].mean()))
    return out


def from_team_call(store, aid: str, call: dict, value: float, now: dt.datetime | None = None) -> str | None:
    """Turn an AI research-team call into a paper order (bullish = buy, bearish = sell what is held). The user
    asks for this; nothing is placed automatically, and never with real money."""
    stance = (call.get("final") or {}).get("stance")
    tk = call["ticker"]
    if stance == "bullish":
        return place(store, aid, tk, "buy", value=value, source=f"team:{call.get('call_id', '')}", now=now)
    if stance == "bearish":
        return place(store, aid, tk, "sell", shares=0, source=f"team:{call.get('call_id', '')}", now=now)
    return None


# ---------------------------------------------------------------- forecast model portfolios
def create_forecast_account(store, data_dir: str, horizon: str = "6m", n: int = 50, cash: float = 1_000_000.0,
                            name: str | None = None, lang: str = "zh") -> str:
    """A paper account that holds the forecaster's top `n` stocks, equal weight, and rebalances every
    `rebalance` trading days (63 = a quarter). Its record shows whether the model works from today on."""
    from stockproof import forecast as fc
    res = fc.load(data_dir)
    if res is None or horizon not in res.get("horizons", {}):
        raise ValueError("no forecast yet: run `stockproof forecast` first")
    r = res["horizons"][horizon]
    zh = lang == "zh"
    spec = {"type": "forecast", "horizon": horizon, "n": int(n), "rebalance": 63, "market": "cn",
            "status_at_start": r.get("status"), "backtest_net_per_year": (r.get("explore") or {}).get("net_per_year")}
    hz = {"3m": "3 个月", "6m": "6 个月", "12m": "12 个月"}.get(horizon, horizon)
    note = (f"中长期预测（{hz}）排名前 {n} 只，等权，每季度调仓；开户时模型状态：{fc.STATUS_ZH.get(r.get('status'), '')}" if zh else
            f"Forecaster ({horizon}) top {n}, equal weight, rebalanced quarterly; model at start: {fc.STATUS_EN.get(r.get('status'), '')}")
    return create_account(store, name or (f"预测前{n}（{hz}）" if zh else f"Forecast top {n} ({horizon})"), cash, "cn",
                          "forecast", spec, note=note)


def step_forecast(store, data_dir: str, aid: str, now: dt.datetime | None = None, fetch: bool = False,
                  scores: dict | None = None) -> dict:
    """On the first day and then every `rebalance` trading days: sell holdings that left the top `n`, buy the
    new ones for an equal share of the account's value. Uses the latest saved forecast (refit monthly)."""
    from stockproof import forecast as fc
    acct = account(store, aid)
    spec = acct["spec"]
    od = orders(store, aid)
    today = market_day("600000.SH", now)
    cal = _calendar(data_dir, "cn", fetch)
    _init(store)
    marks = store.conn.execute("SELECT day FROM paper_marks WHERE account=? AND kind='rebalance' ORDER BY day DESC LIMIT 1",
                               (aid,)).fetchone()
    if marks:
        last = pd.Timestamp(marks[0])
        if int(((cal > last) & (cal <= pd.Timestamp(today))).sum()) < spec["rebalance"]:
            return {"rebalance": False}
    if od["status"].isna().any():
        return {"rebalance": False, "waiting": int(od["status"].isna().sum())}
    if scores is None:
        res = fc.load(data_dir) or {}
        st = (res.get("horizons", {}).get(spec["horizon"]) or {}).get("stocks") or {}
        scores = {tk: v["pct"] for tk, v in st.items()}
    if not scores:
        return {"error": "no forecast scores"}
    target = [tk for tk, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:spec["n"]]]
    s = state(store, data_dir, aid)
    held = {h["ticker"]: h for h in s["holdings"]}
    key = f"rebalance:{today}"
    sold = bought = 0
    for tk in held:
        if tk not in target:
            place(store, aid, tk, "sell", shares=0, source=key, note="left the top list", now=now)
            sold += 1
    each = s["value"] / spec["n"]
    for tk in target:
        if tk not in held:
            place(store, aid, tk, "buy", value=each, source=key, note="entered the top list", now=now)
            bought += 1
    store.conn.execute("INSERT INTO paper_marks VALUES (?,?,?,?)",
                       (aid, today, "rebalance", json.dumps({"target": target, "sell": sold, "buy": bought})))
    store.conn.commit()
    return {"rebalance": True, "sell": sold, "buy": bought, "target": target}


def run_all(store, data_dir: str, fetch: bool = True, log=print) -> dict:
    """The daily job: queue strategy orders, then fill whatever can be filled."""
    _init(store)
    queued = {}
    for a in accounts(store):
        if a["kind"] in ("strategy", "forecast"):
            try:
                queued[a["id"]] = (step_strategy if a["kind"] == "strategy" else step_forecast)(
                    store, data_dir, a["id"], fetch=fetch)
            except Exception as e:
                queued[a["id"]] = {"error": str(e)[:200]}
    return {"queued": queued, "processed": process(store, data_dir, fetch, log)}
