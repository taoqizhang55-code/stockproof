"""Today's date, overridable for the demo (STOCKPROOF_TODAY=YYYY-MM-DD) so bundled data looks current."""

import datetime as dt
import os


def today() -> dt.date:
    v = os.environ.get("STOCKPROOF_TODAY", "").strip()
    if v:
        try:
            return dt.date.fromisoformat(v)
        except ValueError:
            pass
    return dt.date.today()
