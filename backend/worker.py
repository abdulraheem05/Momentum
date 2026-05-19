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
# ============================================================

@app.function(
    image=image,
    secrets=secrets,
    gpu="H100",
    timeout=60 * 60
)
def process_video(job_id, payload):
    import requests

    source_type = payload["source_type"]
    source_url = payload["source_url"]
    mode = payload["mode"]

    update_job_status(job_id, "DOWNLOADING")

    os.makedirs("/tmp/video", exist_ok=True)

    local_video = "/tmp/video/input.mp4"

    try:
        # -----------------------------
        # Download YouTube video
        # -----------------------------
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

        # -----------------------------
        # Download uploaded Azure video
        # -----------------------------
        else:
            response = requests.get(
                source_url,
                stream=True
            )

            response.raise_for_status()

            with open(local_video, "wb") as file:
                for chunk in response.iter_content(
                    chunk_size=1024 * 1024
                ):
                    if chunk:
                        file.write(chunk)

        # -----------------------------
        # Video processing
        # -----------------------------
        if mode in ["video", "both"]:

            update_job_status(
                job_id,
                "PROCESSING_VIDEO"
            )

            chunks = split_video_chunks(
                local_video
            )

            clip_service = ClipService()

            clip_service.process_chunk.map([
                {
                    "job_id": job_id,
                    "chunk_path": chunk,
                    "offset": idx * 600
                }
                for idx, chunk in enumerate(chunks)
            ])

        # -----------------------------
        # Audio processing
        # -----------------------------
        if mode in ["audio", "both"]:

            update_job_status(
                job_id,
                "PROCESSING_AUDIO"
            )

            process_audio.remote(
                job_id,
                local_video
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

    finally:
        try:
            if os.path.exists(local_video):
                os.remove(local_video)
        except Exception:
            pass


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


# ============================================================
# SHARED CLIP SERVICE
# This loads CLIP once per warm Modal container.
# It is used for BOTH:
# 1. image/frame embeddings during processing
# 2. text query embeddings during scene search
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

    # --------------------------------------------------------
    # Used during video processing
    # Creates image embeddings and stores them in Pinecone
    # --------------------------------------------------------

    @modal.method()
    def process_chunk(self, data):
        from scenedetect import (
            detect,
            ContentDetector
        )

        from PIL import Image
        import torch

        chunk_path = data["chunk_path"]
        offset = data["offset"]
        job_id = data["job_id"]

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

    # --------------------------------------------------------
    # Used during scene search
    # Creates text embedding and searches Pinecone
    # --------------------------------------------------------

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
# main.py can call this using:
# modal.Function.from_name("momentum-worker", "search_scenes")
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
# ============================================================

@app.function(
    image=image,
    secrets=secrets,
    timeout=60 * 30
)
def process_audio(job_id, video_path):
    audio_path = f"/tmp/{job_id}_audio.mp3"

    subprocess.run(
        [
            "ffmpeg",
            "-i",
            video_path,
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

    try:
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
# SentenceTransformer is separate from CLIP.
# It loads once per warm AudioSearchService Modal container.
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
# main.py can call this using:
# modal.Function.from_name("momentum-worker", "search_audio")
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