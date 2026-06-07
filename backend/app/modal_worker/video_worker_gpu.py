import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import modal
from pydantic import BaseModel


app = modal.App("momentum-youtube-video-worker")


image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "ffmpeg",
        "curl",
        "unzip",
        "libgl1",
        "libglib2.0-0",
    )
    .run_commands(
        "curl -fsSL https://deno.land/install.sh | sh",
        "ln -s /root/.deno/bin/deno /usr/local/bin/deno",
        "deno --version",
    )
    .pip_install(
        "fastapi[standard]",
        "yt-dlp[default]",
        "supabase",
        "pydantic",
        "scenedetect[opencv]<0.8",
        "opencv-python-headless",
        "torch",
        "transformers",
        "Pillow",
        "pinecone",
        "numpy",
        "azure-storage-blob",
    )
)


class StartVideoRequest(BaseModel):
    job_id: str
    youtube_url: str
    youtube_id: str
    mode: str = "video"


class VisualSearchRequest(BaseModel):
    job_id: str
    youtube_id: str
    query: str
    top_k: int = 3


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_supabase_client():
    from supabase import create_client

    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_KEY"],
    )


def update_parent_job(
    job_id: str,
    status: str | None = None,
    progress: int | None = None,
    message: str | None = None,
    error: str | None = None,
    video_title: str | None = None,
) -> None:
    supabase = get_supabase_client()

    data: Dict[str, Any] = {
        "updated_at": now_iso(),
    }

    if status is not None:
        data["status"] = status

    if progress is not None:
        data["progress"] = progress

    if message is not None:
        data["message"] = message

    if error is not None:
        data["error"] = error

    if video_title is not None:
        data["video_title"] = video_title

    (
        supabase
        .table("youtube_jobs")
        .update(data)
        .eq("id", job_id)
        .execute()
    )


def update_video_job(
    job_id: str,
    visual_status: str | None = None,
    visual_indexed_count: int | None = None,
    pinecone_namespace: str | None = None,
) -> None:
    supabase = get_supabase_client()

    data: Dict[str, Any] = {
        "updated_at": now_iso(),
    }

    if visual_status is not None:
        data["visual_status"] = visual_status

    if visual_indexed_count is not None:
        data["visual_indexed_count"] = visual_indexed_count

    if pinecone_namespace is not None:
        data["pinecone_namespace"] = pinecone_namespace

    (
        supabase
        .table("youtube_video_jobs")
        .update(data)
        .eq("job_id", job_id)
        .execute()
    )


def write_youtube_cookies_if_available(workdir: str) -> str | None:
    cookies_text = os.environ.get("YOUTUBE_COOKIES")

    if not cookies_text:
        print("[cookies] YOUTUBE_COOKIES missing.")
        return None

    cookies_path = os.path.join(workdir, "youtube_cookies.txt")

    with open(cookies_path, "w", encoding="utf-8") as cookie_file:
        cookie_file.write(cookies_text)

    print(f"[cookies] Cookie file written: {cookies_path}")
    print(f"[cookies] Cookie file size: {os.path.getsize(cookies_path)} bytes")

    return cookies_path


def download_youtube_video(
    youtube_id: str,
    workdir: str,
) -> tuple[str, str]:
    import yt_dlp

    normalized_url = f"https://www.youtube.com/watch?v={youtube_id}"

    file_stem = str(uuid.uuid4())
    output_template = os.path.join(workdir, f"{file_stem}.%(ext)s")

    cookies_path = write_youtube_cookies_if_available(workdir)

    ydl_opts = {
        # Prefer mp4 video with audio if available.
        # Fallback to any best format.
        "format": (
            "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/"
            "best[height<=360][ext=mp4]/"
            "best[height<=360]/"
            "best"
        ),
        "merge_output_format": "mp4",

        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,

        "retries": 5,
        "fragment_retries": 5,
        "extractor_retries": 5,
        "socket_timeout": 30,

        "force_ipv4": True,
        "js_runtimes": {
            "deno": {},
        },
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"]
            }
        },
    }

    if cookies_path:
        ydl_opts["cookiefile"] = cookies_path

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(normalized_url, download=True)
        video_title = info.get("title", "Untitled YouTube Video")

        downloaded_path = ydl.prepare_filename(info)

    possible_files = [
        file for file in os.listdir(workdir)
        if file.startswith(file_stem)
    ]

    mp4_files = [
        os.path.join(workdir, file)
        for file in possible_files
        if file.endswith(".mp4")
    ]

    if mp4_files:
        return mp4_files[0], video_title

    if os.path.exists(downloaded_path):
        return downloaded_path, video_title

    raise FileNotFoundError(
        f"Video download failed. Files found: {os.listdir(workdir)}"
    )


def detect_scenes(video_path: str) -> List[Dict[str, float]]:
    from scenedetect import detect, ContentDetector

    raw_scenes = detect(
        video_path,
        ContentDetector(threshold=30.0),
        start_in_scene=True,
    )

    scenes: List[Dict[str, float]] = []

    for index, (start, end) in enumerate(raw_scenes):
        start_seconds = start.get_seconds()
        end_seconds = end.get_seconds()

        duration = end_seconds - start_seconds

        if duration <= 1.0:
            continue

        middle_seconds = (start_seconds + end_seconds) / 2

        scenes.append({
            "scene_index": index,
            "start_time": float(start_seconds),
            "end_time": float(end_seconds),
            "timestamp": float(middle_seconds),
        })

    if not scenes:
        scenes.append({
            "scene_index": 0,
            "start_time": 0.0,
            "end_time": 0.0,
            "timestamp": 0.0,
        })

    return scenes


def extract_frame_image_at_timestamp(video_path: str, timestamp: float):
    """
    Extracts one frame using OpenCV and returns a PIL RGB image.
    This avoids starting a new ffmpeg process for every scene.
    """
    import cv2
    from PIL import Image

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError("Could not open video with OpenCV.")

    fps = cap.get(cv2.CAP_PROP_FPS)

    if not fps or fps <= 0:
        fps = 30

    frame_number = int(timestamp * fps)

    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

    success, frame = cap.read()

    cap.release()

    if not success or frame is None:
        raise RuntimeError(f"Could not extract frame at {timestamp}s")

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    return Image.fromarray(frame_rgb)


_clip_model = None
_clip_processor = None
_clip_device = None


def get_clip_model_and_processor():
    global _clip_model, _clip_processor, _clip_device

    if _clip_model is not None and _clip_processor is not None:
        return _clip_model, _clip_processor, _clip_device

    import torch
    from transformers import CLIPModel, CLIPProcessor

    model_name = "openai/clip-vit-base-patch32"

    _clip_device = "cuda" if torch.cuda.is_available() else "cpu"

    print(f"[CLIP] Using device: {_clip_device}")

    _clip_model = CLIPModel.from_pretrained(model_name)
    _clip_processor = CLIPProcessor.from_pretrained(model_name)

    _clip_model.to(_clip_device)
    _clip_model.eval()

    return _clip_model, _clip_processor, _clip_device


def normalize_vector(values):
    import numpy as np

    array = np.array(values, dtype="float32")

    # Force it to be one-dimensional
    array = array.reshape(-1)

    if array.shape[0] != 512:
        raise ValueError(
            f"CLIP embedding dimension is wrong. Expected 512, got {array.shape[0]}"
        )

    norm = np.linalg.norm(array)

    if norm == 0:
        return array.tolist()

    return (array / norm).tolist()


def embed_image(frame_path: str) -> List[float]:
    import torch
    from PIL import Image

    model, processor, device = get_clip_model_and_processor()

    image = Image.open(frame_path).convert("RGB")

    inputs = processor(
        images=image,
        return_tensors="pt",
    )

    pixel_values = inputs.pixel_values.to(device)

    with torch.no_grad():
        vision_outputs = model.vision_model(pixel_values=pixel_values)

        pooled_output = vision_outputs.pooler_output

        image_features = model.visual_projection(pooled_output)

    print(f"[CLIP] image_features shape: {tuple(image_features.shape)}")

    vector = image_features.squeeze(0).detach().cpu().numpy()

    return normalize_vector(vector)

def embed_images_batch(images) -> List[List[float]]:
    """
    Embeds many PIL images at once.
    This is where GPU becomes useful.
    """
    import torch

    model, processor, device = get_clip_model_and_processor()

    inputs = processor(
        images=images,
        return_tensors="pt",
        padding=True,
    )

    pixel_values = inputs.pixel_values.to(device)

    with torch.no_grad():
        vision_outputs = model.vision_model(pixel_values=pixel_values)
        pooled_output = vision_outputs.pooler_output
        image_features = model.visual_projection(pooled_output)

    print(f"[CLIP] batch image_features shape: {tuple(image_features.shape)}")

    vectors = image_features.detach().cpu().numpy()

    return [normalize_vector(vector) for vector in vectors]


def embed_text(query: str) -> List[float]:
    import torch

    model, processor, device = get_clip_model_and_processor()

    inputs = processor(
        text=[query],
        return_tensors="pt",
        padding=True,
        truncation=True,
    )

    input_ids = inputs.input_ids.to(device)
    attention_mask = inputs.attention_mask.to(device)

    with torch.no_grad():
        text_outputs = model.text_model(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )

        pooled_output = text_outputs.pooler_output

        text_features = model.text_projection(pooled_output)

    print(f"[CLIP] text_features shape: {tuple(text_features.shape)}")

    vector = text_features.squeeze(0).detach().cpu().numpy()

    return normalize_vector(vector)


def get_pinecone_index():
    from pinecone import Pinecone

    pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    return pc.Index(os.environ["PINECONE_INDEX_NAME"])


def format_timestamp(seconds: float) -> str:
    total_seconds = int(seconds)

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    return f"{minutes:02d}:{secs:02d}"


def build_youtube_timestamp_url(youtube_id: str, seconds: float) -> str:
    return f"https://www.youtube.com/watch?v={youtube_id}&t={int(seconds)}s"


def index_video_scenes(
    job_id: str,
    youtube_id: str,
    video_path: str,
) -> int:
    index = get_pinecone_index()
    namespace = youtube_id

    scenes = detect_scenes(video_path)

    if not scenes:
        return 0

    image_batch = []
    metadata_batch = []

    clip_batch_size = 16
    pinecone_batch_size = 16

    indexed_count = 0
    pending_vectors = []

    for scene in scenes:
        scene_index = scene["scene_index"]
        timestamp = scene["timestamp"]

        image = extract_frame_image_at_timestamp(
            video_path=video_path,
            timestamp=timestamp,
        )

        metadata = {
            "job_id": job_id,
            "youtube_id": youtube_id,
            "scene_index": int(scene_index),
            "timestamp": float(timestamp),
            "timestamp_label": format_timestamp(timestamp),
            "youtube_url": build_youtube_timestamp_url(youtube_id, timestamp),
            "scene_start": float(scene["start_time"]),
            "scene_end": float(scene["end_time"]),
        }

        image_batch.append(image)
        metadata_batch.append(metadata)

        if len(image_batch) >= clip_batch_size:
            embeddings = embed_images_batch(image_batch)

            for embedding, metadata_item in zip(embeddings, metadata_batch):
                if len(embedding) != 512:
                    raise ValueError(f"Invalid embedding length: {len(embedding)}")

                vector_id = f"{job_id}-{metadata_item['scene_index']}"
                pending_vectors.append((vector_id, embedding, metadata_item))

            image_batch.clear()
            metadata_batch.clear()

            if len(pending_vectors) >= pinecone_batch_size:
                index.upsert(
                    vectors=pending_vectors,
                    namespace=namespace,
                )

                indexed_count += len(pending_vectors)

                update_video_job(
                    job_id=job_id,
                    visual_indexed_count=indexed_count,
                )

                print(f"[Pinecone] Upserted {indexed_count} scene vectors")

                pending_vectors.clear()

    # Process remaining images
    if image_batch:
        embeddings = embed_images_batch(image_batch)

        for embedding, metadata_item in zip(embeddings, metadata_batch):
            if len(embedding) != 512:
                raise ValueError(f"Invalid embedding length: {len(embedding)}")

            vector_id = f"{job_id}-{metadata_item['scene_index']}"
            pending_vectors.append((vector_id, embedding, metadata_item))

    # Final Pinecone upsert
    if pending_vectors:
        index.upsert(
            vectors=pending_vectors,
            namespace=namespace,
        )

        indexed_count += len(pending_vectors)

        update_video_job(
            job_id=job_id,
            visual_indexed_count=indexed_count,
        )

        print(f"[Pinecone] Final upsert complete. Total: {indexed_count}")

    return indexed_count


@app.function(
    image=image,
    gpu="T4",
    timeout=60 * 60,
    secrets=[
        modal.Secret.from_name("momentum-youtube-v1-secrets"),
        modal.Secret.from_name("momentum-youtube-cookies"),
    ],
)
def process_video_background(
    job_id: str,
    youtube_url: str,
    youtube_id: str,
) -> Dict[str, Any]:
    try:
        update_parent_job(
            job_id=job_id,
            status="processing",
            progress=10,
            message=f"Modal started processing",
            error="",
        )

        update_video_job(
            job_id=job_id,
            visual_status="downloading",
            pinecone_namespace=youtube_id,
        )

        with tempfile.TemporaryDirectory() as workdir:
            update_parent_job(
                job_id=job_id,
                progress=25,
                message="Downloading YouTube video.",
            )

            video_path, video_title = download_youtube_video(
                youtube_id=youtube_id,
                workdir=workdir,
            )

            update_parent_job(
                job_id=job_id,
                progress=45,
                message="Video downloaded. Detecting scenes.",
                video_title=video_title,
            )

            update_video_job(
                job_id=job_id,
                visual_status="detecting_scenes",
            )

            update_parent_job(
                job_id=job_id,
                progress=60,
                message=f"Creating CLIP embeddings and indexing scenes.",
            )

            update_video_job(
                job_id=job_id,
                visual_status="embedding",
            )

            indexed_count = index_video_scenes(
                job_id=job_id,
                youtube_id=youtube_id,
                video_path=video_path,
            )

            update_video_job(
                job_id=job_id,
                visual_status="ready",
                visual_indexed_count=indexed_count,
                pinecone_namespace=youtube_id,
            )

        update_parent_job(
            job_id=job_id,
            status="ready",
            progress=100,
            message="Video scene index ready.",
            error="",
        )

        return {
            "ok": True,
            "job_id": job_id,
            "indexed_count": indexed_count,
        }

    except Exception as error:
        update_parent_job(
            job_id=job_id,
            status="failed",
            progress=0,
            message="Video processing failed.",
            error=str(error),
        )

        update_video_job(
            job_id=job_id,
            visual_status="failed",
        )

        return {
            "ok": False,
            "job_id": job_id,
            "error": str(error),
        }


@app.function(
    image=image,
    timeout=60,
    secrets=[
        modal.Secret.from_name("momentum-youtube-v1-secrets"),
        modal.Secret.from_name("momentum-youtube-cookies"),
    ],
)
@modal.fastapi_endpoint(method="POST")
def start_video_processing(payload: StartVideoRequest):
    function_call = process_video_background.spawn(
        job_id=payload.job_id,
        youtube_url=payload.youtube_url,
        youtube_id=payload.youtube_id,
    )

    update_parent_job(
        job_id=payload.job_id,
        status="queued",
        progress=5,
        message="Video processing submitted to Modal.",
        error="",
    )

    update_video_job(
        job_id=payload.job_id,
        visual_status="queued",
        pinecone_namespace=payload.youtube_id,
    )

    return {
        "ok": True,
        "job_id": payload.job_id,
        "modal_call_id": function_call.object_id,
        "message": "Video processing started in background.",
    }


@app.function(
    image=image,
    timeout=120,
    secrets=[
        modal.Secret.from_name("momentum-youtube-v1-secrets"),
    ],
)
@modal.fastapi_endpoint(method="POST")
def search_visual_scenes(payload: VisualSearchRequest):
    query_vector = embed_text(payload.query)

    index = get_pinecone_index()

    namespace = payload.youtube_id

    search_response = index.query(
        vector=query_vector,
        top_k=payload.top_k,
        namespace=namespace,
        include_metadata=True,
    )

    matches = search_response.get("matches", [])

    results = []

    for match in matches:
        metadata = match.get("metadata", {})

        results.append({
            "score": match.get("score"),
            "timestamp": metadata.get("timestamp"),
            "timestamp_label": metadata.get("timestamp_label"),
            "youtube_url": metadata.get("youtube_url"),
            "scene_index": metadata.get("scene_index"),
            "scene_start": metadata.get("scene_start"),
            "scene_end": metadata.get("scene_end"),
        })

    return {
        "job_id": payload.job_id,
        "youtube_id": payload.youtube_id,
        "query": payload.query,
        "count": len(results),
        "results": results,
    }