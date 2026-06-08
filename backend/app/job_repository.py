from typing import Any, Dict, Optional
import uuid
from datetime import datetime, timezone
from app.supabase_client import supabase


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_upload_job(
    original_file_name: str,
    media_blob_name: str,
    media_blob_url: str,
    media_content_type: str,
    media_file_size: int,
    mode: str,
) -> Dict[str, Any]:
    job_id = str(uuid.uuid4())

    parent_data = {
        "id": job_id,
        "source_type": "upload",
        "youtube_url": None,
        "youtube_id": None,
        "mode": mode,
        "status": "queued",
        "progress": 15,
        "message": "File uploaded. Preparing processing.",
        "error": "",
        "original_file_name": original_file_name,
        "media_blob_name": media_blob_name,
        "media_blob_url": media_blob_url,
        "media_content_type": media_content_type,
        "media_file_size": media_file_size,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }

    parent_response = (
        supabase
        .table("youtube_jobs")
        .insert(parent_data)
        .execute()
    )

    if mode == "audio":
        (
            supabase
            .table("youtube_audio_jobs")
            .insert({
                "job_id": job_id,
                "audio_status": "queued",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            })
            .execute()
        )

    elif mode == "video":
        (
            supabase
            .table("youtube_video_jobs")
            .insert({
                "job_id": job_id,
                "visual_status": "queued",
                "visual_indexed_count": 0,
                "pinecone_namespace": job_id,
                "created_at": now_iso(),
                "updated_at": now_iso(),
            })
            .execute()
        )

    else:
        raise ValueError("mode must be either 'audio' or 'video'")

    return parent_response.data[0]


#------------------------------------------#

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