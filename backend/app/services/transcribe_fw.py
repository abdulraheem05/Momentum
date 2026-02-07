import os
import platform
from pathlib import Path

# Only run this DLL logic on Windows
if platform.system() == "Windows":
    # Get the base path of your venv
    venv_base = Path(os.environ.get('VIRTUAL_ENV', '.'))
    
    # Define the paths to the bin folders we verified exist
    nvidia_bin_paths = [
        venv_base / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin",
        venv_base / "Lib" / "site-packages" / "nvidia" / "cudnn" / "bin",
    ]

    for path in nvidia_bin_paths:
        if path.exists():
            os.add_dll_directory(str(path.resolve()))
            print(f"Added to DLL search path: {path}")
        else:
            print(f"Warning: Could not find NVIDIA bin path: {path}")

from faster_whisper import WhisperModel

def transcribe_audio(audio_path: Path, language: str | None, model_size: str = "small" ) -> dict :
    model = WhisperModel(model_size, device="cuda", compute_type="float16")

    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True
    )
    
    out_segments = []
    for s in segments:
        text = (s.text or "").strip()
        if text:
            out_segments.append({
                "start": float(s.start),
                "end": float(s.end),
                "text": text,
            })

    return {
        "language": info.language,
        "duration": float(info.duration),
        "segments": out_segments,
    }    

    