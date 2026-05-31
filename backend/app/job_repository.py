from typing import Any, Dict, Optional

from app.supabase_client import supabase


def create_youtube_job(
    youtube_url: str,
    youtube_id: str,
    mode: str,
) -> Dict[str, Any]:
    parent_response = (
        supabase
        .table("youtube_jobs")
        .insert({
            "youtube_url": youtube_url,
            "youtube_id": youtube_id,
            "mode": mode,
            "status": "queued",
            "progress": 0,
            "message": f"{mode.capitalize()} job created. Submitting to worker.",
            "error": "",
        })
        .execute()
    )

    if not parent_response.data:
        raise RuntimeError("Failed to create job in youtube_jobs.")

    job = parent_response.data[0]
    job_id = job["id"]

    if mode == "audio":
        child_response = (
            supabase
            .table("youtube_audio_jobs")
            .insert({
                "job_id": job_id,
                "audio_status": "queued",
            })
            .execute()
        )

        if not child_response.data:
            raise RuntimeError("Failed to create audio job row.")

    elif mode == "video":
        child_response = (
            supabase
            .table("youtube_video_jobs")
            .insert({
                "job_id": job_id,
                "visual_status": "queued",
                "visual_indexed_count": 0,
                "pinecone_namespace": job_id,
            })
            .execute()
        )

        if not child_response.data:
            raise RuntimeError("Failed to create video job row.")

    else:
        raise ValueError("Invalid mode. Use 'audio' or 'video'.")

    return job


def get_youtube_job_by_id(job_id: str) -> Optional[Dict[str, Any]]:
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


def get_youtube_job_with_details(job_id: str) -> Optional[Dict[str, Any]]:
    job = get_youtube_job_by_id(job_id)

    if not job:
        return None

    if job["mode"] == "audio":
        audio_response = (
            supabase
            .table("youtube_audio_jobs")
            .select("*")
            .eq("job_id", job_id)
            .execute()
        )

        job["audio_details"] = audio_response.data[0] if audio_response.data else None

    if job["mode"] == "video":
        video_response = (
            supabase
            .table("youtube_video_jobs")
            .select("*")
            .eq("job_id", job_id)
            .execute()
        )

        job["video_details"] = video_response.data[0] if video_response.data else None

    return job


def mark_job_worker_trigger_failed(
    job_id: str,
    error_message: str,
) -> None:
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