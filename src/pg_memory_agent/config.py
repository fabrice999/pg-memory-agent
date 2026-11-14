from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    conninfo: str
    mode: str = "recommend"


def load_settings(conninfo: str | None = None) -> Settings:
    # Empty conninfo permits libpq environment variables/.pgpass.
    return Settings(conninfo=conninfo if conninfo is not None else os.getenv("PGMEM_CONNINFO", ""))
