import os
import platform
from pathlib import Path
import torch
import uuid

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

from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

# Initialize Azure Client
AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")
blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)


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


async def _upload_to_azure(file: UploadFile, job_id: str) -> str:
    ext = Path(file.filename).suffix.lower() or ".mp4"
    blob_name = f"uploads/{job_id}{ext}"
    
    blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=blob_name)
    
    try:
        # Stream the upload directly to Azure
        blob_client.upload_blob(file.file, overwrite=True)
        return blob_name
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Azure Upload failed: {e}")    


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

    ext = Path(file.filename).suffix.lower() or ".mp4"
    blob_name = f"uploads/{job_id}{ext}"

    await _upload_to_azure(file, job_id)

    create_job(
        job_id=job_id,
        mode="audio",
        language=language,
        model_size=model_size,
        ext=ext,
        blob_name=blob_name
    )
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


def get_azure_sas_url(blob_name: str):
    sas_token = generate_blob_sas(
        account_name=blob_service_client.account_name,
        container_name=CONTAINER_NAME,
        blob_name=blob_name,
        account_key=blob_service_client.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(hours=1) # Valid for 1 hour
    )
    return f"https://{blob_service_client.account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}?{sas_token}"


@app.get("/audio/videos/{job_id}/clip")
def audio_clip(job_id: str, start: float, dur: float = 10.0):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row["mode"] != "audio":
        raise HTTPException(status_code=400, detail="This job_id is not an audio job")

    blob_name = f"uploads/{job_id}.mp4"
    url = get_azure_sas_url(blob_name)

    if not url:
        raise HTTPException(status_code=404, detail="Video not found")

    streaming_url = f"{url}#t={start},{start+dur}"

    return {"clip_url": streaming_url}


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
