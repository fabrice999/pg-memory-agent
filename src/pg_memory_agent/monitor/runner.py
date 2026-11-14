
"""Continuous PostgreSQL memory monitoring."""

import time

from pg_memory_agent.collector.snapshot import collect_snapshot
from pg_memory_agent.storage.sqlite import MetricsStore


def run_monitor(
    conninfo: str,
    interval: float = 10,
    db_path: str = "data/metrics.db",
    max_samples: int | None = None,
) -> int:
    """Collect and persist monitoring snapshots."""

    if interval <= 0:
        raise ValueError("interval must be greater than zero")

    if max_samples is not None and max_samples < 1:
        raise ValueError("max_samples must be positive")

    store = MetricsStore(db_path)
    samples = 0

    print(f"Starting PostgreSQL monitoring (interval={interval}s)")
    print(f"SQLite database: {store.db_path}")
    print("Press Ctrl+C to stop.", flush=True)

    try:
        while max_samples is None or samples < max_samples:
            started = time.monotonic()

            snapshot = collect_snapshot(conninfo)
            snapshot_id = store.save_snapshot(snapshot)

            samples += 1

            linux = snapshot["linux"]
            activity = snapshot["postgresql"]["activity"]

            print(
                f"[{snapshot['timestamp_utc']}] "
                f"snapshot={snapshot_id} "
                f"RAM={linux['ram_used_percent']:.1f}% "
                f"active_sessions={activity['active_sessions']} "
                f"databases={len(snapshot['postgresql']['databases'])}",
                flush=True,
            )

            if max_samples is not None and samples >= max_samples:
                break

            elapsed = time.monotonic() - started
            time.sleep(max(0, interval - elapsed))

    except KeyboardInterrupt:
        print("\nMonitoring stopped by user.", flush=True)

    finally:
        store.close()

    return samples

