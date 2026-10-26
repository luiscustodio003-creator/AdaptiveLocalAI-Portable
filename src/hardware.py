"""Portable hardware discovery with conservative fallbacks."""
from __future__ import annotations

import os
import platform
import re
import shutil
from pathlib import Path
from typing import Any


def _memory_bytes() -> tuple[int | None, int | None, str]:
    """Return (total, available, source) without requiring optional packages."""
    try:
        import psutil  # type: ignore
        memory = psutil.virtual_memory()
        return int(memory.total), int(memory.available), "psutil"
    except Exception:
        pass

    system = platform.system()
    try:
        if system == "Linux":
            values: dict[str, int] = {}
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                match = re.match(r"^(MemTotal|MemAvailable|MemFree):\s+(\d+)\s+kB", line)
                if match:
                    values[match.group(1)] = int(match.group(2)) * 1024
            total = values.get("MemTotal")
            available = values.get("MemAvailable", values.get("MemFree"))
            return total, available, "proc_meminfo"
        if system == "Darwin":
            import subprocess
            total_out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                                       text=True, timeout=2, check=True)
            total = int(total_out.stdout.strip())
            page = subprocess.run(["vm_stat"], capture_output=True, text=True,
                                  timeout=2, check=True).stdout
            page_size_match = re.search(r"page size of (\d+) bytes", page)
            free_match = re.search(r"Pages free:\s+(\d+)", page)
            inactive_match = re.search(r"Pages inactive:\s+(\d+)", page)
            page_size = int(page_size_match.group(1)) if page_size_match else 4096
            available = ((int(free_match.group(1)) if free_match else 0) +
                         (int(inactive_match.group(1)) if inactive_match else 0)) * page_size
            return total, available or None, "sysctl_vm_stat"
        if system == "Windows":
            import ctypes
            from ctypes import wintypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullTotalPhys), int(status.ullAvailPhys), "GlobalMemoryStatusEx"
    except Exception:
        pass
    return None, None, "unavailable"


def detect_hardware() -> dict[str, Any]:
    logical = max(1, os.cpu_count() or 1)
    physical: int | None = None
    try:
        import psutil  # type: ignore
        physical = psutil.cpu_count(logical=False)
    except Exception:
        pass
    # Never assert that half the logical CPUs are physical cores.
    physical = int(physical) if physical and physical > 0 else None
    total, available, memory_source = _memory_bytes()
    machine = platform.machine().lower() or "unknown"
    system = platform.system().lower() or "unknown"
    cpu_flags: list[str] = []
    if system == "linux":
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").lower()
            match = re.search(r"^(?:flags|features)\s*:\s*(.+)$", cpuinfo, re.MULTILINE)
            if match:
                available_flags = set(match.group(1).split())
                cpu_flags = sorted(flag for flag in ("avx", "avx2", "avx512f", "fma", "neon", "asimd", "sse4_2")
                                   if flag in available_flags)
        except OSError:
            pass
    elif system == "darwin" and machine in {"arm64", "aarch64"}:
        cpu_flags = ["neon"]
    elif system == "windows":
        # Windows APIs do not expose a complete, portable CPU-feature set.
        # Leave it unknown rather than guessing from the CPU name.
        cpu_flags = []
    return {
        "system": system,
        "release": platform.release(),
        "machine": machine,
        "processor": platform.processor() or "unknown",
        "physical_cores": physical,
        "logical_threads": logical,
        "cpu_features": cpu_flags,
        "memory_total_bytes": total,
        "memory_available_bytes": available,
        "memory_source": memory_source,
        "gpu": {"detected": False, "usable": False, "devices": [], "source": "not_probed"},
        "disk_free_bytes": shutil.disk_usage(Path.cwd()).free if Path.cwd().exists() else None,
    }
