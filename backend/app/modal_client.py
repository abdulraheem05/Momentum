import requests
from app.config import settings


def trigger_modal_processing(
    job_id: str,
    youtube_url: str,
    youtube_id: str,
    mode: str,
) -> None:
    """
    Existing YouTube processing trigger.
    Keep this for YouTube URL jobs.
    """

    if mode == "audio":
        modal_url = settings.MODAL_AUDIO_PROCESS_URL
    elif mode == "video":
        modal_url = settings.MODAL_VIDEO_PROCESS_URL
    else:
        raise ValueError("Invalid mode. Use 'audio' or 'video'.")

    if not modal_url:
        print(f"Modal URL for mode '{mode}' is not set. Skipping trigger.")
        return

    payload = {
        "job_id": job_id,
        "source_type": "youtube",
        "youtube_url": youtube_url,
        "youtube_id": youtube_id,
        "mode": mode,
    }

    response = requests.post(
        modal_url,
        json=payload,
        timeout=15,
    )

    response.raise_for_status()


def trigger_modal_upload_processing(
    job_id: str,
    media_blob_name: str,
    media_blob_url: str,
    original_file_name: str,
    mode: str,
) -> None:
    """
    New local file upload processing trigger.
    This sends Azure blob details to Modal instead of a YouTube URL.
    """

    if mode == "audio":
        modal_url = settings.MODAL_AUDIO_PROCESS_URL
    elif mode == "video":
        modal_url = settings.MODAL_VIDEO_PROCESS_URL
    else:
        raise ValueError("Invalid mode. Use 'audio' or 'video'.")

    if not modal_url:
        print(f"Modal URL for upload mode '{mode}' is not set. Skipping trigger.")
        return

    payload = {
        "job_id": job_id,
        "source_type": "upload",
        "media_blob_name": media_blob_name,
        "media_blob_url": media_blob_url,
        "original_file_name": original_file_name,
        "mode": mode,
    }

    response = requests.post(
        modal_url,
        json=payload,
        timeout=15,
    )

    response.raise_for_status()


def call_modal_visual_search(
    job_id: str,
    youtube_id: str,
    query: str,
    top_k: int = 3,
) -> dict:
    """
    Keep this only if you later want Modal-based visual search.

    For your current plan, visual search happens in FastAPI backend,
    so this function is not needed in the main flow.
    """

    if not settings.MODAL_VIDEO_SEARCH_URL:
        raise RuntimeError("MODAL_VIDEO_SEARCH_URL is not set.")

    payload = {
        "job_id": job_id,
        "youtube_id": youtube_id,
        "query": query,
        "top_k": top_k,
    }

    response = requests.post(
        settings.MODAL_VIDEO_SEARCH_URL,
        json=payload,
        timeout=60,
    )

    response.raise_for_status()
    return response.json()