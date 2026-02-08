import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.paths import ensure_dir, UPLOADS_DIR, AUDIO_DIR, CLIPS_DIR
from app.db.state import init_db, create_job, update_status, get_job, delete_job_row

from app.services.audio.video_store import find_video_path
from app.services.audio.ffmpeg_utils import extract_audio_wav, cut_clip

from app.services.audio.transcribe_fw import transcribe_audio
from app.services.audio.transcript_store import save_transcript, load_transcript, transcript_path

# scene indexing/search (you said you already finished these logics)
from app.services.video.scene_index import build_scene_index
from app.services.video.scene_search import search_scene


app = FastAPI(title="Video Finder (Audio + Scene)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"],
)

ensure_dir()
init_db()

CHUNK_SIZE = 1024 * 1024


# -------------------- helpers --------------------

def convert_sec_to_hhmmss(seconds: float) -> str:
    s = int(max(0.0, float(seconds)))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _normalize(txt: str) -> str:
    return " ".join(txt.lower().strip().split())


async def _save_upload_to_disk(file: UploadFile, job_id: str) -> Path:
    ext = Path(file.filename).suffix.lower() or ".mp4"
    dest = UPLOADS_DIR / f"{job_id}{ext}"

    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                out.write(chunk)
    except Exception as e:
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"File upload failed: {e}")

    return dest


# -------------------- background pipelines --------------------

def process_audio(job_id: str):
    """
    Audio pipeline only:
    UPLOADED -> EXTRACT_AUDIO -> TRANSCRIBE -> SAVE_TRANSCRIPT -> READY_AUDIO
    """
    try:
        row = get_job(job_id)
        if not row:
            return
        if row["mode"] != "audio":
            return

        video_path = find_video_path(job_id)
        if not video_path:
            update_status(job_id, "FAILED_AUDIO", 0, "Video not found on disk")
            return

        language = row.get("language") or "en"
        model_size = row.get("model_size") or "small"

        update_status(job_id, "EXTRACT_AUDIO", 15)
        audio_path = AUDIO_DIR / f"{job_id}.wav"
        extract_audio_wav(video_path, audio_path)

        update_status(job_id, "TRANSCRIBE", 55)
        transcript = transcribe_audio(audio_path, language, model_size)

        update_status(job_id, "SAVE_TRANSCRIPT", 90)
        save_transcript(job_id, transcript)

        update_status(job_id, "READY_AUDIO", 100)

    except Exception as e:
        update_status(job_id, "FAILED_AUDIO", 0, str(e))


def process_scene(job_id: str):
    """
    Scene pipeline only:
    UPLOADED -> SCENE_INDEX -> READY_SCENE
    """
    try:
        row = get_job(job_id)
        if not row:
            return
        if row["mode"] != "scene":
            return

        video_path = find_video_path(job_id)
        if not video_path:
            update_status(job_id, "FAILED_SCENE", 0, "Video not found on disk")
            return

        update_status(job_id, "SCENE_INDEX", 20)

        # 1 frame / 3 seconds (as you wanted)
        build_scene_index(
            video_id=job_id,
            video_path=video_path,
            every_n_seconds=3,
            resize_width=320,
            batch_size=64,
        )

        update_status(job_id, "READY_SCENE", 100)

    except Exception as e:
        update_status(job_id, "FAILED_SCENE", 0, str(e))


# -------------------- request models --------------------

class AudioSearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    top_k: int = Field(default=3, ge=1, le=5)
    clip_duration: float = Field(default=10.0, ge=1.0, le=20.0)


class SceneSearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    top_k: int = Field(default=3, ge=1, le=10)
    clip_duration: float = Field(default=10.0, ge=1.0, le=20.0)


# -------------------- AUDIO endpoints --------------------

@app.post("/audio/videos")
async def upload_audio_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = "en",
    model_size: str = "small",
):
    if language not in ("en", "ta"):
        raise HTTPException(status_code=400, detail="Language must be 'en' or 'ta'")

    job_id = str(uuid.uuid4())
    await _save_upload_to_disk(file, job_id)

    create_job(job_id=job_id, mode="audio", language=language, model_size=model_size)
    background_tasks.add_task(process_audio, job_id)

    return {"job_id": job_id, "mode": "audio", "message": "Uploaded. Audio processing started."}


@app.get("/audio/videos/{job_id}/status")
def audio_status(job_id: str):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["mode"] != "audio":
        raise HTTPException(status_code=400, detail="This job_id is not an audio job")

    return {
        "job_id": job_id,
        "mode": "audio",
        "stage": row["stage"],
        "progress": row["progress"],
        "ready": row["stage"] == "READY_AUDIO",
        "error": row["error"],
    }


@app.post("/audio/videos/{job_id}/search")
def audio_search(job_id: str, body: AudioSearchRequest):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["mode"] != "audio":
        raise HTTPException(status_code=400, detail="This job_id is not an audio job")
    if row["stage"] != "READY_AUDIO":
        raise HTTPException(status_code=409, detail=f"Not ready. Stage: {row['stage']}")

    tp = transcript_path(job_id)
    if not tp.exists():
        raise HTTPException(status_code=400, detail="Transcript missing on disk")

    data = load_transcript(job_id)
    segments = data.get("segments", [])

    query = _normalize(body.query)
    q_words = query.split()

    scored = []
    for seg in segments:
        text = _normalize(seg["text"])
        score = sum(1 for w in q_words if w in text)
        if query in text:
            score += 3
        if score > 0:
            scored.append((score, seg))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, seg in scored[: body.top_k]:
        start = float(seg["start"])
        results.append({
            "score": int(score),
            "start": start,
            "timestamp": convert_sec_to_hhmmss(start),
            "text": seg["text"],
            "clip_url": f"/audio/videos/{job_id}/clip?start={start}&dur={body.clip_duration}",
        })

    best = results[0] if results else None
    alternates = results[1:] if len(results) > 1 else []

    return {"job_id": job_id, "mode": "audio", "best": best, "alternates": alternates}


@app.get("/audio/videos/{job_id}/clip")
def audio_clip(job_id: str, start: float, dur: float = 10.0):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["mode"] != "audio":
        raise HTTPException(status_code=400, detail="This job_id is not an audio job")

    video_path = find_video_path(job_id)
    if not video_path:
        raise HTTPException(status_code=404, detail="Video not found on disk")

    out_path = CLIPS_DIR / "audio" / job_id / f"{int(start)}_{int(dur)}.mp4"
    if not out_path.exists():
        cut_clip(video_path, out_path, float(start), float(dur))

    return FileResponse(str(out_path), media_type="video/mp4")


# -------------------- SCENE endpoints --------------------

@app.post("/scene/videos")
async def upload_scene_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    job_id = str(uuid.uuid4())
    await _save_upload_to_disk(file, job_id)

    create_job(job_id=job_id, mode="scene", language=None, model_size=None)
    background_tasks.add_task(process_scene, job_id)

    return {"job_id": job_id, "mode": "scene", "message": "Uploaded. Scene indexing started."}


@app.get("/scene/videos/{job_id}/status")
def scene_status(job_id: str):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["mode"] != "scene":
        raise HTTPException(status_code=400, detail="This job_id is not a scene job")

    return {
        "job_id": job_id,
        "mode": "scene",
        "stage": row["stage"],
        "progress": row["progress"],
        "ready": row["stage"] == "READY_SCENE",
        "error": row["error"],
    }


@app.post("/scene/videos/{job_id}/search")
def scene_search_endpoint(job_id: str, body: SceneSearchRequest):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["mode"] != "scene":
        raise HTTPException(status_code=400, detail="This job_id is not a scene job")
    if row["stage"] != "READY_SCENE":
        raise HTTPException(status_code=409, detail=f"Not ready. Stage: {row['stage']}")

    try:
        hits = search_scene(job_id, body.query, top_k=body.top_k)  # returns [{score, start}, ...]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    results = []
    for h in hits:
        start = float(h["start"])
        results.append({
            "score": float(h["score"]),
            "start": start,
            "timestamp": convert_sec_to_hhmmss(start),
            "clip_url": f"/scene/videos/{job_id}/clip?start={start}&dur={body.clip_duration}",
        })

    best = results[0] if results else None
    alternates = results[1:] if len(results) > 1 else []

    return {"job_id": job_id, "mode": "scene", "best": best, "alternates": alternates}


@app.get("/scene/videos/{job_id}/clip")
def scene_clip(job_id: str, start: float, dur: float = 10.0):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["mode"] != "scene":
        raise HTTPException(status_code=400, detail="This job_id is not a scene job")

    video_path = find_video_path(job_id)
    if not video_path:
        raise HTTPException(status_code=404, detail="Video not found on disk")

    out_path = CLIPS_DIR / "scene" / job_id / f"{int(start)}_{int(dur)}.mp4"
    if not out_path.exists():
        cut_clip(video_path, out_path, float(start), float(dur))

    return FileResponse(str(out_path), media_type="video/mp4")


# -------------------- misc --------------------

@app.get("/health")
def health():
    return {"ok": True}
