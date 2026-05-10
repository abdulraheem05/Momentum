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