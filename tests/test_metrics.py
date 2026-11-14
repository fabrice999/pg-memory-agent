from datetime import datetime, timezone
from pg_memory_agent.collector.linux import collect_linux_memory
from pg_memory_agent.collector.snapshot import calculate_temp_rates
from pg_memory_agent.cli import main


def _snapshot(bytes_count, files_count, reset=None):
    return {"postgresql": {"databases": [
        {"datid": "5", "datname": "postgres", "temp_bytes": bytes_count,
         "temp_files": files_count, "stats_reset": reset}
    ]}}


def test_temp_rate_delta():
    before = _snapshot(0, 2)
    after = _snapshot(10 * 1024 * 1024, 3)
    row = calculate_temp_rates(before, after, 60)["per_database"][0]
    assert row["status"] == "ok"
    assert row["temp_mb_per_min"] == 10
    assert row["temp_files_delta"] == 1


def test_reset_invalidates_delta():
    before = _snapshot(10, 2, "old")
    after = _snapshot(100, 3, "new")
    assert calculate_temp_rates(before, after, 60)["per_database"][0]["status"] == "baseline_unavailable_or_reset"


def test_linux_collector(monkeypatch, tmp_path):
    class Mem:
        total = 16 * 1024**3
        available = 8 * 1024**3
        percent = 50
    class Swap:
        total = 1024
        used = 256
    monkeypatch.setattr("pg_memory_agent.collector.linux.psutil.virtual_memory", lambda: Mem())
    monkeypatch.setattr("pg_memory_agent.collector.linux.psutil.swap_memory", lambda: Swap())
    (tmp_path / "memory.max").write_text("1073741824\n")
    (tmp_path / "memory.current").write_text("268435456\n")
    result = collect_linux_memory(tmp_path)
    assert result["ram_used_percent"] == 50
    assert result["cgroup_v2_memory_available_bytes"] == 805306368


def test_cli_metrics(monkeypatch, capsys):
    monkeypatch.setattr("pg_memory_agent.cli.collect_snapshot", lambda conninfo, include_queries: {"scope": "instance", "linux": {"ram_total_bytes": 123}})
    assert main(["metrics"]) == 0
    assert '"ram_total_bytes": 123' in capsys.readouterr().out
