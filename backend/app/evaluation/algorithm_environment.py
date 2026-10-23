"""Machine and source identity for offline algorithm timing reports."""

import os
import platform
import subprocess
from pathlib import Path


def environment():
    cpu = platform.processor() or "not recorded"
    if platform.system() == "Windows":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                cpu = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass
    elif Path("/proc/cpuinfo").exists():
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                cpu = line.partition(":")[2].strip()
                break
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = "not recorded", None
    return {
        "cpu_model": cpu,
        "logical_cpu_count": os.cpu_count(),
        "physical_core_count": "not recorded",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "code_commit": commit,
        "working_tree_dirty": dirty,
    }
