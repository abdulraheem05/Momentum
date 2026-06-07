import json
import uuid
from typing import Any, Dict, BinaryIO

from azure.storage.blob import BlobServiceClient, ContentSettings

from app.config import settings



def get_blob_service_client():
    return BlobServiceClient.from_connection_string(
        settings.AZURE_STORAGE_CONNECTION_STRING
    )


def sanitize_filename(filename: str) -> str:
    safe = filename.replace("\\", "_").replace("/", "_").strip()
    return safe or f"upload-{uuid.uuid4()}.mp4"


def upload_media_file_to_azure(
    file_obj: BinaryIO,
    filename: str,
    content_type: str | None,
    job_id: str,
) -> dict:
    blob_service = get_blob_service_client()
    container_name = settings.AZURE_UPLOADS_CONTAINER

    safe_filename = sanitize_filename(filename)
    blob_name = f"uploads/{job_id}/{safe_filename}"

    blob_client = blob_service.get_blob_client(
        container=container_name,
        blob=blob_name,
    )

    file_bytes = file_obj.read()

    blob_client.upload_blob(
        file_bytes,
        overwrite=True,
        content_settings=ContentSettings(
            content_type=content_type or "application/octet-stream"
        ),
    )

    return {
        "blob_name": blob_name,
        "blob_url": blob_client.url,
        "content_type": content_type or "application/octet-stream",
        "file_size": len(file_bytes),
    }


def download_media_blob_to_file(
    blob_name: str,
    output_path: str,
    container_name: str | None = None,
) -> str:
    blob_service = get_blob_service_client()

    blob_client = blob_service.get_blob_client(
        container=container_name or settings.AZURE_UPLOADS_CONTAINER,
        blob=blob_name,
    )

    with open(output_path, "wb") as file:
        stream = blob_client.download_blob()
        file.write(stream.readall())

    return output_path


def load_transcript_json(blob_name: str) -> Dict[str, Any]:
    """
    Downloads transcript JSON from Azure Blob and returns it as a Python dict.
    """

    blob_service_client = BlobServiceClient.from_connection_string(
        settings.AZURE_STORAGE_CONNECTION_STRING
    )

    container_client = blob_service_client.get_container_client(
        settings.AZURE_TRANSCRIPTS_CONTAINER
    )

    blob_client = container_client.get_blob_client(blob_name)

    data = blob_client.download_blob().readall()

    return json.loads(data.decode("utf-8"))