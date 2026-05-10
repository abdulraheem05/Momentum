import os
import uuid
import json
import subprocess
from pathlib import Path

import modal

app = modal.App("momentum-worker")

image = (
    modal.Image.debian_slim()
    .apt_install(
        "ffmpeg",
        "git"
    )
    .pip_install(
        "torch",
        "transformers",
        "sentence-transformers",
        "scenedetect[opencv]",
        "opencv-python-headless",
        "decord",
        "yt-dlp",
        "azure-storage-blob",
        "pinecone",
        "groq",
        "python-dotenv",
        "Pillow",
        "supabase"
    )
)

secrets = [
    modal.Secret.from_name("momentum-secrets")
]

@app.function(
    image=image,
    secrets=secrets,
    gpu="H100",
    timeout=60 * 60
)
def process_video(job_id, payload):

    source_type = payload["source_type"]
    source_url = payload["source_url"]
    mode = payload["mode"]

    os.makedirs("/tmp/video", exist_ok=True)

    local_video = "/tmp/video/input.mp4"

    if source_type == "youtube":

        subprocess.run([
            "yt-dlp",
            "-f",
            "mp4",
            "-o",
            local_video,
            source_url
        ])

    else:

        subprocess.run([
            "ffmpeg",
            "-i",
            source_url,
            "-c",
            "copy",
            local_video
        ])

    if mode in ["video", "both"]:

        chunks = split_video_chunks(local_video)

        process_chunk.map([
            {
                "job_id": job_id,
                "chunk_path": chunk,
                "offset": idx * 600
            }
            for idx, chunk in enumerate(chunks)
        ])

    if mode in ["audio", "both"]:
        process_audio(job_id, local_video)

    update_job_status(job_id, "READY")


def split_video_chunks(video_path):

    output_dir = "/tmp/chunks"

    os.makedirs(output_dir, exist_ok=True)

    output_pattern = f"{output_dir}/chunk_%03d.mp4"

    subprocess.run([
        "ffmpeg",
        "-i",
        video_path,
        "-c",
        "copy",
        "-map",
        "0",
        "-segment_time",
        "600",
        "-f",
        "segment",
        output_pattern
    ])

    return sorted([
        str(Path(output_dir) / file)
        for file in os.listdir(output_dir)
    ])


@app.function(
    image=image,
    secrets=secrets,
    gpu="H100",
    timeout=60 * 30
)

def process_chunk(data):

    from scenedetect import detect, ContentDetector

    chunk_path = data["chunk_path"]
    offset = data["offset"]
    job_id = data["job_id"]

    scenes = detect(
        chunk_path,
        ContentDetector(threshold=27.0)
    )

    for idx, scene in enumerate(scenes):

        start_time = scene[0].get_seconds()

        global_timestamp = offset + start_time

        frame_path = extract_frame(
            chunk_path,
            start_time,
            idx
        )

        thumbnail_url = upload_thumbnail(frame_path)

        vector = generate_clip_embedding(frame_path)

        push_scene_embedding(
            job_id,
            vector,
            global_timestamp,
            thumbnail_url
        )


def extract_frame(video_path, timestamp, idx):

    output = f"/tmp/frame_{idx}.jpg"

    subprocess.run([
        "ffmpeg",
        "-ss",
        str(timestamp),
        "-i",
        video_path,
        "-frames:v",
        "1",
        output
    ])

    return output


def upload_thumbnail(frame_path):

    from azure.storage.blob import BlobServiceClient

    connection_string = os.getenv(
        "AZURE_STORAGE_CONNECTION_STRING"
    )

    container = os.getenv(
        "AZURE_THUMBNAIL_CONTAINER"
    )

    blob_service = BlobServiceClient.from_connection_string(
        connection_string
    )

    blob_name = f"{uuid.uuid4()}.jpg"

    blob_client = blob_service.get_blob_client(
        container=container,
        blob=blob_name
    )

    with open(frame_path, "rb") as data:
        blob_client.upload_blob(data)

    return blob_client.url


def generate_clip_embedding(image_path):

    from transformers import CLIPProcessor, CLIPModel
    from PIL import Image
    import torch

    model = CLIPModel.from_pretrained(
        "openai/clip-vit-base-patch32"
    )

    processor = CLIPProcessor.from_pretrained(
        "openai/clip-vit-base-patch32"
    )

    image = Image.open(image_path)

    inputs = processor(
        images=image,
        return_tensors="pt"
    )

    with torch.no_grad():
        features = model.get_image_features(**inputs)

    return features[0].tolist()


def push_scene_embedding(
    job_id,
    vector,
    timestamp,
    thumbnail_url
):

    from pinecone import Pinecone

    pc = Pinecone(
        api_key=os.getenv("PINECONE_API_KEY")
    )

    index = pc.Index(
        os.getenv("PINECONE_INDEX")
    )

    index.upsert([
        {
            "id": str(uuid.uuid4()),
            "values": vector,
            "metadata": {
                "job_id": job_id,
                "timestamp": timestamp,
                "thumbnail_url": thumbnail_url
            }
        }
    ])


@app.function(
    image=image,
    secrets=secrets,
    timeout=60 * 30
)
def process_audio(job_id, video_path):

    audio_path = "/tmp/audio.mp3"

    subprocess.run([
        "ffmpeg",
        "-i",
        video_path,
        "-vn",
        "-acodec",
        "mp3",
        audio_path
    ])

    transcribe_audio(job_id, audio_path)


def transcribe_audio(job_id, audio_path):

    from groq import Groq

    client = Groq(
        api_key=os.getenv("GROQ_API_KEY")
    )

    with open(audio_path, "rb") as file:

        transcription = client.audio.transcriptions.create(
            file=file,
            model="whisper-large-v3-turbo",
            response_format="verbose_json"
        )

    save_transcript(
        job_id,
        transcription.text
    )

def save_transcript(job_id, text):

    from azure.storage.blob import BlobServiceClient

    blob_service = BlobServiceClient.from_connection_string(
        os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    )

    blob_client = blob_service.get_blob_client(
        container="transcripts",
        blob=f"{job_id}.json"
    )

    payload = json.dumps({
        "text": text
    })

    blob_client.upload_blob(
        payload,
        overwrite=True
    )

def update_job_status(job_id, status):

    from supabase import create_client

    supabase = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY")
    )

    (
        supabase
        .table("jobs")
        .update({
            "status": status
        })
        .eq("id", job_id)
        .execute()
    )