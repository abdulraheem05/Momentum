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

from app.azure_utils import load_transcript_json
from app.search.dialogue_search import search_dialogue_in_transcript

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

class SearchDialogueRequest(BaseModel):
    job_id: str
    query: str


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

@app.post("/youtube/search-dialogue")
def search_dialogue(payload: SearchDialogueRequest):
    """
    Searches remembered dialogue inside the transcript JSON stored in Azure.
    """

    try:
        job = get_youtube_job_by_id(payload.job_id)

        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")

        if job["status"] != "ready":
            raise HTTPException(
                status_code=400,
                detail=f"Job is not ready yet. Current status: {job['status']}",
            )

        blob_name = job.get("transcript_blob_name")

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