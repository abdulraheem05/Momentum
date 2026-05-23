from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.youtube_utils import extract_youtube_id
from app.modal_client import trigger_modal_processing
from app.job_repository import (
    create_youtube_job as create_job_record,
    get_youtube_job_by_id,
    mark_job_worker_trigger_failed,
)


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


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "message": "Momentum YouTube V1 backend is running",
    }


@app.post("/youtube/jobs")
def create_youtube_job(payload: CreateYouTubeJobRequest):
    """
    Creates a job record and triggers the Modal worker.
    """

    try:
        youtube_id = extract_youtube_id(payload.youtube_url)

        job = create_job_record(
            youtube_url=payload.youtube_url,
            youtube_id=youtube_id,
        )

        job_id = job["id"]

        try:
            trigger_modal_processing(
                job_id=job_id,
                youtube_url=payload.youtube_url,
                youtube_id=youtube_id,
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

        return {
            "job_id": job_id,
            "youtube_id": youtube_id,
            "status": job["status"],
            "progress": job["progress"],
            "message": "Job created and worker triggered.",
        }

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@app.get("/youtube/jobs/{job_id}")
def get_youtube_job(job_id: str):
    """
    Frontend uses this endpoint to poll progress.
    """

    job = get_youtube_job_by_id(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    return job