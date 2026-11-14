
import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS metric_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_utc TEXT NOT NULL,
    ram_total_bytes INTEGER NOT NULL,
    ram_available_bytes INTEGER NOT NULL,
    ram_used_percent REAL NOT NULL,
    swap_used_bytes INTEGER NOT NULL,
    active_sessions INTEGER NOT NULL,
    client_sessions INTEGER NOT NULL,
    idle_in_transaction_sessions INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS database_metrics (
    snapshot_id INTEGER NOT NULL,
    datid TEXT NOT NULL,
    datname TEXT NOT NULL,
    temp_files INTEGER NOT NULL,
    temp_bytes INTEGER NOT NULL,
    stats_reset TEXT,
    FOREIGN KEY (snapshot_id)
        REFERENCES metric_snapshots(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_snapshot_time
ON metric_snapshots(timestamp_utc);
"""


class MetricsStore:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(
            parents=True, exist_ok=True
        )

        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)

    def save_snapshot(self, snapshot):
        linux = snapshot["linux"]
        postgres = snapshot["postgresql"]
        activity = postgres["activity"]

        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO metric_snapshots (
                    timestamp_utc,
                    ram_total_bytes,
                    ram_available_bytes,
                    ram_used_percent,
                    swap_used_bytes,
                    active_sessions,
                    client_sessions,
                    idle_in_transaction_sessions
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot["timestamp_utc"],
                    linux["ram_total_bytes"],
                    linux["ram_available_bytes"],
                    linux["ram_used_percent"],
                    linux["swap_used_bytes"],
                    activity["active_sessions"],
                    activity["client_sessions"],
                    activity["idle_in_transaction_sessions"],
                ),
            )

            snapshot_id = cursor.lastrowid

            for db in postgres["databases"]:
                self.conn.execute(
                    """
                    INSERT INTO database_metrics (
                        snapshot_id,
                        datid,
                        datname,
                        temp_files,
                        temp_bytes,
                        stats_reset
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        db["datid"],
                        db["datname"],
                        db["temp_files"],
                        db["temp_bytes"],
                        db["stats_reset"],
                    ),
                )

        return snapshot_id

    def count_snapshots(self):
        row = self.conn.execute(
            "SELECT COUNT(*) FROM metric_snapshots"
        ).fetchone()

        return row[0]

    def close(self):
        self.conn.close()

