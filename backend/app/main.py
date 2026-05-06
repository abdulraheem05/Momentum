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
from app.services.audio.ffmpeg_utils import extract_audio_wav, optimize_video_faststart
from app.services.audio.transcribe_fw import transcribe_audio
from app.services.audio.transcript_store import save_transcript, load_transcript
from app.services.video.scene_index import process_video
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


def upload_file_to_azure(file_path: str, blob_name: str):
    """Uploads a local file from the disk directly to Azure."""
    blob_client = blob_service_client.get_blob_client(
        container=CONTAINER_NAME,
        blob=blob_name
    )
    with open(file_path, "rb") as data:
        blob_client.upload_blob(
            data,
            overwrite=True,
            max_concurrency=4,
            length=os.path.getsize(file_path),
            connection_timeout=600,  # Wait up to 10 minutes to connect
            read_timeout=600
        )


# -------------------- Background Tasks --------------------

def process_audio(job_id: str, local_video_path: str):
    # Initialize these as None so finally block doesn't crash if it fails early
    audio_path = None 
    
    try:
        row = get_job(job_id)
        if not row or row["mode"] != "audio":
            return

        # STAGE 1: Extract Audio
        update_status(job_id, "EXTRACT_AUDIO", 30)
        audio_path = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name

        # 🔥 SPEED FIX: Extracting from the local /tmp file is nearly instant
        extract_audio_wav(local_video_path, audio_path)

        # STAGE 2: Transcribe
        update_status(job_id, "TRANSCRIBE", 70)
        transcript = transcribe_audio(audio_path, row["language"], row["model_size"])

        # STAGE 3: Save results
        update_status(job_id, "SAVE_TRANSCRIPT", 90)
        save_transcript(job_id, transcript)

        update_status(job_id, "READY_AUDIO", 100)

    except Exception as e:
        print(f"Error in process_audio: {e}")
        update_status(job_id, "FAILED_AUDIO", 0, str(e))
        
    finally:
        # 🔥 STORAGE FIX: Clean up Hugging Face /tmp directory
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
        if local_video_path and os.path.exists(local_video_path):
            os.remove(local_video_path)


def process_scene(job_id: str, local_video_path: str, blob_name: str):
    final_path = local_video_path
    try:
        # STAGE 1: Optimize and Upload (Backgrounded)
        update_status(job_id, "OPTIMIZING", 10)
        opt_path = local_video_path + ".opt.mp4"
        try:
            optimize_video_faststart(local_video_path, opt_path)
            final_path = opt_path
        except:
            pass
            
        update_status(job_id, "UPLOADING", 30)
        upload_file_to_azure(final_path, blob_name)

        # STAGE 2: Indexing
        update_status(job_id, "SCENE_INDEX", 60)
        process_video(video_path=final_path, video_id=job_id)

        update_status(job_id, "READY_SCENE", 100)
    except Exception as e:
        update_status(job_id, "FAILED_SCENE", 0, str(e))
    finally:
        # Cleanup
        for p in [local_video_path, opt_path]:
            if os.path.exists(p): os.remove(p)


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

    # 1. Save the raw upload to the Hugging Face /tmp directory
    raw_fd, raw_path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(raw_fd, "wb") as buffer:
        buffer.write(await file.read())

    # 2. Optimize the video for instant web playback
    opt_fd, opt_path = tempfile.mkstemp(suffix=".mp4")
    os.close(opt_fd) 
    
    try:
        optimize_video_faststart(raw_path, opt_path)
        os.remove(raw_path) # Delete raw immediately to save disk space
        final_local_path = opt_path
    except Exception as e:
        print(f"Optimization failed, using original: {e}")
        os.remove(opt_path)
        final_local_path = raw_path

    # 3. Call your clean helper function!
    upload_file_to_azure(final_local_path, blob_name)

    # 4. Create the DB record
    create_job(job_id=job_id, mode="audio", language="en", model_size="small",
               ext=ext, blob_name=blob_name)

    # 5. Pass the local path to the background task
    background_tasks.add_task(process_audio, job_id, final_local_path)

    return {"job_id": job_id}


@app.post("/audio/videos/{job_id}/search")
def audio_search(job_id: str, body: AudioSearchRequest):
    row = get_job(job_id)
    if not row or row["stage"] != "READY_AUDIO":
        raise HTTPException(status_code=400, detail="Not ready")

    blob_name = row["blob_name"]
    base_url = get_azure_sas_url(blob_name)

    data = load_transcript(job_id)
    segments = data.get("segments", [])

    results = []

    for seg in segments:
        if body.query.lower() in seg["text"].lower():
            start = float(seg["start"])
            results.append({
                "start": start,
                "timestamp": convert_sec_to_hhmmss(start),
                "text": seg["text"],
                "clip_url": f"{base_url}#t={start},{start+body.clip_duration}"
            })

    best = results[0] if results else None
    alternates = results[1:] if len(results) > 1 else []

    return {
        "best": best,
        "alternates": alternates
    }

@app.get("/audio/videos/{job_id}/status")
def audio_status(job_id: str):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "stage": row.get("stage"),
        "progress": row.get("progress", 0),
        "ready": row.get("stage") == "READY_AUDIO",
        "error": row.get("error")
    }


# -------------------- SCENE --------------------

import tempfile
import os

@app.post("/scene/videos")
async def upload_scene_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    ext = Path(file.filename).suffix.lower() or ".mp4"
    blob_name = f"uploads/{job_id}{ext}"

    # 1. ONLY save the file locally
    raw_fd, raw_path = tempfile.mkstemp(suffix=ext)
    with os.fdopen(raw_fd, "wb") as buffer:
        buffer.write(await file.read())

    # 2. Create DB record immediately
    create_job(job_id=job_id, mode="scene", ext=ext, blob_name=blob_name)

    # 3. Hand everything off to the background task
    background_tasks.add_task(process_scene, job_id, raw_path, blob_name)

    return {"job_id": job_id}

@app.post("/scene/videos/{job_id}/search")
def scene_search_endpoint(job_id: str, body: SceneSearchRequest):
    row = get_job(job_id)

    blob_name = row["blob_name"]
    base_url = get_azure_sas_url(blob_name)

    hits = search_scene(job_id, body.query, top_k=body.top_k)

    results = []
    for h in hits:
        start = float(h["start"])

        results.append({
            "start": start,
            "timestamp": convert_sec_to_hhmmss(start),
            "score": h["score"], 
            "clip_url": f"{base_url}#t={start},{start+body.clip_duration}"
        })

    return {"results": results}

@app.get("/scene/videos/{job_id}/status")
def scene_status(job_id: str):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "stage": row.get("stage"),
        "progress": row.get("progress", 0),
        "ready": row.get("stage") == "READY_SCENE",
        "error": row.get("error")
    }


# -------------------- Health --------------------

@app.get("/health")
def health():
    return {"ok": True}