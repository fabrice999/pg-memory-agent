from pg_memory_agent.collector.postgres import PARAMETERS, collect_configuration
from pg_memory_agent.cli import main


def test_expected_settings_exist():
    assert "work_mem" in PARAMETERS
    assert "hash_mem_multiplier" in PARAMETERS


def test_read_only_collector(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.last_sql = ""
        def execute(self, sql, params=None):
            assert sql.lstrip().upper().startswith("SELECT")
            self.last_sql = sql
        def fetchone(self):
            return {"database_name": "postgres", "server_version": "18.0"}
        def fetchall(self):
            return [{"name": name, "setting": ("16384" if name == "work_mem" else "2"), "unit": ("kB" if name == "work_mem" else None), "source": "default"} for name in PARAMETERS]
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    class FakeConnection:
        def cursor(self):
            return FakeCursor()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    monkeypatch.setattr("pg_memory_agent.collector.postgres.psycopg.connect", lambda *a, **kw: FakeConnection())
    result = collect_configuration("")
    assert result["work_mem_mb"] == 16
    assert result["scope"] == "instance"


def test_cli_status(monkeypatch, capsys):
    monkeypatch.setattr("pg_memory_agent.cli.collect_configuration", lambda c: {"work_mem_mb": 16})
    assert main(["status"]) == 0
    assert "16" in capsys.readouterr().out
