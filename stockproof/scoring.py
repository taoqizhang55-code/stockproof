"""
Ask the LLM to read headlines and score each one, in batches (one request per
stock instead of one per headline: faster and cheaper).

For each headline the model returns:
  relevance : 0-1, is this headline really about THIS company?
              (catches "Merck KGaA" news under MRK, "GE HealthCare" under GE...)
  score     : -1 (very negative) to +1 (very positive) for this company's stock
  reason    : one short sentence, in English or Chinese
  duplicate_of : the same event as an earlier headline in the batch (reworded / other outlet)?
              Duplicates are kept and shown, but not counted twice in the mood.
"""

from __future__ import annotations

from stockproof.llm import LLMClient, LLMError

BATCH_SIZE = 10

REASON_LANGUAGE = {"en": "English", "zh": "Simplified Chinese"}


def build_prompt(ticker: str, name: str, titles: list[str], lang: str) -> str:
    lines = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
    return (
        "You are a careful equity news analyst.\n"
        f"Company: {name} (ticker {ticker}).\n\n"
        f"Headlines:\n{lines}\n\n"
        "For EACH headline give:\n"
        "- relevance: 0 to 1. 1 = mainly about this company; 0.5 = this company is one of "
        "several discussed; 0 = about a different company (even one with a similar name) "
        "or only the general market.\n"
        "- score: -1 (very negative) to 1 (very positive) for this company's stock price. "
        "0 = neutral, no new information, or opinion pieces without facts.\n"
        f"- reason: one short sentence in {REASON_LANGUAGE.get(lang, 'English')}.\n"
        "- duplicate_of: if the headline reports the SAME event as an earlier-numbered headline in "
        "this list (just reworded or from another outlet), that headline's number; otherwise null. "
        "Different events of the same kind (e.g. buybacks on different days) are not duplicates.\n\n"
        'Reply ONLY with JSON: {"items": [{"i": 0, "relevance": 0.9, "score": 0.4, '
        '"reason": "...", "duplicate_of": null}, ...]} with one item per headline, same numbering.'
    )


def _clip(x, lo, hi, default):
    try:
        return max(lo, min(hi, float(x)))
    except (TypeError, ValueError):
        return default


def score_headlines(client: LLMClient, ticker: str, name: str,
                    titles: list[str], lang: str = "en") -> list[dict | None]:
    """Returns one dict per title (same order), or None where the model gave no answer."""
    results: list[dict | None] = [None] * len(titles)
    for start in range(0, len(titles), BATCH_SIZE):
        batch = titles[start:start + BATCH_SIZE]
        data = client.chat_json(build_prompt(ticker, name, batch, lang))
        items = data.get("items")
        if not isinstance(items, list):
            raise LLMError("Model reply has no 'items' list.")
        for pos, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            i = item.get("i", pos)
            try:
                i = int(i)
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(batch):
                dup = item.get("duplicate_of")
                try:
                    dup = int(dup) if dup is not None and str(dup).strip().lower() not in ("", "null", "none") else None
                except (TypeError, ValueError):
                    dup = None
                if dup is not None and not (0 <= dup < i):
                    dup = None                       # must point to an earlier headline in this batch
                results[start + i] = {
                    "relevance": _clip(item.get("relevance"), 0.0, 1.0, 1.0),
                    "score": _clip(item.get("score"), -1.0, 1.0, 0.0),
                    "reason": str(item.get("reason", ""))[:300],
                    "duplicate_of": None if dup is None else start + dup,   # position in `titles`
                }
    return results
