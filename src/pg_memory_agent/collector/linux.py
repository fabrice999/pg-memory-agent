"""Read-only host and cgroup memory observation."""
from pathlib import Path
import psutil


def _read_cgroup_int(path: Path) -> int | None:
    try:
        value = path.read_text(encoding="ascii").strip()
        return None if value == "max" else int(value)
    except (OSError, ValueError):
        return None


def collect_linux_memory(cgroup_root: Path = Path("/sys/fs/cgroup")) -> dict:
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    limit = _read_cgroup_int(cgroup_root / "memory.max")
    current = _read_cgroup_int(cgroup_root / "memory.current")
    return {
        "ram_total_bytes": mem.total,
        "ram_available_bytes": mem.available,
        "ram_used_percent": mem.percent,
        "swap_total_bytes": swap.total,
        "swap_used_bytes": swap.used,
        "cgroup_v2_memory_max_bytes": limit,
        "cgroup_v2_memory_current_bytes": current,
        "cgroup_v2_memory_available_bytes": max(0, limit - current) if limit is not None and current is not None else None,
    }
