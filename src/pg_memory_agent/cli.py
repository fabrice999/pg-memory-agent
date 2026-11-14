import argparse
import json
import sys

import psycopg

from pg_memory_agent import __version__
from pg_memory_agent.collector.postgres import collect_configuration
from pg_memory_agent.collector.snapshot import collect_snapshot, collect_interval
from pg_memory_agent.config import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pg-memory-agent")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="Display current PostgreSQL memory settings (read only)")
    status.add_argument("--conninfo", help="Overrides PGMEM_CONNINFO / libpq defaults")
    metrics = sub.add_parser("metrics", help="Read Linux and PostgreSQL workload metrics")
    metrics.add_argument("--conninfo", help="Overrides PGMEM_CONNINFO / libpq defaults")
    metrics.add_argument("--interval", type=float, default=0, metavar="SECONDS", help="Take two snapshots to compute temporary I/O rates (1-3600 seconds)")
    metrics.add_argument("--queries", action="store_true", help="Include top spilling statements when pg_stat_statements is available")
    args = parser.parse_args(argv)
    if args.command == "status":
        try:
            result = collect_configuration(load_settings(args.conninfo).conninfo)
        except (psycopg.Error, RuntimeError) as exc:
            # Do not expose connection strings/passwords in the error output.
            print(f"Unable to read PostgreSQL configuration ({type(exc).__name__}).", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "metrics":
        if not (0 <= args.interval <= 3600):
            parser.error("--interval must be between 0 and 3600 seconds")
        try:
            conninfo = load_settings(args.conninfo).conninfo
            result = (collect_interval(conninfo, args.interval, args.queries)
                      if args.interval > 0 else collect_snapshot(conninfo, args.queries))
        except (psycopg.Error, RuntimeError, OSError) as exc:
            print(f"Unable to collect metrics ({type(exc).__name__}).", file=sys.stderr)
            return 1
        print(json.dumps(result, indent=2, default=str))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
