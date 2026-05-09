import uuid

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.models.schemas import (
    UploadCompleteRequest,
    SceneSearchRequest,
    AudioSearchRequest
)

from app.services.azure_sas import generate_upload_sas
from app.services.auth import get_current_user
from app.services.modal_trigger import trigger_worker
from app.services.quota import (
    check_quota,
    increment_usage
)

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
async def get_sas_token(
    current_user=Depends(get_current_user)
):
    await check_quota(current_user["sub"])

    return generate_upload_sas()


@app.post("/jobs/create")
async def create_job(
    request: UploadCompleteRequest,
    current_user=Depends(get_current_user)
):

    await check_quota(current_user["sub"])

    job_id = str(uuid.uuid4())

    source_url = request.blob_url or request.youtube_url

    (
        supabase
        .table("jobs")
        .insert({
            "id": job_id,
            "user_id": current_user["sub"],
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
        "user_id": current_user["sub"]
    }

    trigger_worker(job_id, payload)

    await increment_usage(current_user["sub"])

    return {
        "job_id": job_id,
        "status": "PROCESSING"
    }


@app.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    current_user=Depends(get_current_user)
):

    response = (
        supabase
        .table("jobs")
        .select("*")
        .eq("id", job_id)
        .execute()
    )

    return response.data[0]