import subprocess

def run_ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "ffmpeg failed")

def extract_audio_wav(input_path: str, audio_out: str) -> None:
    """Extracts audio from a local path or URL."""
    run_ffmpeg([
        "-i", input_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-f", "wav",
        audio_out
    ])

def optimize_video_faststart(input_path: str, output_path: str) -> None:
    """
    Moves metadata to the front of the file. 
    This fixes the 'stuck' video issue in the browser.
    """
    run_ffmpeg([
        "-i", input_path,
        "-c", "copy",          # Don't re-encode, just copy (fast!)
        "-movflags", "+faststart", 
        output_path
    ])