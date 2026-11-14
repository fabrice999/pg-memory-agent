
from pg_memory_agent.storage.sqlite import MetricsStore


def test_save_snapshot(tmp_path):
    db_path = tmp_path / "metrics.db"
    store = MetricsStore(db_path)

    snapshot = {
        "timestamp_utc": "2026-11-14T12:00:00+00:00",
        "linux": {
            "ram_total_bytes": 32000000000,
            "ram_available_bytes": 28000000000,
            "ram_used_percent": 12.5,
            "swap_used_bytes": 0,
        },
        "postgresql": {
            "activity": {
                "active_sessions": 2,
                "client_sessions": 5,
                "idle_in_transaction_sessions": 0,
            },
            "databases": [
                {
                    "datid": "5",
                    "datname": "postgres",
                    "temp_files": 10,
                    "temp_bytes": 104857600,
                    "stats_reset": None,
                }
            ],
        },
    }

    snapshot_id = store.save_snapshot(snapshot)

    assert snapshot_id == 1
    assert store.count_snapshots() == 1

    row = store.conn.execute(
        """
        SELECT temp_bytes
        FROM database_metrics
        WHERE snapshot_id = ?
        """,
        (snapshot_id,),
    ).fetchone()

    assert row[0] == 104857600

    store.close()

    assert db_path.exists()

