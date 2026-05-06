import subprocess

def run_ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffmpeg failed")

def extract_audio_wav(video_url: str, audio_out: str) -> None:
    run_ffmpeg([
        "-i", video_url,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-f", "wav",
        audio_out
    ])