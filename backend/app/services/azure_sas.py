import os
import uuid
from datetime import datetime, timedelta

from azure.storage.blob import (
    BlobSasPermissions,
    BlobServiceClient,
    generate_blob_sas
)

from dotenv import load_dotenv

load_dotenv()

CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")

blob_service_client = BlobServiceClient.from_connection_string(
    CONNECTION_STRING
)


def generate_upload_sas():
    job_id = str(uuid.uuid4())

    blob_name = f"uploads/{job_id}.mp4"

    client = blob_service_client.get_blob_client(
        container=CONTAINER_NAME,
        blob=blob_name
    )

    sas_token = generate_blob_sas(
        account_name=blob_service_client.account_name,
        container_name=CONTAINER_NAME,
        blob_name=blob_name,
        account_key=blob_service_client.credential.account_key,
        permission=BlobSasPermissions(write=True, create=True),
        expiry=datetime.utcnow() + timedelta(hours=1)
    )

    upload_url = f"{client.url}?{sas_token}"

    return {
        "job_id": job_id,
        "upload_url": upload_url,
        "blob_url": client.url
    }