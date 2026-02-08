import json
from pathlib import Path
from app.core.paths import TRANSCRIPTS_DIR


def transcript_path(video_id: str) -> Path:
    return TRANSCRIPTS_DIR / f"{video_id}.json"


def save_transcript(video_id: str, data: dict) -> Path:
    p = transcript_path(video_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_transcript(video_id: str) -> dict:
    p = transcript_path(video_id)
    return json.loads(p.read_text(encoding="utf-8"))
