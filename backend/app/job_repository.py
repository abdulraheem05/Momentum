from typing import Any, Dict, Optional

from app.supabase_client import supabase


def create_youtube_job(
    youtube_url: str,
    youtube_id: str,
) -> Dict[str, Any]:
    """
    Creates a new YouTube processing job in Supabase.
    """

    response = (
        supabase
        .table("youtube_jobs")
        .insert({
            "youtube_url": youtube_url,
            "youtube_id": youtube_id,
            "status": "queued",
            "progress": 0,
            "message": "Job created. Submitting to worker.",
        })
        .execute()
    )

    if not response.data:
        raise RuntimeError("Failed to create job in Supabase.")

    return response.data[0]


def get_youtube_job_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Gets one YouTube job by job ID.
    """

    response = (
        supabase
        .table("youtube_jobs")
        .select("*")
        .eq("id", job_id)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


def mark_job_worker_trigger_failed(
    job_id: str,
    error_message: str,
) -> None:
    """
    Updates a job as failed when the backend could not trigger Modal.
    """

    (
        supabase
        .table("youtube_jobs")
        .update({
            "status": "failed",
            "progress": 0,
            "message": "Failed to trigger worker.",
            "error": error_message,
        })
        .eq("id", job_id)
        .execute()
    )