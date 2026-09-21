"""SQLite bridge for the SQL analytics layer (stdlib only, no credentials).

Responsibility (feature/sql-analytics branch only)::

    integrated DataFrame (read-only)
        -> load_integrated_dataset (CREATE TABLE from actual columns + INSERT)
        -> execute_query / execute_sql_file (SELECTs from sql/*.sql)
        -> get_sql_kpis / validate_sql_vs_pandas (comparison reports)

The loader derives the table schema from the DataFrame's ACTUAL columns
(never invents tables/columns): booleans/integers -> INTEGER, floats ->
REAL, datetimes -> ISO-8601 TEXT, everything else -> TEXT. Column order
follows the DataFrame for determinism. The source frame is never mutated.

Aggregation contract (mirrors the analysis engine):

* record-level metrics read the base table directly;
* shipment-level metrics aggregate via one row per shipment
  (``MAX(delay_duration)`` per shipment is robust to one-to-many
  duplication) - see ``sql/views.sql`` ``shipment_delay_summary``.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd

PathLike = Union[str, Path]

DEFAULT_TABLE = "integrated_logistics"
SQL_DIR = Path(__file__).resolve().parent.parent / "sql"

_SECTION_HEADER = re.compile(r"^--\s*query:\s*(\S+)\s*$")


def _sqlite_type(series: pd.Series) -> str:
    """Map a Series dtype to a SQLite storage type."""
    if pd.api.types.is_bool_dtype(series):
        return "INTEGER"
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "TEXT"
    return "TEXT"


def _quote(identifier: str) -> str:
    """Quote a SQLite identifier (escapes embedded double quotes)."""
    return '"' + identifier.replace('"', '""') + '"'


def _to_storage_value(value: Any) -> Any:
    """Convert a cell to a SQLite-storable value (datetimes -> ISO TEXT)."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        import datetime as _dt

        if isinstance(value, (_dt.datetime, _dt.date)):
            return value.isoformat()
    except (TypeError, ValueError):
        pass
    return value


def get_connection(db_path: PathLike = ":memory:") -> sqlite3.Connection:
    """Open a SQLite connection (``:memory:`` default; file path optional)."""
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    """Return the column names of ``table`` (empty list when absent)."""
    rows = connection.execute(
        "SELECT name FROM pragma_table_info(?)", (table,)
    ).fetchall()
    return [str(row["name"]) for row in rows]


def load_integrated_dataset(
    dataset: pd.DataFrame,
    db_path: PathLike = ":memory:",
    table: str = DEFAULT_TABLE,
    connection: Optional[sqlite3.Connection] = None,
) -> tuple[sqlite3.Connection, dict[str, Any]]:
    """Load an integrated DataFrame into SQLite (source frame untouched).

    Creates ``table`` from the frame's actual columns, inserts every row,
    and validates the inserted count. Raises ValueError on an empty frame
    and RuntimeError when the inserted row count mismatches.

    Returns ``(connection, report)``. The caller owns (and must close) the
    connection unless it passed one in, which is then left open.
    """
    if dataset.empty and len(dataset.columns) == 0:
        raise ValueError("Refusing to load a dataset with no columns.")
    owns_connection = connection is None
    conn = connection if connection is not None else get_connection(db_path)

    columns = [str(col) for col in dataset.columns]
    definitions = ", ".join(
        f"{_quote(col)} {_sqlite_type(dataset[col])}" for col in columns
    )
    try:
        conn.execute(f"CREATE TABLE IF NOT EXISTS {_quote(table)} ({definitions})")
        placeholders = ", ".join(["?"] * len(columns))
        names = ", ".join(_quote(col) for col in columns)
        rows = [
            tuple(_to_storage_value(dataset[col].iloc[i]) for col in columns)
            for i in range(len(dataset))
        ]
        if rows:
            conn.executemany(
                f"INSERT INTO {_quote(table)} ({names}) VALUES ({placeholders})", rows
            )
        conn.commit()
        inserted = conn.execute(
            f"SELECT COUNT(*) AS n FROM {_quote(table)}"
        ).fetchone()["n"]
    except Exception:
        if owns_connection:
            conn.close()
        raise
    if int(inserted) != int(len(dataset)):
        if owns_connection:
            conn.close()
        raise RuntimeError(
            f"Row-count mismatch loading '{table}': "
            f"source {len(dataset)} rows, table {inserted} rows."
        )
    report = {
        "table": table,
        "source_rows": int(len(dataset)),
        "inserted_rows": int(inserted),
        "columns": columns,
    }
    return conn, report


def execute_query(
    connection: sqlite3.Connection,
    sql: str,
    params: Optional[Union[tuple, list, dict]] = None,
) -> pd.DataFrame:
    """Execute a SELECT query and return the result as a DataFrame."""
    if params is None:
        return pd.read_sql_query(sql, connection)
    return pd.read_sql_query(sql, connection, params=params)


def split_sql_sections(sql_text: str) -> dict[str, str]:
    """Split a ``.sql`` file into ``{name: sql}`` by ``-- query: <name>`` headers.

    Text before the first header is ignored (e.g. file-level comments).
    Raises ValueError on duplicate section names.
    """
    sections: dict[str, str] = {}
    current: Optional[str] = None
    buffer: list[str] = []
    for line in sql_text.splitlines():
        match = _SECTION_HEADER.match(line.strip())
        if match:
            if current is not None:
                sections[current] = "\n".join(buffer).strip()
            name = match.group(1)
            if name in sections:
                raise ValueError(f"Duplicate SQL section name: '{name}'.")
            current = name
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        sections[current] = "\n".join(buffer).strip()
    return sections


def execute_sql_file(
    connection: sqlite3.Connection,
    path: PathLike,
    table: str = DEFAULT_TABLE,
) -> dict[str, pd.DataFrame]:
    """Execute every ``-- query: <name>`` section in a SQL file.

    ``{table}`` placeholders in the SQL are replaced with the quoted table
    name so files stay reusable. Returns ``{name: DataFrame}`` in file order.
    """
    text = Path(path).read_text(encoding="utf-8")
    results: dict[str, pd.DataFrame] = {}
    for name, sql in split_sql_sections(text).items():
        rendered = sql.replace("{table}", _quote(table))
        results[name] = execute_query(connection, rendered)
    return results


def execute_sql_script(
    connection: sqlite3.Connection,
    path: PathLike,
    table: str = DEFAULT_TABLE,
) -> None:
    """Execute a DDL/DML script file (e.g. ``sql/views.sql``).

    ``{table}`` placeholders are rendered before execution. Commits on
    success; rolls back and re-raises on error.
    """
    text = Path(path).read_text(encoding="utf-8").replace("{table}", _quote(table))
    try:
        connection.executescript(text)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def apply_views(
    connection: sqlite3.Connection,
    views_path: Optional[PathLike] = None,
    table: str = DEFAULT_TABLE,
) -> list[str]:
    """Create the reusable views from ``sql/views.sql``.

    Returns the view names created (queried from sqlite_master).
    """
    path = Path(views_path) if views_path is not None else SQL_DIR / "views.sql"
    if not path.is_file():
        raise FileNotFoundError(f"Views SQL file not found: {path}")
    execute_sql_script(connection, path, table=table)
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'view' ORDER BY name"
    ).fetchall()
    return [str(row["name"]) for row in rows]


def get_sql_kpis(
    connection: sqlite3.Connection,
    metrics_path: Optional[PathLike] = None,
    table: str = DEFAULT_TABLE,
) -> dict[str, pd.DataFrame]:
    """Run ``sql/metrics.sql`` and return ``{section: DataFrame}``."""
    path = Path(metrics_path) if metrics_path is not None else SQL_DIR / "metrics.sql"
    if not path.is_file():
        raise FileNotFoundError(f"Metrics SQL file not found: {path}")
    return execute_sql_file(connection, path, table=table)


def _scalar(frame: pd.DataFrame) -> Any:
    """Extract the single value of a one-row, one-column result."""
    if frame.empty:
        return None
    value = frame.iloc[0, 0]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def validate_sql_vs_pandas(
    comparisons: list[dict[str, Any]],
    rtol: float = 1e-6,
) -> dict[str, Any]:
    """Compare SQL values against Pandas values with a relative tolerance.

    Each comparison is ``{"name": ..., "sql": ..., "pandas": ...}`` where
    ``None`` matches ``None`` (both unavailable). Returns a report with per
    metric ``match`` flags plus an overall ``all_match`` flag. Never forces
    numbers to agree: mismatches are reported with both values.
    """
    details: list[dict[str, Any]] = []
    for item in comparisons:
        name = str(item.get("name", "metric"))
        sql_value = item.get("sql")
        pandas_value = item.get("pandas")
        if sql_value is None and pandas_value is None:
            match: bool = True
            note = "both unavailable"
        elif sql_value is None or pandas_value is None:
            match = False
            note = "one side unavailable"
        else:
            try:
                difference = abs(float(sql_value) - float(pandas_value))
                scale = max(abs(float(pandas_value)), 1e-12)
                match = difference <= rtol * scale
                note = f"|sql-pandas|={difference}"
            except (TypeError, ValueError):
                match = sql_value == pandas_value
                note = "exact comparison"
        details.append(
            {
                "name": name,
                "sql": sql_value,
                "pandas": pandas_value,
                "match": match,
                "note": note,
            }
        )
    return {"comparisons": details, "all_match": all(d["match"] for d in details)}
