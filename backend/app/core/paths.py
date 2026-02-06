from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = ROOT_DIR/"data"

UPLOADS_DIR = DATA_DIR/"uploads"
AUDIO_DIR = DATA_DIR/"audio"
TRANSCRIPTS_DIR = DATA_DIR/"transcriptions"
INDEX_TEXT_DIR = DATA_DIR/"index"/"text"
INDEX_FRAMES_DIR = DATA_DIR/"index"/"frames"
CLIPS_DIR = DATA_DIR/"clips"

def ensure_dir() -> None:
    for p in [
        DATA_DIR,
        UPLOADS_DIR,
        AUDIO_DIR,
        TRANSCRIPTS_DIR,
        INDEX_TEXT_DIR,
        INDEX_FRAMES_DIR,
        CLIPS_DIR
    ]:
        p.mkdir(parents=True, exist_ok=True) 
