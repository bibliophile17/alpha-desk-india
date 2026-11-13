"""Price ingestion. All providers return the same standard columns."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

import pandas as pd
import yfinance as yf

STANDARD_COLUMNS = [
    "date", "ticker", "open", "high", "low", "close", "adj_close",
    "volume", "dividends", "split_ratio", "source", "retrieved_at",
]
REQUIRED_RAW_COLUMNS = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
ACTION_COLUMNS = {"Dividends": "dividends", "Stock Splits": "split_ratio"}


class PriceError(Exception):
    """Base class. `stage` says where in the pipeline the failure happened."""
    stage = "unclassified"


class FetchError(PriceError):
    stage = "fetch"        # library exception, or empty response


class ResponseFormatError(PriceError):
    stage = "format"       # data arrived in an unexpected shape


class ProcessingError(PriceError):
    stage = "processing"   # our own code failed on well-formed data


class PriceProvider(Protocol):
    name: str

    def fetch(self, ticker: str, start: str, end: str) -> pd.DataFrame: ...


class YFinanceProvider:
    name = "yfinance"

    def fetch(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        try:
            raw = yf.Ticker(ticker).history(
                start=start, end=end, auto_adjust=False, actions=True
            )
        except Exception as exc:
            raise FetchError(f"{type(exc).__name__}: {exc}") from exc

        if raw is None or len(raw) == 0:
            raise FetchError("empty response (bad symbol, rate limit, or block)")

        self._check_format(raw)
        return self._standardise(raw, ticker)

    @staticmethod
    def _check_format(raw) -> None:
        if not isinstance(raw, pd.DataFrame):
            raise ResponseFormatError(f"expected DataFrame, got {type(raw).__name__}")
        if isinstance(raw.columns, pd.MultiIndex):
            raise ResponseFormatError("MultiIndex columns (yfinance output layout changed?)")
        if not isinstance(raw.index, pd.DatetimeIndex):
            raise ResponseFormatError(
                f"index is {type(raw.index).__name__}, expected DatetimeIndex")
        missing = [c for c in REQUIRED_RAW_COLUMNS if c not in raw.columns]
        if missing:
            raise ResponseFormatError(
                f"missing columns {missing}; got {list(raw.columns)}")
        for c in REQUIRED_RAW_COLUMNS:
            if not pd.api.types.is_numeric_dtype(raw[c]):
                raise ResponseFormatError(f"column {c} has dtype {raw[c].dtype}")

    def _standardise(self, raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
        df = raw.copy()

        # Dates arrive timezone-aware (Asia/Kolkata). Keep the calendar date only.
        dates = pd.DatetimeIndex(df.index)
        if dates.tz is not None:
            dates = dates.tz_localize(None)
        df = df.reset_index(drop=True)
        df.insert(0, "date", dates.normalize().to_numpy())

        # Dividend/split columns are optional. If absent we assume "no events",
        # but we record that assumption so the corporate-action checks are known
        # to be blind for this ticker (the probe turns it into a review flag).
        missing_actions = [new for old, new in ACTION_COLUMNS.items()
                           if old not in df.columns]
        df = df.rename(columns={
            "Open": "open", "High": "high", "Low": "low", "Close": "close",
            "Adj Close": "adj_close", "Volume": "volume", **ACTION_COLUMNS,
        })
        for col in missing_actions:
            df[col] = 0.0

        df["ticker"] = ticker
        df["source"] = self.name
        df["retrieved_at"] = datetime.now(timezone.utc).isoformat()

        out = df[STANDARD_COLUMNS].copy()
        out.attrs["actions_columns_missing"] = missing_actions
        return out