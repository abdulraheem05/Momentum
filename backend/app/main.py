from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.supabase_client import supabase
from app.youtube_utils import extract_youtube_id
from app.modal_client import trigger_modal_processing


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
    Creates a Supabase job and triggers the Modal worker.
    """

    try:
        youtube_id = extract_youtube_id(payload.youtube_url)

        insert_response = (
            supabase
            .table("youtube_jobs")
            .insert({
                "youtube_url": payload.youtube_url,
                "youtube_id": youtube_id,
                "status": "queued",
                "progress": 0,
                "message": "Job created. Waiting for worker.",
            })
            .execute()
        )

        if not insert_response.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to create job in Supabase."
            )

        job = insert_response.data[0]
        job_id = job["id"]

        try:
            trigger_modal_processing(
                job_id=job_id,
                youtube_url=payload.youtube_url,
                youtube_id=youtube_id,
            )
        except Exception as modal_error:
            (
                supabase
                .table("youtube_jobs")
                .update({
                    "status": "failed",
                    "progress": 0,
                    "message": "Failed to trigger worker.",
                    "error": str(modal_error),
                })
                .eq("id", job_id)
                .execute()
            )

            raise HTTPException(
                status_code=500,
                detail=f"Job created but failed to trigger worker: {modal_error}",
            )

        return {
            "job_id": job_id,
            "youtube_id": youtube_id,
            "status": "queued",
            "progress": 0,
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

    response = (
        supabase
        .table("youtube_jobs")
        .select("*")
        .eq("id", job_id)
        .single()
        .execute()
    )

    if not response.data:
        raise HTTPException(status_code=404, detail="Job not found.")

    return response.data