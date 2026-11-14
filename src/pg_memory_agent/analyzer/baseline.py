
"""Historical workload baseline analysis."""

import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median


MIB = 1024 * 1024

# Initial baseline-quality policy.
MIN_SAMPLES = 30
MIN_DURATION_MINUTES = 5
MIN_COVERAGE = 0.80
MIN_VALID_TEMP_INTERVALS = 0.80


def percentile(values, percentage):
    """Nearest-rank percentile for a list of numbers."""
    if not values:
        return None

    ordered = sorted(values)
    rank = math.ceil(len(ordered) * percentage / 100)
    return ordered[max(0, rank - 1)]


def parse_timestamp(value):
    """Convert an ISO 8601 timestamp to UTC."""
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    ).astimezone(timezone.utc)


def analyze_baseline(
    db_path="data/metrics.db",
    minutes=60,
    now=None,
):
    """Analyze stored PostgreSQL and Linux metrics."""

    if minutes <= 0:
        raise ValueError("minutes must be positive")

    path = Path(db_path)

    if not path.is_file():
        raise FileNotFoundError(
            f"Metrics database not found: {path}"
        )

    now = now or datetime.now(timezone.utc)

    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    now = now.astimezone(timezone.utc)
    start = now - timedelta(minutes=minutes)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row

        snapshots = conn.execute(
            """
            SELECT *
            FROM metric_snapshots
            WHERE timestamp_utc >= ?
              AND timestamp_utc <= ?
            ORDER BY timestamp_utc, id
            """,
            (start.isoformat(), now.isoformat()),
        ).fetchall()

        db_rows = conn.execute(
            """
            SELECT
                d.snapshot_id,
                d.datid,
                d.datname,
                d.temp_bytes,
                d.temp_files,
                d.stats_reset
            FROM database_metrics d
            JOIN metric_snapshots s
              ON s.id = d.snapshot_id
            WHERE s.timestamp_utc >= ?
              AND s.timestamp_utc <= ?
            ORDER BY s.timestamp_utc, s.id
            """,
            (start.isoformat(), now.isoformat()),
        ).fetchall()

    databases = {}

    for row in db_rows:
        databases.setdefault(
            row["snapshot_id"], {}
        )[row["datid"]] = row

    count = len(snapshots)

    if count == 0:
        return {
            "observation_minutes": minutes,
            "samples": 0,
            "observed_duration_minutes": 0,
            "coverage_ratio": 0,
            "memory": None,
            "activity": None,
            "temporary_io": None,
            "baseline_status": "INSUFFICIENT_DATA",
            "reason": "No monitoring samples found",
        }

    ram_used = [
        row["ram_used_percent"]
        for row in snapshots
    ]

    ram_available = [
        row["ram_available_bytes"] / MIB
        for row in snapshots
    ]

    active = [
        row["active_sessions"]
        for row in snapshots
    ]

    swap_used = [
        row["swap_used_bytes"] / MIB
        for row in snapshots
    ]

    timestamps = [
        parse_timestamp(row["timestamp_utc"])
        for row in snapshots
    ]

    duration_seconds = (
        timestamps[-1] - timestamps[0]
    ).total_seconds()

    gaps = [
        (timestamps[i] - timestamps[i - 1]).total_seconds()
        for i in range(1, count)
    ]

    positive_gaps = [gap for gap in gaps if gap > 0]

    sampling_interval = (
        median(positive_gaps)
        if positive_gaps else None
    )

    # Cap large gaps to avoid treating an outage
    # as complete monitoring coverage.
    if sampling_interval:
        covered_seconds = sum(
            min(gap, 3 * sampling_interval)
            for gap in positive_gaps
        )
    else:
        covered_seconds = 0

    coverage = min(
        1.0,
        covered_seconds / (minutes * 60),
    )

    # PostgreSQL temporary statistics are
    # cumulative, so calculate differences
    # between consecutive snapshots.
    total_temp_bytes = 0
    total_temp_files = 0
    valid_seconds = 0
    valid_intervals = 0
    invalid_intervals = 0
    peak_temp_mb_min = 0.0

    for i in range(1, count):
        previous = snapshots[i - 1]
        current = snapshots[i]

        elapsed = (
            timestamps[i] - timestamps[i - 1]
        ).total_seconds()

        if elapsed <= 0:
            invalid_intervals += 1
            continue

        # Ignore gaps longer than 3 normal
        # sampling intervals.
        if (
            sampling_interval
            and elapsed > 3 * sampling_interval
        ):
            invalid_intervals += 1
            continue

        old_dbs = databases.get(previous["id"], {})
        new_dbs = databases.get(current["id"], {})

        # Require the same monitored database set.
        if not old_dbs or old_dbs.keys() != new_dbs.keys():
            invalid_intervals += 1
            continue

        interval_bytes = 0
        interval_files = 0
        interval_valid = True

        for datid, new in new_dbs.items():
            old = old_dbs[datid]

            # A statistics reset invalidates
            # the counter difference.
            if old["stats_reset"] != new["stats_reset"]:
                interval_valid = False
                break

            byte_delta = (
                new["temp_bytes"] - old["temp_bytes"]
            )
            file_delta = (
                new["temp_files"] - old["temp_files"]
            )

            if byte_delta < 0 or file_delta < 0:
                interval_valid = False
                break

            interval_bytes += byte_delta
            interval_files += file_delta

        if not interval_valid:
            invalid_intervals += 1
            continue

        valid_intervals += 1
        valid_seconds += elapsed
        total_temp_bytes += interval_bytes
        total_temp_files += interval_files

        rate = (
            interval_bytes / MIB
            / elapsed * 60
        )

        peak_temp_mb_min = max(
            peak_temp_mb_min, rate
        )

    # Rates use only valid observation intervals.
    avg_temp_mb_min = (
        total_temp_bytes / MIB
        / valid_seconds * 60
        if valid_seconds > 0 else None
    )

    interval_count = max(0, count - 1)
    valid_fraction = (
        valid_intervals / interval_count
        if interval_count else 0
    )

    valid_baseline = (
        count >= MIN_SAMPLES
        and duration_seconds >= MIN_DURATION_MINUTES * 60
        and coverage >= MIN_COVERAGE
        and valid_fraction >= MIN_VALID_TEMP_INTERVALS
    )

    if valid_baseline:
        reason = "Sufficient monitoring coverage"
    else:
        reason = (
            "Insufficient duration, sample coverage, "
            "or valid temporary I/O intervals"
        )

    return {
        "observation_minutes": minutes,
        "samples": count,
        "observed_duration_minutes": round(
            duration_seconds / 60, 2
        ),
        "coverage_ratio": round(coverage, 3),
        "sampling_interval_seconds": (
            round(sampling_interval, 2)
            if sampling_interval else None
        ),
        "memory": {
            "avg_ram_used_percent": round(
                mean(ram_used), 2
            ),
            "max_ram_used_percent": max(ram_used),
            "min_ram_available_mb": round(
                min(ram_available), 2
            ),
            "max_swap_used_mb": round(
                max(swap_used), 2
            ),
        },
        "activity": {
            "avg_active_sessions": round(
                mean(active), 2
            ),
            "p95_active_sessions": percentile(
                active, 95
            ),
            "max_active_sessions": max(active),
        },
        "temporary_io": {
            "total_written_mb": round(
                total_temp_bytes / MIB, 2
            ),
            "total_temp_files": total_temp_files,
            "avg_mb_per_min": (
                round(avg_temp_mb_min, 2)
                if avg_temp_mb_min is not None
                else None
            ),
            "peak_mb_per_min": (
                round(peak_temp_mb_min, 2)
                if valid_intervals else None
            ),
            "valid_intervals": valid_intervals,
            "invalid_intervals": invalid_intervals,
        },
        "baseline_status": (
            "VALID" if valid_baseline
            else "INSUFFICIENT_DATA"
        ),
        "reason": reason,
    }

