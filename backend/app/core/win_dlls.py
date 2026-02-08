import os
import platform
from pathlib import Path

def add_nvidia_dll_dirs() -> None:
    if platform.system() != "Windows":
        return

    venv = os.environ.get("VIRTUAL_ENV")
    if not venv:
        return

    base = Path(venv)
    paths = [
        base / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin",
        base / "Lib" / "site-packages" / "nvidia" / "cudnn" / "bin",
    ]

    for p in paths:
        if p.exists():
            os.add_dll_directory(str(p.resolve()))
