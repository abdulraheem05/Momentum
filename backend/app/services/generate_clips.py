import os
import uuid
import subprocess

from azure.storage.blob import BlobServiceClient


def generate_clip(
    source_video,
    timestamp
):

    start = max(timestamp - 5, 0)
    end = timestamp + 5

    output = f"/tmp/{uuid.uuid4()}.mp4"

    subprocess.run([
        "ffmpeg",
        "-ss",
        str(start),
        "-to",
        str(end),
        "-i",
        source_video,
        "-c",
        "copy",
        output
    ])

    return output


def upload_result_clip(local_path):

    blob_service = BlobServiceClient.from_connection_string(
        os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    )

    container = os.getenv(
        "AZURE_RESULTS_CONTAINER"
    )

    blob_name = f"{uuid.uuid4()}.mp4"

    blob_client = blob_service.get_blob_client(
        container=container,
        blob=blob_name
    )

    with open(local_path, "rb") as data:
        blob_client.upload_blob(data)

    return blob_client.url