from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
from fastapi import UploadFile, File, Form
from fastapi import BackgroundTasks

from app.youtube_utils import extract_youtube_id
from app.modal_client import trigger_modal_processing, trigger_modal_upload_processing
from app.job_repository import (
    create_youtube_job as create_job_record,
    get_youtube_job_by_id,
    get_youtube_job_with_details,
    mark_job_worker_trigger_failed, 
    create_upload_job
)

from app.azure_utils import load_transcript_json, upload_media_file_to_azure, delete_media_blob_from_azure, create_upload_sas_url
from app.search.dialogue_search import search_dialogue_in_transcript
from app.search.visual_search import warmup_clip_model, search_visual_scenes_backend

app = FastAPI(title="Momentum YouTube V1 Backend")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later replace with your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateYouTubeJobRequest(BaseModel):
    youtube_url: str
    mode: str = "audio"


class SearchVisualRequest(BaseModel):
    job_id: str
    query: str

class SearchDialogueRequest(BaseModel):
    job_id: str
    query: str

class CompleteUploadRequest(BaseModel):
    filename: str
    mode: str
    blob_name: str
    blob_url: str
    content_type: str | None = None
    file_size: int | None = None
    
class CreateUploadUrlRequest(BaseModel):
    filename: str
    content_type: str | None = None
    mode: str = "video"
    file_size: int | None = None

@app.get("/")
def health_check():
    return {
        "status": "ok",
        "message": "Momentum YouTube V1 backend is running",
    }

@app.post("/upload/jobs")
async def create_local_upload_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    mode: str = Form("video"),
):
    try:
        mode = mode.lower().strip()

        if mode not in {"video", "audio"}:
            raise HTTPException(
                status_code=400,
                detail="mode must be either 'video' or 'audio'.",
            )

        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="No file selected.",
            )

        job_id_for_blob = str(uuid.uuid4())

        upload_info = upload_media_file_to_azure(
            file_obj=file.file,
            filename=file.filename,
            content_type=file.content_type,
            job_id=job_id_for_blob,
        )

        job = create_upload_job(
            original_file_name=file.filename,
            media_blob_name=upload_info["blob_name"],
            media_blob_url=upload_info["blob_url"],
            media_content_type=upload_info["content_type"],
            media_file_size=upload_info["file_size"],
            mode=mode,
        )

        try:
            trigger_modal_upload_processing(
                job_id=job["id"],
                media_blob_name=upload_info["blob_name"],
                media_blob_url=upload_info["blob_url"],
                original_file_name=file.filename,
                mode=mode,
            )
        except Exception as modal_error:
            mark_job_worker_trigger_failed(
                job_id=job["id"],
                error_message=str(modal_error),
            )

            raise HTTPException(
                status_code=500,
                detail=f"Upload job created but failed to trigger worker: {modal_error}",
            )

        if mode == "video":
            background_tasks.add_task(warmup_clip_model)

        return {
            "job_id": job["id"],
            "source_type": "upload",
            "mode": mode,
            "status": "queued",
            "progress": 5,
            "message": "File uploaded. Processing started.",
            "file_name": file.filename,
            "media_blob_url": upload_info["blob_url"],
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) 
    

@app.get("/upload/jobs/{job_id}")
def get_upload_job(job_id: str):
    job = get_youtube_job_with_details(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    return job

@app.post("/upload/presign")
def create_upload_presigned_url(payload: CreateUploadUrlRequest):
    try:
        mode = payload.mode.lower().strip()

        if mode not in {"video", "audio"}:
            raise HTTPException(
                status_code=400,
                detail="mode must be either 'video' or 'audio'.",
            )

        job_id_for_blob = str(uuid.uuid4())

        upload_info = create_upload_sas_url(
            filename=payload.filename,
            content_type=payload.content_type,
            job_id=job_id_for_blob,
        )

        return {
            "source_type": "upload",
            "mode": mode,
            "filename": payload.filename,
            "file_size": payload.file_size,
            **upload_info,
        }

    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
    

@app.post("/upload/complete")
def complete_direct_upload(
    payload: CompleteUploadRequest,
    background_tasks: BackgroundTasks,
):
    try:
        mode = payload.mode.lower().strip()

        if mode not in {"video", "audio"}:
            raise HTTPException(
                status_code=400,
                detail="mode must be either 'video' or 'audio'.",
            )

        job = create_upload_job(
            original_file_name=payload.filename,
            media_blob_name=payload.blob_name,
            media_blob_url=payload.blob_url,
            media_content_type=payload.content_type or "application/octet-stream",
            media_file_size=payload.file_size or 0,
            mode=mode,
        )

        trigger_modal_upload_processing(
            job_id=job["id"],
            media_blob_name=payload.blob_name,
            media_blob_url=payload.blob_url,
            original_file_name=payload.filename,
            mode=mode,
        )

        if mode == "video":
            background_tasks.add_task(warmup_clip_model)

        return {
            "job_id": job["id"],
            "source_type": "upload",
            "mode": mode,
            "status": "queued",
            "progress": 15,
            "message": "File uploaded. Processing started.",
            "file_name": payload.filename,
            "media_blob_url": payload.blob_url,
        }

    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

@app.post("/upload/search-visual")
def search_upload_visual(payload: SearchVisualRequest):
    return search_visual(payload)


@app.post("/upload/search-dialogue")
def search_upload_dialogue(payload: SearchDialogueRequest):
    return search_dialogue(payload)

@app.delete("/upload/jobs/{job_id}/file")
def delete_uploaded_file(job_id: str):
    try:
        job = get_youtube_job_with_details(job_id)

        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")

        if job.get("source_type") != "upload":
            return {
                "ok": True,
                "deleted": False,
                "message": "Job is not a local upload job.",
            }

        blob_name = job.get("media_blob_name")

        if not blob_name:
            return {
                "ok": True,
                "deleted": False,
                "message": "No uploaded blob found for this job.",
            }

        deleted = delete_media_blob_from_azure(blob_name)

        return {
            "ok": True,
            "deleted": deleted,
            "blob_name": blob_name,
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

@app.post("/youtube/jobs")
def create_youtube_job(payload: CreateYouTubeJobRequest, background_tasks: BackgroundTasks):
    try:
        mode = payload.mode.lower().strip()

        if mode not in ["audio", "video"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid mode. Use 'audio' or 'video'.",
            )

        youtube_id = extract_youtube_id(payload.youtube_url)

        job = create_job_record(
            youtube_url=payload.youtube_url,
            youtube_id=youtube_id,
            mode=mode,
        )

        job_id = job["id"]

        try:
            trigger_modal_processing(
                job_id=job_id,
                youtube_url=payload.youtube_url,
                youtube_id=youtube_id,
                mode=mode,
            )
        except Exception as modal_error:
            mark_job_worker_trigger_failed(
                job_id=job_id,
                error_message=str(modal_error),
            )

            raise HTTPException(
                status_code=500,
                detail=f"Job created but failed to trigger worker: {modal_error}",
            )
        
        if mode == "video":
            background_tasks.add_task(warmup_clip_model)

        return {
            "job_id": job_id,
            "youtube_id": youtube_id,
            "mode": mode,
            "status": job["status"],
            "progress": job["progress"],
            "message": f"{mode.capitalize()} job created and worker triggered.",
        }

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.get("/youtube/jobs/{job_id}")
def get_youtube_job(job_id: str):
    job = get_youtube_job_with_details(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    return job

@app.post("/youtube/search-dialogue")
def search_dialogue(payload: SearchDialogueRequest):
    """
    Searches remembered dialogue inside the transcript JSON stored in Azure.
    """

    try:
        job = get_youtube_job_with_details(payload.job_id)

        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        
        if job["mode"] != "audio":
            raise HTTPException(
                status_code=400,
                detail="This job is not an audio search job.",
            )

        if job["status"] != "ready":
            raise HTTPException(
                status_code=400,
                detail=f"Job is not ready yet. Current status: {job['status']}",
            )

        audio_details = job.get("audio_details")

        if not audio_details:
            raise HTTPException(
                status_code=500,
                detail="Audio details are missing for this job.",
            )

        blob_name = audio_details.get("transcript_blob_name")

        if not blob_name:
            raise HTTPException(
                status_code=500,
                detail="Transcript blob name is missing for this job.",
            )

        transcript_data = load_transcript_json(blob_name)

        results = search_dialogue_in_transcript(
            transcript_data=transcript_data,
            query=payload.query,
            max_results=3,
        )

        return {
            "job_id": payload.job_id,
            "query": payload.query,
            "count": len(results),
            "results": results,
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
    

@app.post("/youtube/search-visual")
def search_visual(payload: SearchVisualRequest):
    try:
        job = get_youtube_job_with_details(payload.job_id)

        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")

        if job["mode"] != "video":
            raise HTTPException(
                status_code=400,
                detail="This job is not a video search job.",
            )

        if job["status"] != "ready":
            raise HTTPException(
                status_code=400,
                detail=f"Job is not ready yet. Current status: {job['status']}",
            )

        video_details = job.get("video_details")

        if not video_details:
            raise HTTPException(
                status_code=500,
                detail="Video details are missing for this job.",
            )

        if video_details["visual_status"] != "ready":
            raise HTTPException(
                status_code=400,
                detail=f"Video index is not ready yet. Current status: {video_details['visual_status']}",
            )

        pinecone_namespace = (
            video_details.get("pinecone_namespace")
            or payload.job_id
        )

        result = search_visual_scenes_backend(
            job_id=payload.job_id,
            namespace=pinecone_namespace,
            query=payload.query,
            top_k=3,
        )

        return {
            "job_id": payload.job_id,
            **result,
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))