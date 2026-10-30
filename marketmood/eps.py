"""
Quarterly EPS history and earnings surprise (SUE), point-in-time.

Point-in-time means: for each quarter we keep the number AS FIRST REPORTED and the
date it was filed. Companies often restate old numbers later; using the restated
value in a backtest would be using information nobody had at the time.

Q4 is usually not reported on its own (the 10-K reports the full year), so:
    Q4 EPS = full-year EPS - (Q1 + Q2 + Q3)
This is the standard approximation (share counts change a little during the year).

SUE (standardized unexpected earnings), the classic academic measure:
    change = EPS this quarter - EPS same quarter last year
    SUE    = change / standard deviation of the previous 8 such changes
A SUE of +2 means "a much bigger improvement than this company usually shows".
"""

from __future__ import annotations

import pandas as pd

CONCEPTS = ["EarningsPerShareDiluted", "EarningsPerShareBasic"]
FORMS = {"10-Q", "10-K", "10-Q/A", "10-K/A", "20-F", "40-F"}


def _raw_eps(facts: dict) -> tuple[pd.DataFrame, str]:
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for concept in CONCEPTS:
        units = gaap.get(concept, {}).get("units", {})
        rows = units.get("USD/shares") or next(iter(units.values()), [])
        if rows:
            df = pd.DataFrame(rows)
            if {"start", "end", "val", "filed", "form"} <= set(df.columns):
                return df, concept
    return pd.DataFrame(), ""


def quarterly_eps(facts: dict) -> pd.DataFrame:
    """Columns: start, end, eps, filed, fiscal (e.g. 'FY2026 Q3'), q4_derived."""
    raw, concept = _raw_eps(facts)
    if raw.empty:
        return pd.DataFrame(columns=["start", "end", "eps", "filed", "fiscal", "q4_derived"])
    raw = raw[raw["form"].isin(FORMS)].copy()
    for col in ("start", "end", "filed"):
        raw[col] = pd.to_datetime(raw[col])
    raw["days"] = (raw["end"] - raw["start"]).dt.days

    # first-reported value for each period
    raw = raw.sort_values("filed").drop_duplicates(["start", "end"], keep="first")

    q = raw[raw["days"].between(80, 100)].copy()
    q["q4_derived"] = False
    annual = raw[raw["days"].between(350, 380)]

    derived = []
    for _, a in annual.iterrows():
        inside = q[(q["start"] >= a["start"] - pd.Timedelta(days=5)) &
                   (q["end"] <= a["end"] - pd.Timedelta(days=60))]
        if len(inside) != 3:
            continue
        last_end = inside["end"].max()
        if ((q["start"] > last_end) & (q["end"] <= a["end"] + pd.Timedelta(days=5))).any():
            continue                                  # Q4 was reported separately already
        derived.append({"start": last_end + pd.Timedelta(days=1), "end": a["end"],
                        "val": a["val"] - inside["val"].sum(), "filed": a["filed"],
                        "fy": a.get("fy"), "fp": "Q4", "q4_derived": True})
    if derived:
        q = pd.concat([q, pd.DataFrame(derived)], ignore_index=True)

    q = q.sort_values("end").drop_duplicates("end", keep="first").reset_index(drop=True)
    fy = q["fy"] if "fy" in q else pd.Series([None] * len(q))
    fp = q["fp"] if "fp" in q else pd.Series([None] * len(q))
    q["fiscal"] = [f"FY{int(y)} {p}" if pd.notna(y) and isinstance(p, str) else ""
                   for y, p in zip(fy, fp)]
    q = q.rename(columns={"val": "eps"})
    q.attrs["concept"] = concept
    return q[["start", "end", "eps", "filed", "fiscal", "q4_derived"]]


def add_sue(q: pd.DataFrame, window: int = 8, min_history: int = 4) -> pd.DataFrame:
    """Adds eps_year_ago, change, sue. Only uses quarters that end ~1 year apart."""
    q = q.copy().reset_index(drop=True)
    q["eps_year_ago"], q["change"], q["sue"] = None, None, None
    ends = q["end"]
    for i in range(len(q)):
        target = ends[i] - pd.Timedelta(days=365)
        gaps = (ends - target).abs()
        j = gaps.idxmin()
        if j < i and gaps[j] <= pd.Timedelta(days=20):
            q.at[i, "eps_year_ago"] = q.at[j, "eps"]
            q.at[i, "change"] = q.at[i, "eps"] - q.at[j, "eps"]
    changes = pd.to_numeric(q["change"], errors="coerce")
    for i in range(len(q)):
        past = changes.iloc[max(0, i - window):i].dropna()
        # (a std of ~1e-17 is rounding noise from EPS that never changed, not a real scale)
        if pd.notna(changes.iloc[i]) and len(past) >= min_history and past.std() > 1e-6:
            q.at[i, "sue"] = float(changes.iloc[i] / past.std())
    for col in ("eps_year_ago", "change", "sue"):
        q[col] = pd.to_numeric(q[col], errors="coerce")
    return q
