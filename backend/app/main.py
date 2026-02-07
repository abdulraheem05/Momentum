import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, Query, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.paths import ensure_dir, UPLOADS_DIR, AUDIO_DIR, CLIPS_DIR
from app.db.state import init_db, create_video, update_status, get_video, delete_video_row
from app.services.video_store import find_video_path
from app.services.ffmpeg_utils import extract_audio_wav, cut_clip
from app.services.transcribe_fw import transcribe_audio
from app.services.transcript_store import save_transcript, load_transcript, transcript_path

app = FastAPI(title="Video Scene Finder")

app.add_middleware(
    CORSMiddleware,
    allow_origins = ["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"]
)

ensure_dir()
init_db()

CHUNK_SIZE = 1024*1024

@app.get("/health")
def health():
    return{"ok":True}

def convert_sec_to_hhmmss(seconds: float) -> str:
    s = int(max(0.0, seconds))
    hours = s // 3600
    minutes = s % 3600 // 60
    seconds = s % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def _normalize(input: str) -> str:
    return " ".join(input.lower().strip().split())

@app.post("/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException("File not found")
    
    if not file.filename.lower().endswith((".mp4", ".mov", ".mkv")):
        raise HTTPException("Fil format not supported")
    
    video_id = str(uuid.uuid4())

    ext = Path(file.filename).suffix.lower() or "mp4"
    dest = UPLOADS_DIR/f"{video_id}{ext}"

    bytes_written = 0

    try:
        with open (dest, "wb") as out:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break

                out.write(chunk)
                bytes_written += len(chunk)

    except Exception as e:
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")
    
    return {
        "video_id": video_id,
        "saved_as": dest.name,
        "size_bytes": bytes_written
    }

@app.post("/videos/{video_id}/extract-audio")
def extract_audio(video_id: str):
    video_path = find_video_path(video_id)

    if not video_path:
        raise HTTPException(status_code=404, detail="Video not found")
    
    audio_out = AUDIO_DIR/f"{video_id}.wav"

    try:
        extract_audio_wav(video_path, audio_out)

    except Exception as e:
        raise HTTPException(status_code=500, detail= str(e))
    
    return {"video_id":video_id, "audio_file":audio_out.name}

@app.post("/videos/{video_id}/transcribe")
def transcribe(video_id: str, language: str = Query(default="en", description="en or ta"), model_size: str = Query(default="small")):
    video_path = find_video_path(video_id)
    if not video_path:
        raise HTTPException(status_code=404, detail="Video not found")

    audio_path = AUDIO_DIR / f"{video_id}.wav"
    if not audio_path.exists():
        raise HTTPException(status_code=400, detail="Audio not found. Run extract-audio first.")

    try:
        data = transcribe_audio(audio_path, language=language, model_size=model_size)
        p = save_transcript(video_id, data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"video_id": video_id, "transcript_file": p.name, "segments": len(data.get("segments", [])), "detected_language": data.get("language")}
