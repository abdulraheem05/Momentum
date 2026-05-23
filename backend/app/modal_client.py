import requests
from app.config import settings


def trigger_modal_processing(job_id: str, youtube_url: str, youtube_id: str) -> None:
    """
    Calls the Modal worker web endpoint.

    For now, if MODAL_PROCESS_URL is not set, we do not crash the backend.
    This lets us test job creation before Modal is ready.
    """

    if not settings.MODAL_PROCESS_URL:
        print("MODAL_PROCESS_URL is not set. Skipping Modal trigger for now.")
        return

    payload = {
        "job_id": job_id,
        "youtube_url": youtube_url,
        "youtube_id": youtube_id,
    }

    response = requests.post(
        settings.MODAL_PROCESS_URL,
        json=payload,
        timeout=15,
    )

    response.raise_for_status()