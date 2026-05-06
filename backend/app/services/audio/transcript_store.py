import json
import os
from azure.storage.blob import BlobServiceClient

AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")

blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)


def _blob_name(video_id: str) -> str:
    return f"transcripts/{video_id}.json"


def save_transcript(video_id: str, data: dict) -> str:
    blob_name = _blob_name(video_id)

    blob_client = blob_service_client.get_blob_client(
        container=CONTAINER_NAME,
        blob=blob_name
    )

    blob_client.upload_blob(
        json.dumps(data, ensure_ascii=False),
        overwrite=True
    )

    return blob_name


def load_transcript(video_id: str) -> dict:
    blob_name = _blob_name(video_id)

    blob_client = blob_service_client.get_blob_client(
        container=CONTAINER_NAME,
        blob=blob_name
    )

    stream = blob_client.download_blob()
    return json.loads(stream.readall())