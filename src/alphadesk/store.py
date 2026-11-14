"""DuckDB + Parquet storage of research tables. The database file is a build artifact
(gitignored): it is regenerated from CSV/JSON outputs, never hand-edited."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


def build_database(db_path, tables: dict, parquet_dir=None) -> dict:
    """Write each DataFrame as a DuckDB table (and optional Parquet). Returns row counts."""
    import duckdb                                    # lazy: only needed when storing

    for name, df in tables.items():
        if not _NAME.match(name):
            raise ValueError(f"bad table name {name!r}")
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"{name} is not a DataFrame")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    if parquet_dir:
        Path(parquet_dir).mkdir(parents=True, exist_ok=True)
    counts = {}
    con = duckdb.connect(str(db_path))
    try:
        for name, df in tables.items():
            con.register("_src", df)
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _src")
            con.unregister("_src")
            counts[name] = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            if parquet_dir:
                target = (Path(parquet_dir) / f"{name}.parquet").as_posix()
                con.execute(f"COPY {name} TO '{target}' (FORMAT PARQUET)")
    finally:
        con.close()
    return counts
