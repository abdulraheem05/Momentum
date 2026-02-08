import subprocess
from pathlib import Path

def run_ffmpeg(args: list[str]) -> None:

    cmd = ["ffmpeg","-y", "-hide_banner", "-loglevel", "error",*args]
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
        "-f", "wav",
        str(audio_out)   
    ])

def cut_clip(video_path: Path, trim_output_path: Path, start_sec: float, duration_sec: float = 10.0) -> None:
    trim_output_path.parent.mkdir(parents=True, exist_ok=True)

    run_ffmpeg([
        "-ss", str(max(0.0, start_sec)),
        "-i", str(video_path),
        "-t", str(duration_sec),
        "-c", "copy",
        str(trim_output_path)
    ])