"""Load saved price CSVs (prices_<ticker>.csv, indices as prices_IDX_<name>.csv)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def _ticker_from_name(stem: str) -> str:
    name = stem[len("prices_"):]
    return "^" + name[4:] if name.startswith("IDX_") else name


def load_price_frames(d) -> dict:
    """{ticker: DataFrame sorted by date}. Raises if the folder has no price files."""
    frames = {}
    for f in sorted(Path(d).glob("prices_*.csv")):
        df = pd.read_csv(f, parse_dates=["date"]).sort_values("date")
        frames[_ticker_from_name(f.stem)] = df.reset_index(drop=True)
    if not frames:
        raise FileNotFoundError(f"no prices_*.csv files in {d}")
    return frames


def series_of(frames: dict, ticker: str, col: str) -> pd.Series:
    s = frames[ticker].set_index("date")[col]
    s.index = pd.DatetimeIndex(s.index).normalize()
    return s
