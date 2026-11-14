# PG Memory Agent — Step 2

A minimal, read-only foundation for PostgreSQL instance-level `work_mem` monitoring.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -v
export PGMEM_CONNINFO='host=localhost port=5432 dbname=postgres user=pg_memory_monitor'
pg-memory-agent status
```

Use `.pgpass` or other libpq credential providers instead of putting a password in the command line. `status` only reads `pg_settings`.

Next: implement OS and PostgreSQL workload collectors, time-series sampling and safe budget analysis.

## Step 3: workload metrics (read only)

```bash
export PGMEM_CONNINFO='host=localhost port=5432 dbname=postgres user=postgres'
pg-memory-agent metrics
pg-memory-agent metrics --interval 10
pg-memory-agent metrics --interval 10 --queries
pytest -v
```

`metrics` reads Linux RAM, swap and (where available) cgroup v2 memory
plus PostgreSQL client-session counts and cumulative temporary-file
counters for all databases. `--interval` calculates reset-aware rates
in MB/minute per database. Rates require two observations; the initial
snapshot cannot provide them. `--queries` optionally shows top spilling
statements, but only if `pg_stat_statements` is installed in the
connected database, loaded and accessible. The displayed statement
statistics are cumulative, **not** deltas. Query texts may contain
sensitive application data; omit `--queries` if not needed.

The collector never changes PostgreSQL configuration. This is *not* a
memory tuning recommendation. For a remote PostgreSQL server, the Linux
metrics refer to the machine running this CLI, not the database host.
Do not use these metrics for tuning unless both run on the same host,
or a remote OS collector is introduced. With multiple cgroup setups,
the cgroup v2 fields may be null or refer to a parent slice; validate
what they represent before interpreting them as PostgreSQL limits.
