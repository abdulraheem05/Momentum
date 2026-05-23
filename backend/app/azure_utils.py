import json
from typing import Any, Dict

from azure.storage.blob import BlobServiceClient

from app.config import settings


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