from azure.storage.blob import BlobServiceClient
import os


def delete_original_video(blob_url):

    blob_service = BlobServiceClient.from_connection_string(
        os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    )

    container = os.getenv(
        "AZURE_CONTAINER_NAME"
    )

    blob_name = blob_url.split("/")[-1]

    blob_client = blob_service.get_blob_client(
        container=container,
        blob=f"uploads/{blob_name}"
    )

    blob_client.delete_blob()