"""Combine snapshots and calculate reset-safe counter deltas."""
from datetime import datetime, timezone
import time
from pg_memory_agent.collector.linux import collect_linux_memory
from pg_memory_agent.collector.workload import collect_workload


def collect_snapshot(conninfo: str, include_queries: bool = False) -> dict:
    result = collect_workload(conninfo, include_queries=include_queries)
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "instance",
        "linux": collect_linux_memory(),
        "postgresql": result,
    }


def calculate_temp_rates(before: dict, after: dict, elapsed_seconds: float) -> dict:
    """Return per-database counter differences; unknown when reset/missing."""
    if elapsed_seconds <= 0:
        raise ValueError("elapsed_seconds must be positive")
    old = {row["datid"]: row for row in before["postgresql"]["databases"]}
    result = []
    for row in after["postgresql"]["databases"]:
        prev = old.get(row["datid"])
        valid = (prev is not None and prev["stats_reset"] == row["stats_reset"]
                 and row["temp_bytes"] >= prev["temp_bytes"]
                 and row["temp_files"] >= prev["temp_files"])
        if valid:
            bytes_diff = row["temp_bytes"] - prev["temp_bytes"]
            files_diff = row["temp_files"] - prev["temp_files"]
            result.append({"database": row["datname"], "status": "ok",
                           "temp_bytes_delta": bytes_diff, "temp_files_delta": files_diff,
                           "temp_mb_per_min": round(bytes_diff / 1024**2 * 60 / elapsed_seconds, 3)})
        else:
            result.append({"database": row["datname"], "status": "baseline_unavailable_or_reset",
                           "temp_bytes_delta": None, "temp_files_delta": None,
                           "temp_mb_per_min": None})
    return {"elapsed_seconds": round(elapsed_seconds, 3), "per_database": result}


def collect_interval(conninfo: str, interval_seconds: float, include_queries: bool = False) -> dict:
    before = collect_snapshot(conninfo, include_queries=False)
    started = time.monotonic()
    time.sleep(interval_seconds)
    after = collect_snapshot(conninfo, include_queries=include_queries)
    elapsed = time.monotonic() - started
    after["temp_rates"] = calculate_temp_rates(before, after, elapsed)
    return after
