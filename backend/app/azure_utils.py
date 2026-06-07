import json
import uuid
from typing import Any, Dict, BinaryIO

from azure.storage.blob import BlobServiceClient, ContentSettings

from app.config import settings

from datetime import datetime, timedelta, timezone
from azure.storage.blob import (
    BlobServiceClient,
    BlobSasPermissions,
    ContentSettings,
    generate_blob_sas,
)
from app.config import settings


def create_upload_sas_url(
    filename: str,
    content_type: str | None,
    job_id: str,
) -> dict:
    blob_service = get_blob_service_client()
    container_name = settings.AZURE_UPLOADS_CONTAINER

    safe_filename = sanitize_filename(filename)
    blob_name = f"uploads/{job_id}/{safe_filename}"

    account_name = blob_service.account_name

    # Extract account key from connection string
    account_key = None
    for part in settings.AZURE_STORAGE_CONNECTION_STRING.split(";"):
        if part.startswith("AccountKey="):
            account_key = part.replace("AccountKey=", "", 1)
            break

    if not account_key:
        raise RuntimeError("Could not find AccountKey in Azure connection string.")

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(write=True, create=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=20),
    )

    blob_client = blob_service.get_blob_client(
        container=container_name,
        blob=blob_name,
    )

    return {
        "blob_name": blob_name,
        "blob_url": blob_client.url,
        "sas_upload_url": f"{blob_client.url}?{sas_token}",
        "content_type": content_type or "application/octet-stream",
    }

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

    file_obj.seek(0, 2)
    file_size = file_obj.tell()
    file_obj.seek(0)

    blob_client.upload_blob(
        file_obj,
        overwrite=True,
        length=file_size,
        max_concurrency=4,
        content_settings=ContentSettings(
            content_type=content_type or "application/octet-stream"
        ),
    )

    return {
        "blob_name": blob_name,
        "blob_url": blob_client.url,
        "content_type": content_type or "application/octet-stream",
        "file_size": file_size,
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

def delete_media_blob_from_azure(blob_name: str) -> bool:
    if not blob_name:
        return False

    blob_service = get_blob_service_client()

    blob_client = blob_service.get_blob_client(
        container=settings.AZURE_UPLOADS_CONTAINER,
        blob=blob_name,
    )

    try:
        blob_client.delete_blob()
        return True
    except Exception as error:
        print(f"[Azure cleanup] Could not delete blob {blob_name}: {error}")
        return False

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