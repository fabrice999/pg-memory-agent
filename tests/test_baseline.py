
from datetime import datetime, timedelta, timezone

from pg_memory_agent.analyzer.baseline import (
    analyze_baseline,
    percentile,
)
from pg_memory_agent.storage.sqlite import MetricsStore


def create_snapshot(timestamp, temp_bytes, active=2):
    return {
        "timestamp_utc": timestamp.isoformat(),
        "linux": {
            "ram_total_bytes": 32 * 1024**3,
            "ram_available_bytes": 20 * 1024**3,
            "ram_used_percent": 37.5,
            "swap_used_bytes": 0,
        },
        "postgresql": {
            "activity": {
                "active_sessions": active,
                "client_sessions": active + 2,
                "idle_in_transaction_sessions": 0,
            },
            "databases": [
                {
                    "datid": "5",
                    "datname": "postgres",
                    "temp_files": temp_bytes // (1024**2),
                    "temp_bytes": temp_bytes,
                    "stats_reset": None,
                }
            ],
        },
    }


def test_percentile():
    values = list(range(1, 101))

    assert percentile(values, 95) == 95
    assert percentile(values, 50) == 50
    assert percentile([], 95) is None


def test_valid_baseline(tmp_path):
    path = tmp_path / "metrics.db"
    store = MetricsStore(path)

    now = datetime(
        2026, 11, 14, 12, 0,
        tzinfo=timezone.utc,
    )

    # 61 snapshots, spanning exactly 60 minutes.
    # Temporary data grows by 1 MiB per minute.
    for i in range(61):
        timestamp = now - timedelta(minutes=60 - i)

        store.save_snapshot(
            create_snapshot(
                timestamp=timestamp,
                temp_bytes=i * 1024**2,
                active=10 if i == 60 else 2,
            )
        )

    store.close()

    result = analyze_baseline(
        db_path=path,
        minutes=60,
        now=now,
    )

    assert result["samples"] == 61
    assert result["baseline_status"] == "VALID"

    assert result["activity"]["p95_active_sessions"] == 2
    assert result["activity"]["max_active_sessions"] == 10

    assert result["temporary_io"]["total_written_mb"] == 60
    assert result["temporary_io"]["avg_mb_per_min"] == 1
    assert result["temporary_io"]["valid_intervals"] == 60


def test_insufficient_data(tmp_path):
    path = tmp_path / "metrics.db"
    store = MetricsStore(path)

    now = datetime.now(timezone.utc)

    for i in range(3):
        store.save_snapshot(
            create_snapshot(
                timestamp=now - timedelta(seconds=20 - i * 10),
                temp_bytes=i * 1024**2,
            )
        )

    store.close()

    result = analyze_baseline(
        db_path=path,
        minutes=60,
        now=now,
    )

    assert result["samples"] == 3
    assert (
        result["baseline_status"]
        == "INSUFFICIENT_DATA"
    )

