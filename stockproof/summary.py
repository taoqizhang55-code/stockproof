"""Turn scored headlines into a per-stock summary."""

from __future__ import annotations

import pandas as pd

POSITIVE, NEGATIVE = 0.15, -0.15
MIN_SAMPLE = 5          # fewer relevant headlines than this -> mood is flagged as unreliable


def mood_label(score: float | None) -> str:
    if score is None or pd.isna(score):
        return "none"
    if score >= POSITIVE:
        return "positive"
    if score <= NEGATIVE:
        return "negative"
    return "neutral"


def _counted(df: pd.DataFrame, min_relevance: float) -> pd.DataFrame:
    """Headlines that count toward the mood: relevant, and not a repeat of another story."""
    rel = df[df["relevance"] >= min_relevance]
    if "duplicate_of" in rel.columns:
        rel = rel[rel["duplicate_of"].isna()]
    return rel


def summarize(df: pd.DataFrame, tickers: list[str], min_relevance: float,
              min_sample: int = MIN_SAMPLE) -> pd.DataFrame:
    """One row per ticker: headline counts, relevance-weighted mood of relevant headlines,
    and the most positive / most negative relevant headline."""
    rows = []
    for t in [x.upper() for x in tickers]:
        g = df[df["ticker"] == t]
        rel = _counted(g, min_relevance)
        if len(rel):
            w = rel["relevance"]
            mood = float((rel["score"] * w).sum() / w.sum())
            best, worst = rel.loc[rel["score"].idxmax()], rel.loc[rel["score"].idxmin()]
        else:
            mood, best, worst = None, None, None
        rows.append({
            "ticker": t,
            "headlines": len(g),
            "relevant": len(rel),
            "few": 0 < len(rel) < min_sample,
            "mood": mood,
            "label": mood_label(mood),
            "positive": int((rel["score"] >= POSITIVE).sum()),
            "negative": int((rel["score"] <= NEGATIVE).sum()),
            "best": None if best is None else best["title"],
            "best_score": None if best is None else float(best["score"]),
            "worst": None if worst is None else worst["title"],
            "worst_score": None if worst is None else float(worst["score"]),
        })
    out = pd.DataFrame(rows)
    return out.sort_values("mood", ascending=False, na_position="last").reset_index(drop=True)


def daily_mood(df: pd.DataFrame, min_relevance: float) -> pd.DataFrame:
    """Mood per stock per day (relevance-weighted, relevant headlines only).
    Columns: ticker, date, mood, n."""
    rel = _counted(df, min_relevance).copy()
    if rel.empty:
        return pd.DataFrame(columns=["ticker", "date", "mood", "n"])
    rel["w"] = rel["relevance"]
    rel["ws"] = rel["score"] * rel["w"]
    g = rel.groupby(["ticker", "date"]).agg(ws=("ws", "sum"), w=("w", "sum"), n=("score", "size"))
    g["mood"] = g["ws"] / g["w"]
    return g.reset_index()[["ticker", "date", "mood", "n"]].sort_values(["ticker", "date"])
