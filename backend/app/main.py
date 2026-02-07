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

def convert_sec_to_hhmmss(seconds: float) -> str:
    s = int(max(0.0, seconds))
    hours = s // 3600
    minutes = s % 3600 // 60
    seconds = s % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def _normalize(input: str) -> str:
    return " ".join(input.lower().strip().split())


def process_video(video_id: str):

    try:
        row = get_video(video_id)
        if not row:
            return
        
        video_path = find_video_path(video_id)
        if not video_path:
            update_status(video_id, "FAILED", 0, "Video not found")

        language = row["language"]
        model_size = row["model_size"]

        update_status(video_id, "EXTRACTING", 10)
        audio_path = AUDIO_DIR/f"{video_id}.wav"
        extract_audio_wav(video_path, audio_path)

        update_status(video_id, "TRANSCRIBING", 40)
        transcript = transcribe_audio(audio_path, language, model_size)

        update_status(video_id, "SAVED TRANSCRIPT", 85)
        save_transcript(video_id, transcript)

        update_status(video_id, "READY", 100)

    except Exception as e:
        update_status(video_id, "FAILED", 0, str(e))

    
class SearchRequest(BaseModel):
    query : str = Field(..., min_length=2)
    top_k : int = Field(default=3, ge=1, le=5)
    clip_duration : float = Field(default=10.0, ge=1.0, le=20.0)

@app.post("/videos")
async def create_new_video(
        background_tasks : BackgroundTasks,
        file : UploadFile = File (...),
        language : str = "en",
        model_size : str = "small"
) : 
    if not language in ("en","ta"):
        raise HTTPException(status_code=400, detail="Language must be en or ta")
    
    video_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower() or ".mp4"
    dest = UPLOADS_DIR/f"{video_id}{ext}"

    try:
        with open (dest, "wb") as out:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                out.write(chunk)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File uplload failed: {e}")
    

    create_video(video_id, language, model_size)
    background_tasks.add_task(process_video, video_id)

    return {
        "video_id": video_id,
        "message": "Uploaded successfully. We are processing your video..."
    }


@app.get("/videos/{video_id}/status")
def status(video_id: str):
    row = get_video(video_id)
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")
    
    return {
        "video_id": video_id,
        "stage": row["stage"],
        "progress": row["progress"],
        "ready_to_search": row["stage"] == "READY",
        "error": row["error"]
    }


@app.post("/videos/{video_id}/search")
def search(video_id: str, body: SearchRequest):
    row = get_video(video_id)
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")
    
    if row["stage"] != "READY":
        raise HTTPException(status_code=409, detail=f"Video not ready yet. Status: {row['stage']}")
    

    data = load_transcript(video_id)
    segments = data.get("segments", [])

    query = _normalize(body.query)
    q_words = query.split()

    scored = []

    for s in segments:
        text = _normalize(s["text"])
        score = sum(1 for w in q_words if w in text)
        if query in text:
            score += 3
        if score > 0:
            scored.append((score, s))

    
    scored.sort(key = lambda x : x[0], reverse = True)

    results = []
    for score, seg in scored[:body.top_k]:
        start = seg["start"]
        clip_url = f"/videos/{video_id}/clip?start={start}&dur={body.clip_duration}"

        results.append({
            "score": score,
            "timestamp": convert_sec_to_hhmmss(start),
            "start": start,
            "text": seg["text"],
            "clip_url": clip_url
        })

    best = results[0] if results else None
    alternates = results[1:] if len(results) > 1 else []

    return {
        "video_id": video_id,
        "best": best,
        "alternates": alternates
    }
    
@app.get("/videos/{video_id}/clip")
def clip(video_id: str, start: float, duration: float = 10.0):
    video_path = find_video_path(video_id)
    if not video_path:
        raise HTTPException(status_code=404, detail="video not found")
    
    out_path = CLIPS_DIR/ video_id /f"{int(start)}_{int(duration)}.mp4"

    if not out_path.exists():
        cut_clip(video_path, out_path, start, duration)

    return FileResponse(str(out_path), media_type="video/mp4")



















@app.get("/health")
def health():
    return{"ok":True}
