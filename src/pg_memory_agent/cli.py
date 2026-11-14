
"""Command-line interface for PG Memory Agent."""

import argparse
import json
import sqlite3
import sys

import psycopg

from pg_memory_agent import __version__
from pg_memory_agent.analyzer.baseline import analyze_baseline
from pg_memory_agent.collector.postgres import collect_configuration
from pg_memory_agent.collector.snapshot import (
    collect_snapshot,
    collect_interval,
)
from pg_memory_agent.config import load_settings
from pg_memory_agent.monitor.runner import run_monitor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pg-memory-agent",
        description=(
            "PostgreSQL memory monitoring and "
            "work_mem optimization agent"
        ),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    # STATUS
    status = sub.add_parser(
        "status",
        help="Display PostgreSQL memory configuration",
    )
    status.add_argument(
        "--conninfo",
        help="Overrides PGMEM_CONNINFO / libpq defaults",
    )

    # METRICS
    metrics = sub.add_parser(
        "metrics",
        help="Collect Linux and PostgreSQL metrics",
    )
    metrics.add_argument(
        "--conninfo",
        help="Overrides PGMEM_CONNINFO / libpq defaults",
    )
    metrics.add_argument(
        "--interval",
        type=float,
        default=0,
        metavar="SECONDS",
        help="Sample interval (0 or 1-3600 seconds)",
    )
    metrics.add_argument(
        "--queries",
        action="store_true",
        help="Include pg_stat_statements observations",
    )

    # MONITOR
    monitor = sub.add_parser(
        "monitor",
        help="Continuously collect and persist metrics",
    )
    monitor.add_argument(
        "--conninfo",
        help="Overrides PGMEM_CONNINFO / libpq defaults",
    )
    monitor.add_argument(
        "--interval",
        type=float,
        default=10,
        metavar="SECONDS",
        help="Sampling interval (default: 10 seconds)",
    )
    monitor.add_argument(
        "--db-path",
        default="data/metrics.db",
        help="SQLite metrics database",
    )
    monitor.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Stop after N samples",
    )

    # BASELINE
    baseline = sub.add_parser(
        "baseline",
        help="Analyze historical memory and workload metrics",
    )
    baseline.add_argument(
        "--minutes",
        type=int,
        default=60,
        help="Historical observation window (default: 60)",
    )
    baseline.add_argument(
        "--db-path",
        default="data/metrics.db",
        help="SQLite metrics database",
    )

    args = parser.parse_args(argv)

    # STATUS EXECUTION
    if args.command == "status":
        try:
            conninfo = load_settings(args.conninfo).conninfo
            result = collect_configuration(conninfo)
        except (psycopg.Error, RuntimeError) as exc:
            print(
                "Unable to read PostgreSQL configuration "
                f"({type(exc).__name__}).",
                file=sys.stderr,
            )
            return 1

        print(json.dumps(result, indent=2, default=str))
        return 0

    # METRICS EXECUTION
    if args.command == "metrics":
        if not (
            args.interval == 0
            or 1 <= args.interval <= 3600
        ):
            parser.error(
                "--interval must be 0 or between "
                "1 and 3600 seconds"
            )

        try:
            conninfo = load_settings(args.conninfo).conninfo

            if args.interval > 0:
                result = collect_interval(
                    conninfo,
                    args.interval,
                    args.queries,
                )
            else:
                result = collect_snapshot(
                    conninfo,
                    args.queries,
                )

        except (psycopg.Error, RuntimeError, OSError) as exc:
            print(
                f"Unable to collect metrics "
                f"({type(exc).__name__}).",
                file=sys.stderr,
            )
            return 1

        print(json.dumps(result, indent=2, default=str))
        return 0

    # MONITOR EXECUTION
    if args.command == "monitor":
        if not 1 <= args.interval <= 3600:
            parser.error(
                "--interval must be between "
                "1 and 3600 seconds"
            )

        if args.max_samples is not None and args.max_samples < 1:
            parser.error(
                "--max-samples must be a positive integer"
            )

        try:
            conninfo = load_settings(args.conninfo).conninfo

            run_monitor(
                conninfo=conninfo,
                interval=args.interval,
                db_path=args.db_path,
                max_samples=args.max_samples,
            )

        except (
            psycopg.Error,
            RuntimeError,
            OSError,
        ) as exc:
            print(
                f"Monitoring failed "
                f"({type(exc).__name__}).",
                file=sys.stderr,
            )
            return 1

        return 0

    # BASELINE EXECUTION
    if args.command == "baseline":
        if not 1 <= args.minutes <= 10080:
            parser.error(
                "--minutes must be between 1 and 10080"
            )

        try:
            result = analyze_baseline(
                db_path=args.db_path,
                minutes=args.minutes,
            )

        except (
            OSError,
            sqlite3.DatabaseError,
            ValueError,
        ) as exc:
            print(
                f"Baseline analysis failed: {exc}",
                file=sys.stderr,
            )
            return 1

        print(json.dumps(result, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

