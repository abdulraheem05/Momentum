import subprocess
from pathlib import Path

def run_ffmpeg(args: list[str]) -> None:

    cmd = ["ffmpeg","-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffmpeg failed")
    
def extract_audio_wav (video_path : Path, audio_out: Path) -> None:
    audio_out.parent.mkdir(parents=True, exist_ok=True)

    run_ffmpeg([
        "-i", str(video_path),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-f", "wav"    
    ])

