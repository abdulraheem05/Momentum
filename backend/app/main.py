import os
import uuid
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions

# Your services
from app.db.state import init_db, create_job, update_status, get_job
from app.services.audio.ffmpeg_utils import extract_audio_wav, cut_clip
from app.services.audio.transcribe_fw import transcribe_audio
from app.services.audio.transcript_store import save_transcript, load_transcript
from app.services.video.scene_index import build_scene_index
from app.services.video.scene_search import search_scene

load_dotenv()

# -------------------- Azure --------------------

AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")

blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)

# -------------------- App --------------------

app = FastAPI(title="Video Finder (Azure Only)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"],
)

init_db()

# -------------------- Helpers --------------------

def convert_sec_to_hhmmss(seconds: float) -> str:
    s = int(max(0.0, float(seconds)))
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"


def get_azure_sas_url(blob_name: str):
    sas_token = generate_blob_sas(
        account_name=blob_service_client.account_name,
        container_name=CONTAINER_NAME,
        blob_name=blob_name,
        account_key=blob_service_client.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(hours=1)
    )
    return f"https://{blob_service_client.account_name}.blob.core.windows.net/{CONTAINER_NAME}/{blob_name}?{sas_token}"


async def upload_to_azure(file: UploadFile, blob_name: str):
    blob_client = blob_service_client.get_blob_client(
        container=CONTAINER_NAME,
        blob=blob_name
    )
    blob_client.upload_blob(file.file, overwrite=True)
    await file.seek(0)


def download_blob_to_temp(blob_name: str, suffix=".mp4") -> str:
    blob_client = blob_service_client.get_blob_client(
        container=CONTAINER_NAME,
        blob=blob_name
    )

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    with open(tmp.name, "wb") as f:
        stream = blob_client.download_blob()
        f.write(stream.readall())

    return tmp.name


# -------------------- Background Tasks --------------------

def process_audio(job_id: str):
    try:
        row = get_job(job_id)
        if not row or row["mode"] != "audio":
            return

        blob_name = row["blob_name"]
        ext = row["ext"]

        update_status(job_id, "DOWNLOADING", 10)
        video_path = download_blob_to_temp(blob_name, suffix=ext)

        update_status(job_id, "EXTRACT_AUDIO", 30)
        audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
        extract_audio_wav(video_path, audio_path)

        update_status(job_id, "TRANSCRIBE", 70)
        transcript = transcribe_audio(audio_path, row["language"], row["model_size"])

        update_status(job_id, "SAVE_TRANSCRIPT", 90)
        save_transcript(job_id, transcript)

        os.remove(video_path)
        os.remove(audio_path)

        update_status(job_id, "READY_AUDIO", 100)

    except Exception as e:
        update_status(job_id, "FAILED_AUDIO", 0, str(e))


def process_scene(job_id: str):
    try:
        row = get_job(job_id)
        if not row or row["mode"] != "scene":
            return

        blob_name = row["blob_name"]
        ext = row["ext"]

        update_status(job_id, "DOWNLOADING", 10)
        video_path = download_blob_to_temp(blob_name, suffix=ext)

        update_status(job_id, "SCENE_INDEX", 50)
        build_scene_index(
            video_id=job_id,
            video_path=video_path,
            every_n_seconds=3,
            resize_width=320,
            batch_size=64,
        )

        os.remove(video_path)

        update_status(job_id, "READY_SCENE", 100)

    except Exception as e:
        update_status(job_id, "FAILED_SCENE", 0, str(e))


# -------------------- Request Models --------------------

class AudioSearchRequest(BaseModel):
    query: str
    top_k: int = 3
    clip_duration: float = 10.0


class SceneSearchRequest(BaseModel):
    query: str
    top_k: int = 3
    clip_duration: float = 10.0


# -------------------- AUDIO --------------------

@app.post("/audio/videos")
async def upload_audio_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower() or ".mp4"

    blob_name = f"uploads/{job_id}{ext}"
    await upload_to_azure(file, blob_name)

    create_job(job_id=job_id, mode="audio", language="en", model_size="small",
               ext=ext, blob_name=blob_name)

    background_tasks.add_task(process_audio, job_id)

    return {"job_id": job_id}


@app.post("/audio/videos/{job_id}/search")
def audio_search(job_id: str, body: AudioSearchRequest):
    row = get_job(job_id)
    if not row or row["stage"] != "READY_AUDIO":
        raise HTTPException(status_code=400, detail="Not ready")

    data = load_transcript(job_id)
    segments = data.get("segments", [])

    results = []
    for seg in segments:
        if body.query.lower() in seg["text"].lower():
            start = float(seg["start"])
            clip_blob = f"clips/{job_id}/{int(start)}.mp4"
            results.append({
                "start": start,
                "timestamp": convert_sec_to_hhmmss(start),
                "clip_url": get_azure_sas_url(clip_blob)
            })

    return {"results": results[:body.top_k]}


@app.get("/audio/videos/{job_id}/clip")
def audio_clip(job_id: str, start: float, dur: float = 10.0):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404)

    video_path = download_blob_to_temp(row["blob_name"], suffix=row["ext"])

    tmp_clip = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
    cut_clip(video_path, tmp_clip, start, dur)

    clip_blob = f"clips/{job_id}/{int(start)}_{int(dur)}.mp4"
    blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=clip_blob)

    with open(tmp_clip, "rb") as f:
        blob_client.upload_blob(f, overwrite=True)

    os.remove(video_path)
    os.remove(tmp_clip)

    return {"clip_url": get_azure_sas_url(clip_blob)}


# -------------------- SCENE --------------------

@app.post("/scene/videos")
async def upload_scene_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower() or ".mp4"

    blob_name = f"uploads/{job_id}{ext}"
    await upload_to_azure(file, blob_name)

    create_job(job_id=job_id, mode="scene", ext=ext, blob_name=blob_name)

    background_tasks.add_task(process_scene, job_id)

    return {"job_id": job_id}


@app.post("/scene/videos/{job_id}/search")
def scene_search_endpoint(job_id: str, body: SceneSearchRequest):
    hits = search_scene(job_id, body.query, top_k=body.top_k)

    results = []
    for h in hits:
        start = float(h["start"])
        results.append({
            "start": start,
            "timestamp": convert_sec_to_hhmmss(start),
            "clip_url": f"/scene/videos/{job_id}/clip?start={start}&dur={body.clip_duration}"
        })

    return {"results": results}


@app.get("/scene/videos/{job_id}/clip")
def scene_clip(job_id: str, start: float, dur: float = 10.0):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404)

    video_path = download_blob_to_temp(row["blob_name"], suffix=row["ext"])

    tmp_clip = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
    cut_clip(video_path, tmp_clip, start, dur)

    clip_blob = f"clips/{job_id}/{int(start)}_{int(dur)}.mp4"
    blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=clip_blob)

    with open(tmp_clip, "rb") as f:
        blob_client.upload_blob(f, overwrite=True)

    os.remove(video_path)
    os.remove(tmp_clip)

    return {"clip_url": get_azure_sas_url(clip_blob)}


# -------------------- Health --------------------

@app.get("/health")
def health():
    return {"ok": True}