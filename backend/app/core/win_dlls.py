import os
import platform
from pathlib import Path

def patch_nvidia_dlls() -> None:
    """
    Windows-only. Ensures PyTorch/Transformers load the correct cuDNN/cuBLAS
    DLLs from the venv's site-packages/nvidia/*/bin folders.
    Must run BEFORE importing torch/transformers.
    """
    if platform.system() != "Windows":
        return

    venv = os.environ.get("VIRTUAL_ENV")
    if not venv:
        return

    nvidia_base = Path(venv) / "Lib" / "site-packages" / "nvidia"
    if not nvidia_base.exists():
        return

    for folder in nvidia_base.iterdir():
        bin_path = folder / "bin"
        if bin_path.exists():
            os.add_dll_directory(str(bin_path.resolve()))
