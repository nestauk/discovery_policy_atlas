"""psycopg2 connection pool and query helpers.

Replaces the Supabase Python SDK for all direct database access.
The pool is initialised lazily on first use and shared process-wide.
"""

import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
import psycopg2.extensions
from psycopg2.pool import ThreadedConnectionPool

from app.core.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[ThreadedConnectionPool] = None


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        if not settings.DATABASE_URL:
            raise ValueError("DATABASE_URL is required for database access")
        # Register JSON/JSONB adapters so JSONB columns come back as Python dicts
        psycopg2.extras.register_default_json(globally=True)
        psycopg2.extras.register_default_jsonb(globally=True)
        _pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=20,
            dsn=settings.DATABASE_URL,
        )
        logger.info("Database connection pool initialised")
    return _pool


def _adapt_value(v: Any) -> Any:
    """Wrap dicts/lists with Json() so psycopg2 serialises them as JSONB."""
    if isinstance(v, (dict, list)):
        return psycopg2.extras.Json(v)
    return v


def adapt_params(params: List[Any]) -> List[Any]:
    """Adapt a list of parameter values for psycopg2 (wraps dicts/lists with Json)."""
    return [_adapt_value(p) for p in params]


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def fetch(sql: str, params=None) -> List[Dict]:
    """Execute a SELECT and return all rows as plain dicts."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
    finally:
        pool.putconn(conn)


def fetchone(sql: str, params=None) -> Optional[Dict]:
    """Execute a SELECT and return the first row, or None."""
    rows = fetch(sql, params)
    return rows[0] if rows else None


def fetchcount(sql: str, params=None) -> int:
    """Execute a COUNT query and return the integer result."""
    row = fetchone(sql, params)
    if row is None:
        return 0
    return int(next(iter(row.values()), 0))


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

@contextmanager
def _write_conn():
    """Context manager that commits on success and rolls back on error."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def execute(sql: str, params=None) -> None:
    """Execute a DML statement (INSERT/UPDATE/DELETE) with no return value."""
    if params is not None:
        params = [_adapt_value(p) for p in params]
    with _write_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)


def insert(table: str, data: Dict) -> Dict:
    """Insert a single row and return the inserted row as a dict."""
    keys = list(data.keys())
    values = [_adapt_value(data[k]) for k in keys]
    cols = ", ".join(f'"{k}"' for k in keys)
    placeholders = ", ".join(["%s"] * len(keys))
    sql = f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders}) RETURNING *'
    with _write_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, values)
            row = cur.fetchone()
    if row is None:
        raise RuntimeError(f"INSERT into {table!r} returned no row")
    return dict(row)


def insert_many(table: str, rows: List[Dict]) -> None:
    """Batch-insert rows without returning data."""
    if not rows:
        return
    keys = list(rows[0].keys())
    cols = ", ".join(f'"{k}"' for k in keys)
    placeholders = ", ".join(["%s"] * len(keys))
    sql = f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})'
    with _write_conn() as conn:
        with conn.cursor() as cur:
            values_list = [[_adapt_value(row.get(k)) for k in keys] for row in rows]
            cur.executemany(sql, values_list)


def upsert(
    table: str,
    data: Dict,
    conflict_cols: List[str],
    conflict_where: Optional[str] = None,
) -> Optional[Dict]:
    """Insert or update on conflict.  Returns the upserted row.

    conflict_where: optional SQL predicate for partial-index conflict targets,
    e.g. ``"upload_step <> 'deleted'"`` — must match the index's WHERE clause.
    """
    keys = list(data.keys())
    values = [_adapt_value(data[k]) for k in keys]
    cols = ", ".join(f'"{k}"' for k in keys)
    placeholders = ", ".join(["%s"] * len(keys))
    conflict = ", ".join(f'"{c}"' for c in conflict_cols)
    where_clause = f" WHERE {conflict_where}" if conflict_where else ""
    update_set = ", ".join(
        f'"{k}" = EXCLUDED."{k}"'
        for k in keys
        if k not in conflict_cols
    )
    sql = (
        f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders}) '
        f"ON CONFLICT ({conflict}){where_clause} DO UPDATE SET {update_set} RETURNING *"
    )
    with _write_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, values)
            row = cur.fetchone()
    return dict(row) if row else None


def upsert_many(
    table: str,
    rows: List[Dict],
    conflict_cols: List[str],
    conflict_where: Optional[str] = None,
) -> None:
    """Batch upsert rows.  Uses executemany — no RETURNING.

    conflict_where: optional SQL predicate for partial-index conflict targets.
    """
    if not rows:
        return
    keys = list(rows[0].keys())
    cols = ", ".join(f'"{k}"' for k in keys)
    placeholders = ", ".join(["%s"] * len(keys))
    conflict = ", ".join(f'"{c}"' for c in conflict_cols)
    where_clause = f" WHERE {conflict_where}" if conflict_where else ""
    update_set = ", ".join(
        f'"{k}" = EXCLUDED."{k}"'
        for k in keys
        if k not in conflict_cols
    )
    sql = (
        f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders}) '
        f"ON CONFLICT ({conflict}){where_clause} DO UPDATE SET {update_set}"
    )
    with _write_conn() as conn:
        with conn.cursor() as cur:
            values_list = [[_adapt_value(row.get(k)) for k in keys] for row in rows]
            cur.executemany(sql, values_list)


# ---------------------------------------------------------------------------
# Vector helper
# ---------------------------------------------------------------------------

def fmt_vector(embedding: List[float]) -> str:
    """Format a float list as a pgvector literal string, e.g. '[0.1,0.2,...]'."""
    return "[" + ",".join(str(x) for x in embedding) + "]"
