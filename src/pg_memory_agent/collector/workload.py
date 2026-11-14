"""Read-only PostgreSQL workload snapshot.

Statistics counters are cumulative. A single snapshot must not be interpreted
as a spill *rate* or proof that increasing work_mem will help.
"""
from typing import Any
import psycopg
from psycopg.rows import dict_row


SQL_ACTIVITY = """
SELECT count(*) FILTER (WHERE backend_type = 'client backend')::bigint AS client_sessions,
       count(*) FILTER (WHERE backend_type = 'client backend' AND state = 'active')::bigint AS active_sessions,
       count(*) FILTER (WHERE backend_type = 'client backend' AND state = 'idle in transaction')::bigint AS idle_in_transaction_sessions
FROM pg_stat_activity
"""
SQL_DATABASES = """
SELECT datid::text AS datid, datname, temp_files, temp_bytes, stats_reset
FROM pg_stat_database
WHERE datid <> 0
ORDER BY datname
"""
SQL_PGSS_EXISTS = "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements') AS installed"
SQL_PGSS = """
SELECT d.datname, s.queryid::text AS queryid, s.calls,
       round(s.mean_exec_time::numeric, 2) AS mean_exec_time_ms,
       s.temp_blks_read, s.temp_blks_written,
       left(s.query, 160) AS query_sample
FROM pg_stat_statements s
JOIN pg_database d ON d.oid = s.dbid
WHERE s.temp_blks_written > 0
ORDER BY s.temp_blks_written DESC
LIMIT 10
"""


def collect_workload(conninfo: str, include_queries: bool = False) -> dict[str, Any]:
    """Collect one PostgreSQL snapshot; queries are SELECT only."""
    with psycopg.connect(conninfo, connect_timeout=5, row_factory=dict_row,
                        application_name="pg-memory-agent") as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_ACTIVITY)
            activity = dict(cur.fetchone())
            cur.execute(SQL_DATABASES)
            databases = [dict(row) for row in cur.fetchall()]
            pgss = {"status": "not_requested", "top_spilling_queries": []}
            if include_queries:
                cur.execute(SQL_PGSS_EXISTS)
                if not cur.fetchone()["installed"]:
                    pgss["status"] = "extension_not_installed_in_connected_database"
                else:
                    # A restricted role may lack access to the extension/view.
                    # Inspect the available view without aborting all metrics.
                    try:
                        with conn.transaction():
                            cur.execute(SQL_PGSS)
                            pgss = {"status": "ok", "top_spilling_queries": [dict(x) for x in cur.fetchall()]}
                    except psycopg.Error:
                        pgss["status"] = "query_unavailable"
    return {"activity": activity, "databases": databases, "pg_stat_statements": pgss}
