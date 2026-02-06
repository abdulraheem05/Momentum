from pathlib import Path
from typing import Optional

from app.core.paths import UPLOADS_DIR

VIDEO_EXTS = (".mp4", ".mkv", ".mov", ".webm", ".avi")


def find_video_path(video_id: str) -> Optional[Path]:
    """
    Find an uploaded video file by video_id regardless of extension.
    """
    for ext in VIDEO_EXTS:
        p = UPLOADS_DIR / f"{video_id}{ext}"
        if p.exists():
            return p

    # fallback: scan uploads dir (handles odd extensions)
    for p in UPLOADS_DIR.glob(f"{video_id}.*"):
        if p.is_file():
            return p

    return None