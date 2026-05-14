import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.services.search.scene_search import search_scenes
from app.services.search.audio_search import search_audio

from app.services.generate_clips import (
    generate_clip,
    upload_result_clip
)

from app.services.history import (
    save_history,
    get_history
)

from app.models.schemas import (
    UploadCompleteRequest,
    SceneSearchRequest,
    AudioSearchRequest
)


from app.services.cleanup import (
    delete_original_video
)

from app.services.azure_sas import generate_upload_sas
from app.services.modal_trigger import trigger_worker

from app.db.supabase import supabase

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def home():
    return {"message": "Momentum Backend Running"}


@app.get("/upload/sas-token")
async def get_sas_token():

    return generate_upload_sas()


@app.post("/jobs/create")
async def create_job(
    request: UploadCompleteRequest
):

    job_id = str(uuid.uuid4())

    source_url = request.blob_url or request.youtube_url

    (
        supabase
        .table("jobs")
        .insert({
            "id": job_id,
            "source_type": request.source_type,
            "source_url": source_url,
            "mode": request.mode,
            "status": "PROCESSING"
        })
        .execute()
    )

    payload = {
        "source_type": request.source_type,
        "source_url": source_url,
        "mode": request.mode,
    }

    trigger_worker(job_id, payload)

    return {
        "job_id": job_id,
        "status": "PROCESSING"
    }


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):

    response = (
        supabase
        .table("jobs")
        .select("*")
        .eq("id", job_id)
        .execute()
    )

    return response.data[0]

@app.post("/search/scene")
async def scene_search(request: SceneSearchRequest):

    results = search_scenes(
        request.job_id,
        request.query
    )

    response = []

    job_response = (
        supabase
        .table("jobs")
        .select("*")
        .eq("id", request.job_id)
        .execute()
    )

    if not job_response.data:
        raise HTTPException(status_code=404, detail="Job id not found")
    
    job = job_response.data[0]

    source_video = job["source_url"]

    for item in results:

        clip_path = generate_clip(
            source_video,
            item["timestamp"]
        )

        clip_url = upload_result_clip(
            clip_path
        )

        save_history(
            request.job_id,
            request.query,
            "scene",
            clip_url,
            item["thumbnail_url"],
            item["timestamp"]
        )

        response.append({
            "clip_url": clip_url,
            "thumbnail_url": item["thumbnail_url"],
            "timestamp": item["timestamp"],
            "score": item["score"]
        })

    return response


@app.post("/search/audio")
async def audio_search(request: AudioSearchRequest):

    results = search_audio(
        request.job_id,
        request.query
    )

    response = []

    job_response = (
        supabase
        .table("jobs")
        .select("*")
        .eq("id", request.job_id)
        .execute()
    )

    if not job_response.data:
        raise HTTPException(status_code=404, detail="Job id not found")
    
    job = job_response.data[0]

    source_video = job["source_url"]

    for item in results:

        clip_path = generate_clip(
            source_video,
            item["timestamp"]
        )

        clip_url = upload_result_clip(
            clip_path
        )

        thumbnail_url = ""

        save_history(
            request.job_id,
            request.query,
            "audio",
            clip_url,
            thumbnail_url,
            item["timestamp"]
        )

        response.append({
            "clip_url": clip_url,
            "timestamp": item["timestamp"],
            "score": item["score"]
        })

    return response

@app.get("/history")
async def history():

    return get_history()


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):

    job_response = (
        supabase
        .table("jobs")
        .select("*")
        .eq("id", job_id)
        .execute()
    ).data[0]

    if not job_response:
        raise HTTPException(status_code=404, detail="Job id not found")
    
    job = job_response.data[0]

    if job["source_type"] == "upload":
        delete_original_video(job["source_url"])

    (
        supabase
        .table("jobs")
        .delete()
        .eq("id", job_id)
        .execute()
    )

    return {
        "message": "Original movie deleted"
    }