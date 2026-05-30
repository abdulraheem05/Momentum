import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import modal
from pydantic import BaseModel


app = modal.App("momentum-youtube-video-worker-gpu")


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
        "opencv-python-headless",
        "torch",
        "transformers",
        "Pillow",
        "pinecone",
        "numpy",
    )
)


class StartVideoRequest(BaseModel):
    job_id: str
    youtube_url: str
    youtube_id: str
    mode: str = "video"


class VisualSearchRequest(BaseModel):
    job_id: str
    youtube_id: str | None = None
    query: str
    top_k: int = 5


# ----------------------------
# Config
# ----------------------------

FRAME_SAMPLE_INTERVAL_SECONDS = 1.5
MAX_INDEXED_FRAMES = 500

CLIP_BATCH_SIZE = 32
PINECONE_BATCH_SIZE = 64

# Important:
# ViT-B/16 is better than ViT-B/32 and still outputs 512-dim vectors.
# So your existing 512-dim Pinecone index can still be used.
CLIP_MODEL_NAME = "openai/clip-vit-base-patch16"


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
        # Use 480p instead of 360p. 360p can lose small objects/details.
        # CLIP does not need 1080p, but 480p is a safer balance.
        "format": (
            "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/"
            "best[height<=480][ext=mp4]/"
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


def get_video_duration_seconds(video_path: str) -> float:
    import cv2

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError("Could not open video with OpenCV.")

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)

    cap.release()

    if not fps or fps <= 0:
        fps = 30

    if not frame_count or frame_count <= 0:
        return 0.0

    return float(frame_count / fps)


def build_dense_timestamps(
    video_path: str,
    interval_seconds: float = FRAME_SAMPLE_INTERVAL_SECONDS,
    max_frames: int = MAX_INDEXED_FRAMES,
) -> List[float]:
    duration = get_video_duration_seconds(video_path)

    if duration <= 0:
        return [0.0]

    timestamps = []
    current = 0.0

    # Avoid exact first and final frames because they can be black/title/transition frames.
    start_offset = min(0.5, duration * 0.05)
    current = start_offset

    while current < duration - 0.3:
        timestamps.append(round(current, 3))
        current += interval_seconds

    if not timestamps:
        timestamps = [duration * 0.5]

    # If the video is long, keep a fixed budget but spread frames across the full video.
    if len(timestamps) > max_frames:
        import numpy as np

        selected_indexes = np.linspace(0, len(timestamps) - 1, max_frames).astype(int)
        timestamps = [timestamps[i] for i in selected_indexes]

    print(f"[frames] duration={duration:.2f}s, timestamps={len(timestamps)}")

    return timestamps


def extract_frames_batch_from_video(
    video_path: str,
    timestamps: List[float],
) -> List[Any]:
    import cv2
    from PIL import Image

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError("Could not open video with OpenCV.")

    fps = cap.get(cv2.CAP_PROP_FPS)

    if not fps or fps <= 0:
        fps = 30

    images = []

    for timestamp in timestamps:
        frame_number = int(timestamp * fps)

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

        success, frame = cap.read()

        if not success or frame is None:
            print(f"[frames] Failed to read frame at {timestamp}s")
            continue

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        images.append(Image.fromarray(frame_rgb))

    cap.release()

    return images


_clip_model = None
_clip_processor = None
_clip_device = None


def get_clip_model_and_processor():
    global _clip_model, _clip_processor, _clip_device

    if _clip_model is not None and _clip_processor is not None:
        return _clip_model, _clip_processor, _clip_device

    import torch
    from transformers import CLIPModel, CLIPProcessor

    _clip_device = "cuda" if torch.cuda.is_available() else "cpu"

    print(f"[CLIP] Model: {CLIP_MODEL_NAME}")
    print(f"[CLIP] Device: {_clip_device}")

    _clip_model = CLIPModel.from_pretrained(CLIP_MODEL_NAME)
    _clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)

    _clip_model.to(_clip_device)
    _clip_model.eval()

    return _clip_model, _clip_processor, _clip_device


def normalize_vector(values):
    import numpy as np

    array = np.array(values, dtype="float32").reshape(-1)

    if array.shape[0] != 512:
        raise ValueError(
            f"CLIP embedding dimension is wrong. Expected 512, got {array.shape[0]}"
        )

    norm = np.linalg.norm(array)

    if norm == 0:
        return array.tolist()

    return (array / norm).tolist()


def average_vectors(vectors: List[List[float]]) -> List[float]:
    import numpy as np

    if not vectors:
        raise ValueError("Cannot average empty vector list.")

    matrix = np.array(vectors, dtype="float32")
    avg = matrix.mean(axis=0)

    return normalize_vector(avg)


def embed_images_batch(images) -> List[List[float]]:
    import torch

    model, processor, device = get_clip_model_and_processor()

    inputs = processor(
        images=images,
        return_tensors="pt",
        padding=True,
    )

    pixel_values = inputs.pixel_values.to(device)

    with torch.no_grad():
        image_features = model.get_image_features(pixel_values=pixel_values)

    vectors = image_features.detach().cpu().numpy()

    return [normalize_vector(vector) for vector in vectors]


def build_query_variants(query: str) -> List[str]:
    clean_query = query.strip()

    if not clean_query:
        return []

    # CLIP often works better with image-style prompts.
    return [
        clean_query,
        f"a photo of {clean_query}",
        f"a video frame showing {clean_query}",
        f"a scene with {clean_query}",
        f"an image containing {clean_query}",
    ]


def embed_text(query: str) -> List[float]:
    import torch

    model, processor, device = get_clip_model_and_processor()

    query_variants = build_query_variants(query)

    inputs = processor(
        text=query_variants,
        return_tensors="pt",
        padding=True,
        truncation=True,
    )

    input_ids = inputs.input_ids.to(device)
    attention_mask = inputs.attention_mask.to(device)

    with torch.no_grad():
        text_features = model.get_text_features(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )

    vectors = text_features.detach().cpu().numpy()
    normalized_vectors = [normalize_vector(vector) for vector in vectors]

    return average_vectors(normalized_vectors)


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


def index_video_frames(
    job_id: str,
    youtube_id: str,
    video_path: str,
) -> int:
    index = get_pinecone_index()

    # Important:
    # Use job_id as namespace so old runs of the same YouTube video do not pollute results.
    namespace = job_id

    timestamps = build_dense_timestamps(
        video_path=video_path,
        interval_seconds=FRAME_SAMPLE_INTERVAL_SECONDS,
        max_frames=MAX_INDEXED_FRAMES,
    )

    if not timestamps:
        return 0

    indexed_count = 0
    pending_vectors = []

    for batch_start in range(0, len(timestamps), CLIP_BATCH_SIZE):
        batch_timestamps = timestamps[batch_start:batch_start + CLIP_BATCH_SIZE]

        images = extract_frames_batch_from_video(
            video_path=video_path,
            timestamps=batch_timestamps,
        )

        if not images:
            continue

        # If some frames failed, align timestamps to actual images count conservatively.
        valid_timestamps = batch_timestamps[:len(images)]

        embeddings = embed_images_batch(images)

        for local_index, (embedding, timestamp) in enumerate(zip(embeddings, valid_timestamps)):
            if len(embedding) != 512:
                raise ValueError(f"Invalid embedding length: {len(embedding)}")

            frame_index = batch_start + local_index

            metadata = {
                "job_id": job_id,
                "youtube_id": youtube_id,
                "frame_index": int(frame_index),
                "timestamp": float(timestamp),
                "timestamp_label": format_timestamp(timestamp),
                "youtube_url": build_youtube_timestamp_url(youtube_id, timestamp),

                # Kept for frontend compatibility with your existing result code.
                "scene_index": int(frame_index),
                "scene_start": max(0.0, float(timestamp) - FRAME_SAMPLE_INTERVAL_SECONDS / 2),
                "scene_end": float(timestamp) + FRAME_SAMPLE_INTERVAL_SECONDS / 2,

                "indexing_type": "dense_frame_sampling",
                "sample_interval_seconds": float(FRAME_SAMPLE_INTERVAL_SECONDS),
            }

            vector_id = f"{job_id}-frame-{frame_index}"

            pending_vectors.append((vector_id, embedding, metadata))

        if len(pending_vectors) >= PINECONE_BATCH_SIZE:
            index.upsert(
                vectors=pending_vectors,
                namespace=namespace,
            )

            indexed_count += len(pending_vectors)

            update_video_job(
                job_id=job_id,
                visual_indexed_count=indexed_count,
            )

            print(f"[Pinecone] Upserted {indexed_count} frame vectors")

            pending_vectors.clear()

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


def dedupe_matches_by_time(matches: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    """
    Pinecone may return multiple nearby frames from the same visual moment.
    This keeps the best result from each nearby time window.
    """
    results = []
    used_time_buckets = set()

    for match in matches:
        metadata = match.get("metadata", {})
        timestamp = metadata.get("timestamp")

        if timestamp is None:
            continue

        timestamp = float(timestamp)

        # 5-second bucket. This avoids showing 00:10, 00:11, 00:13 as separate results.
        bucket = int(timestamp // 5)

        if bucket in used_time_buckets:
            continue

        used_time_buckets.add(bucket)
        results.append(match)

        if len(results) >= top_k:
            break

    return results


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
            message="Modal started video processing.",
            error="",
        )

        update_video_job(
            job_id=job_id,
            visual_status="downloading",
            pinecone_namespace=job_id,
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
                message="Video downloaded. Sampling frames.",
                video_title=video_title,
            )

            update_video_job(
                job_id=job_id,
                visual_status="sampling_frames",
                pinecone_namespace=job_id,
            )

            update_parent_job(
                job_id=job_id,
                progress=60,
                message="Creating CLIP frame embeddings.",
            )

            update_video_job(
                job_id=job_id,
                visual_status="embedding",
                pinecone_namespace=job_id,
            )

            indexed_count = index_video_frames(
                job_id=job_id,
                youtube_id=youtube_id,
                video_path=video_path,
            )

            update_video_job(
                job_id=job_id,
                visual_status="ready",
                visual_indexed_count=indexed_count,
                pinecone_namespace=job_id,
            )

        update_parent_job(
            job_id=job_id,
            status="ready",
            progress=100,
            message="Video frame index ready.",
            error="",
        )

        return {
            "ok": True,
            "job_id": job_id,
            "indexed_count": indexed_count,
            "pinecone_namespace": job_id,
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
        pinecone_namespace=payload.job_id,
    )

    return {
        "ok": True,
        "job_id": payload.job_id,
        "modal_call_id": function_call.object_id,
        "message": "GPU video processing started in background.",
    }