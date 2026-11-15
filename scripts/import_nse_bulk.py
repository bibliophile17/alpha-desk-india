import csv
import shutil
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "reference"

EXPORT = REF / "nse_integrated_filings_export.csv"
UNIVERSE = ROOT / "config" / "universe.csv"
EVENTS = REF / "earnings_announcements.csv"

TARGET_PERIODS = {"30-JUN-2026", "30-SEP-2026"}

def clean(value):
    return " ".join(str(value or "").replace("\ufeff", "").split()).strip()

def read_csv(path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [
            {clean(k).upper(): clean(v) for k, v in row.items()}
            for row in reader
        ]

def parse_date(value):
    for fmt in ("%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(value.upper(), fmt).date()
        except ValueError:
            pass
    return None

def parse_timestamp(value):
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            return datetime.strptime(value.upper(), fmt)
        except ValueError:
            pass
    return None

def fiscal_quarter(ticker, date):
    # ABB follows a calendar-year financial year.
    if ticker == "ABB.NS":
        q = (date.month - 1) // 3 + 1
        return f"Q{q}FY{str(date.year)[-2:]}"

    # Standard Indian March year-end.
    if date.month == 6:
        return f"Q1FY{str(date.year + 1)[-2:]}"
    if date.month == 9:
        return f"Q2FY{str(date.year + 1)[-2:]}"
    if date.month == 12:
        return f"Q3FY{str(date.year + 1)[-2:]}"
    return f"Q4FY{str(date.year)[-2:]}"

def main():
    universe = read_csv(UNIVERSE)
    export = read_csv(EXPORT)
    existing = read_csv(EVENTS)

    ticker_map = {
        row["TICKER"].removesuffix(".NS"): row
        for row in universe
    }

    existing_keys = {
        (r["TICKER"], r["FISCAL_QUARTER"])
        for r in existing
    }

    grouped = defaultdict(list)
    skipped = defaultdict(int)

    for row in export:
        symbol = row.get("SYMBOL", "").upper()
        if symbol not in ticker_map:
            continue

        period = row.get("QUARTER END DATE", "").upper()
        if period not in TARGET_PERIODS:
            continue

        if row.get("TYPE OF SUBMISSION", "").upper() != "ORIGINAL":
            skipped["not_original"] += 1
            continue

        if row.get("AUDITED / UNAUDITED", "").upper() not in (
            "UN-AUDITED", "UNAUDITED"
        ):
            skipped["not_unaudited"] += 1
            continue

        if row.get("CONSOLIDATED / STANDALONE", "").upper() != "CONSOLIDATED":
            skipped["not_consolidated"] += 1
            continue

        timestamp = parse_timestamp(row.get("BROADCAST DATE/TIME", ""))
        if not timestamp:
            skipped["missing_broadcast_timestamp"] += 1
            continue

        url = row.get("DETAILS", "")
        if not url.startswith("https://"):
            skipped["missing_source_url"] += 1
            continue

        date = parse_date(period)
        if not date:
            skipped["invalid_period_date"] += 1
            continue

        ticker = symbol + ".NS"
        quarter = fiscal_quarter(ticker, date)
        key = (ticker, quarter)

        if key in existing_keys:
            skipped["already_present"] += 1
            continue

        company = ticker_map[symbol]

        event = {
            "ticker": ticker,
            "company": company["COMPANY"],
            "sector": company["SECTOR"],
            "fiscal_quarter": quarter,
            "announce_date": timestamp.date().isoformat(),
            "announce_time": timestamp.strftime("%H:%M:%S"),
            "time_source": "nse_broadcast_time",
            "revenue": "",
            "pat": "",
            "eps": "",
            "prior_revenue": "",
            "prior_pat": "",
            "prior_eps": "",
            "source_url": url,
            "retrieved_at": datetime.now().astimezone().isoformat()
        }

        grouped[key].append((timestamp, event))

    # Keep the earliest original filing per ticker-quarter.
    additions = []
    for key, candidates in grouped.items():
        candidates.sort(key=lambda x: x[0])
        additions.append(candidates[0][1])
        if len(candidates) > 1:
            skipped["multiple_originals_same_quarter"] += len(candidates) - 1

    additions.sort(key=lambda r: (r["announce_date"], r["ticker"]))

    print(f"Universe: {len(universe)} companies")
    print(f"NSE export: {len(export)} records")
    print(f"New events found: {len(additions)}")
    print(f"Already present: {skipped['already_present']}")
    print(f"Missing timestamps: {skipped['missing_broadcast_timestamp']}")

    print("\nNew events by sector:")
    sectors = defaultdict(int)
    for event in additions:
        sectors[event["sector"]] += 1
    for sector, count in sorted(sectors.items()):
        print(f"  {sector}: {count}")

    if not additions:
        print("\nNo new events to import.")
        return

    # Preserve the original file before modifying it.
    backup = REF / (
        "earnings_announcements.pre_bulk_"
        + datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv"
    )
    shutil.copy2(EVENTS, backup)

    columns = list(existing[0].keys()) if existing else list(additions[0].keys())

    with EVENTS.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        for event in additions:
            writer.writerow(event)

    print(f"\nImported: {len(additions)}")
    print(f"Backup: {backup}")
    print(f"Updated: {EVENTS}")

    print("\nRun the announcement validator next.")

if __name__ == "__main__":
    main()
