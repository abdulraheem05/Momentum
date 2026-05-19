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
        "supabase",
        "requests",
        "numpy"
    )
)


secrets = [
    modal.Secret.from_name("momentum-secrets")
]


# ============================================================
# MAIN PROCESS VIDEO FUNCTION
# This now acts only as the controller.
# It does NOT pass /tmp file paths between Modal containers.
# ============================================================

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

    try:
        update_job_status(job_id, "STARTED")

        # -----------------------------
        # Video processing
        # -----------------------------
        if mode in ["video", "both"]:

            update_job_status(
                job_id,
                "PROCESSING_VIDEO"
            )

            clip_service = ClipService()

            clip_service.process_video_file.remote(
                job_id,
                source_type,
                source_url
            )

        # -----------------------------
        # Audio processing
        # -----------------------------
        if mode in ["audio", "both"]:

            update_job_status(
                job_id,
                "PROCESSING_AUDIO"
            )

            process_audio_from_source.remote(
                job_id,
                source_type,
                source_url
            )

        update_job_status(
            job_id,
            "READY"
        )

    except Exception as e:

        print("PROCESS_VIDEO_ERROR:", str(e))

        update_job_status(
            job_id,
            "FAILED"
        )

        raise e


# ============================================================
# VIDEO CHUNKING
# ============================================================

def split_video_chunks(video_path):
    output_dir = "/tmp/chunks"

    os.makedirs(output_dir, exist_ok=True)

    output_pattern = f"{output_dir}/chunk_%03d.mp4"

    subprocess.run(
        [
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
        ],
        check=True
    )

    return sorted([
        str(Path(output_dir) / file)
        for file in os.listdir(output_dir)
        if file.endswith(".mp4")
    ])


def download_blob_to_file(blob_url, local_path):
    from azure.storage.blob import BlobServiceClient
    from urllib.parse import urlparse

    blob_service = BlobServiceClient.from_connection_string(
        os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    )

    parsed_url = urlparse(blob_url)

    path_parts = parsed_url.path.lstrip("/").split("/", 1)

    container_name = path_parts[0]
    blob_name = path_parts[1]

    blob_client = blob_service.get_blob_client(
        container=container_name,
        blob=blob_name
    )

    with open(local_path, "wb") as file:
        file.write(
            blob_client.download_blob().readall()
        )


def download_source_video(source_type, source_url, local_video):
    os.makedirs("/tmp/video", exist_ok=True)

    if source_type == "youtube":
        subprocess.run(
            [
                "yt-dlp",
                "-f",
                "mp4",
                "-o",
                local_video,
                source_url
            ],
            check=True
        )

    else:
        download_blob_to_file(
            source_url,
            local_video
        )


# ============================================================
# SHARED CLIP SERVICE
# Downloads video, splits video, processes chunks, and searches.
# All video /tmp files stay inside this same Modal class container.
# ============================================================

@app.cls(
    image=image,
    secrets=secrets,
    gpu="H100",
    timeout=60 * 30
)
class ClipService:

    @modal.enter()
    def load_model(self):
        from transformers import (
            CLIPProcessor,
            CLIPModel
        )

        import torch

        self.device = (
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )

        print("Loading CLIP model inside Modal ClipService...")

        self.model = CLIPModel.from_pretrained(
            "openai/clip-vit-base-patch32"
        ).to(self.device)

        self.processor = CLIPProcessor.from_pretrained(
            "openai/clip-vit-base-patch32",
            use_fast=True
        )

        print("CLIP model loaded.")

    @modal.method()
    def process_video_file(self, job_id, source_type, source_url):
        local_video = "/tmp/video/input.mp4"

        try:
            download_source_video(
                source_type,
                source_url,
                local_video
            )

            chunks = split_video_chunks(
                local_video
            )

            for idx, chunk_path in enumerate(chunks):
                self.process_chunk_local(
                    job_id=job_id,
                    chunk_path=chunk_path,
                    offset=idx * 600
                )

        finally:
            try:
                if os.path.exists(local_video):
                    os.remove(local_video)
            except Exception:
                pass

    def process_chunk_local(self, job_id, chunk_path, offset):
        from scenedetect import (
            detect,
            ContentDetector
        )

        from PIL import Image
        import torch

        scenes = detect(
            chunk_path,
            ContentDetector(threshold=27.0)
        )

        for idx, scene in enumerate(scenes):

            start_time = scene[0].get_seconds()

            global_timestamp = (
                offset + start_time
            )

            frame_path = extract_frame(
                chunk_path,
                start_time,
                idx
            )

            thumbnail_url = upload_thumbnail(
                frame_path
            )

            image = Image.open(frame_path).convert("RGB")

            inputs = self.processor(
                images=image,
                return_tensors="pt"
            ).to(self.device)

            with torch.no_grad():
                features = self.model.get_image_features(
                    **inputs
                )

            vector = features[0].cpu().tolist()

            push_scene_embedding(
                job_id=job_id,
                vector=vector,
                timestamp=global_timestamp,
                thumbnail_url=thumbnail_url
            )

            try:
                os.remove(frame_path)
            except Exception:
                pass

    @modal.method()
    def search_scene(self, job_id, query, top_k=5):
        import torch
        from pinecone import Pinecone

        inputs = self.processor(
            text=[query],
            return_tensors="pt",
            padding=True
        ).to(self.device)

        with torch.no_grad():
            features = self.model.get_text_features(
                **inputs
            )

        query_vector = features[0].cpu().tolist()

        if len(query_vector) != 512:
            raise ValueError(
                f"Scene query vector dimension is {len(query_vector)}, expected 512"
            )

        pc = Pinecone(
            api_key=os.getenv("PINECONE_API_KEY")
        )

        index = pc.Index(
            os.getenv("PINECONE_INDEX")
        )

        results = index.query(
            vector=query_vector,
            top_k=top_k,
            include_metadata=True,
            filter={
                "job_id": {
                    "$eq": job_id
                }
            }
        )

        response = []

        for match in results["matches"]:

            metadata = match["metadata"]

            response.append({
                "timestamp": metadata["timestamp"],
                "thumbnail_url": metadata["thumbnail_url"],
                "score": match["score"]
            })

        return response


# ============================================================
# MODAL SCENE SEARCH FUNCTION
# ============================================================

@app.function(
    image=image,
    secrets=secrets,
    gpu="H100",
    timeout=60 * 10
)
def search_scenes(job_id, query, top_k=5):
    clip_service = ClipService()

    return clip_service.search_scene.remote(
        job_id,
        query,
        top_k
    )


# ============================================================
# AUDIO PROCESSING
# Audio now downloads the video inside its own Modal container.
# It does NOT receive /tmp path from process_video.
# ============================================================

@app.function(
    image=image,
    secrets=secrets,
    timeout=60 * 30
)
def process_audio_from_source(job_id, source_type, source_url):
    local_video = "/tmp/video/input.mp4"
    audio_path = f"/tmp/{job_id}_audio.mp3"

    try:
        download_source_video(
            source_type,
            source_url,
            local_video
        )

        subprocess.run(
            [
                "ffmpeg",
                "-i",
                local_video,
                "-vn",
                "-acodec",
                "mp3",
                audio_path
            ],
            check=True
        )

        transcribe_audio(
            job_id,
            audio_path
        )

    finally:
        try:
            if os.path.exists(local_video):
                os.remove(local_video)
        except Exception:
            pass

        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception:
            pass


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
        transcription
    )


def save_transcript(job_id, transcription):
    from azure.storage.blob import BlobServiceClient

    blob_service = BlobServiceClient.from_connection_string(
        os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    )

    blob_client = blob_service.get_blob_client(
        container=os.getenv("AZURE_RESULTS_CONTAINER"),
        blob=f"{job_id}.json"
    )

    segments = []

    for segment in transcription.segments:

        if hasattr(segment, "model_dump"):
            segments.append(segment.model_dump())

        elif isinstance(segment, dict):
            segments.append(segment)

        else:
            segments.append({
                "start": getattr(segment, "start", None),
                "end": getattr(segment, "end", None),
                "text": getattr(segment, "text", "")
            })

    payload = json.dumps({
        "segments": segments
    })

    blob_client.upload_blob(
        payload,
        overwrite=True
    )


# ============================================================
# AUDIO SEARCH SERVICE
# ============================================================

@app.cls(
    image=image,
    secrets=secrets,
    timeout=60 * 10
)
class AudioSearchService:

    @modal.enter()
    def load_model(self):
        from sentence_transformers import SentenceTransformer

        print("Loading SentenceTransformer inside Modal AudioSearchService...")

        self.model = SentenceTransformer(
            "all-MiniLM-L6-v2"
        )

        print("SentenceTransformer loaded.")

    @modal.method()
    def search_audio(self, job_id, query, top_k=5):
        import json
        import numpy as np
        from azure.storage.blob import BlobServiceClient

        blob_service = BlobServiceClient.from_connection_string(
            os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        )

        blob_client = blob_service.get_blob_client(
            container=os.getenv("AZURE_RESULTS_CONTAINER"),
            blob=f"{job_id}.json"
        )

        transcript_data = blob_client.download_blob().readall()

        transcript = json.loads(
            transcript_data
        )

        segments = transcript.get(
            "segments",
            []
        )

        if not segments:
            return []

        texts = [
            segment.get("text", "")
            for segment in segments
        ]

        query_vector = self.model.encode(
            query,
            normalize_embeddings=True
        )

        text_vectors = self.model.encode(
            texts,
            normalize_embeddings=True
        )

        scores = np.dot(
            text_vectors,
            query_vector
        )

        ranked_indices = scores.argsort()[::-1][:top_k]

        response = []

        for idx in ranked_indices:

            segment = segments[int(idx)]

            response.append({
                "timestamp": segment.get("start", 0),
                "text": segment.get("text", ""),
                "score": float(scores[int(idx)])
            })

        return response


# ============================================================
# MODAL AUDIO SEARCH FUNCTION
# ============================================================

@app.function(
    image=image,
    secrets=secrets,
    timeout=60 * 10
)
def search_audio(job_id, query, top_k=5):
    audio_service = AudioSearchService()

    return audio_service.search_audio.remote(
        job_id,
        query,
        top_k
    )


# ============================================================
# SHARED HELPERS
# ============================================================

def extract_frame(video_path, timestamp, idx):
    output = f"/tmp/frame_{uuid.uuid4()}_{idx}.jpg"

    subprocess.run(
        [
            "ffmpeg",
            "-ss",
            str(timestamp),
            "-i",
            video_path,
            "-frames:v",
            "1",
            output
        ],
        check=True
    )

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
        blob_client.upload_blob(
            data,
            overwrite=True
        )

    return blob_client.url


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

    if len(vector) != 512:
        raise ValueError(
            f"Scene image vector dimension is {len(vector)}, expected 512"
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