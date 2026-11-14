from typing import Any
import psycopg
from psycopg.rows import dict_row

PARAMETERS = (
    "work_mem",
    "hash_mem_multiplier",
    "shared_buffers",
    "max_connections",
    "max_parallel_workers_per_gather",
)


def collect_configuration(conninfo: str) -> dict[str, Any]:
    """Read settings only; no ALTER SYSTEM or SET commands."""
    with psycopg.connect(conninfo, connect_timeout=5, row_factory=dict_row, application_name="pg-memory-agent") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS database_name, current_setting('server_version') AS server_version")
            identity = dict(cur.fetchone())
            cur.execute("SELECT name, setting, unit, source FROM pg_settings WHERE name = ANY(%s) ORDER BY name", (list(PARAMETERS),))
            rows = cur.fetchall()
    settings = {r["name"]: {"setting": r["setting"], "unit": r["unit"], "source": r["source"]} for r in rows}
    missing = sorted(set(PARAMETERS) - set(settings))
    if missing:
        raise RuntimeError(f"Missing settings: {', '.join(missing)}")
    # pg_settings reports work_mem in kilobytes, not MB.
    unit = settings["work_mem"]["unit"]
    if unit != "kB":
        raise RuntimeError(f"Unexpected work_mem unit: {unit!r}")
    return {
        **identity,
        "scope": "instance",
        "mode": "observe",
        "work_mem_mb": int(settings["work_mem"]["setting"]) / 1024,
        "settings": settings,
    }
