import subprocess
from pathlib import Path

def extract_frames(
        video_path: Path,
        frame_out: Path,
        every_n_sec: int = 3,
        width: int = 320,
) -> None:
    frame_out.mkdir(parents=True, exist_ok=True)
    out_pattern = str(frame_out/"frame_%06d.jpg")

    vf = f"fps=1/{every_n_sec}, scale={width}:-1"

    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error",
        "-i", str(video_path),
        "-vf", vf,
        "-q:v", "2",
        out_pattern
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffmpeg frame extraction failed")