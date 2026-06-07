import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import modal
from pydantic import BaseModel


app = modal.App("momentum-youtube-v1-worker")


image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install(
        "ffmpeg",
        "curl",
        "unzip",
    )
    .run_commands(
        "curl -fsSL https://deno.land/install.sh | sh",
        "ln -s /root/.deno/bin/deno /usr/local/bin/deno",
        "deno --version",
    )
    .pip_install(
        "fastapi[standard]",
        "yt-dlp[default]",
        "groq",
        "supabase",
        "azure-storage-blob",
        "pydantic",
    )
)


class ProcessYouTubeRequest(BaseModel):
    job_id: str
    source_type: str = "youtube"

    youtube_url: str | None = None
    youtube_id: str | None = None

    media_blob_name: str | None = None
    media_blob_url: str | None = None
    original_file_name: str | None = None

    mode: str = "audio"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_supabase_client():
    from supabase import create_client

    supabase_url = os.environ["SUPABASE_URL"]
    supabase_key = os.environ["SUPABASE_KEY"]

    return create_client(supabase_url, supabase_key)


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

def update_audio_job(
    job_id: str,
    audio_status: str | None = None,
    transcript_blob_name: str | None = None,
    transcript_blob_url: str | None = None,
) -> None:
    supabase = get_supabase_client()

    data: Dict[str, Any] = {
        "updated_at": now_iso(),
    }

    if audio_status is not None:
        data["audio_status"] = audio_status

    if transcript_blob_name is not None:
        data["transcript_blob_name"] = transcript_blob_name

    if transcript_blob_url is not None:
        data["transcript_blob_url"] = transcript_blob_url

    (
        supabase
        .table("youtube_audio_jobs")
        .update(data)
        .eq("job_id", job_id)
        .execute()
    )


def download_youtube_audio(youtube_url: str, workdir: str) -> tuple[str, str]:
    """
    Downloads YouTube media and extracts audio to mp3.
    Uses cookies if provided through Modal Secret.
    """

    import yt_dlp

    file_stem = str(uuid.uuid4())
    output_template = os.path.join(workdir, f"{file_stem}.%(ext)s")

    cookies_text = os.environ.get("YOUTUBE_COOKIES")
    cookies_path = None

    if cookies_text:
        cookies_path = os.path.join(workdir, "youtube_cookies.txt")
        with open(cookies_path, "w", encoding="utf-8") as cookie_file:
            cookie_file.write(cookies_text)

    ydl_opts = {
    "format": "139/bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best[acodec!=none]/best",

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

    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "64",
        }
    ],
}

    if cookies_path:
        ydl_opts["cookiefile"] = cookies_path

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=True)
        video_title = info.get("title", "Untitled YouTube Video")

    audio_path = os.path.join(workdir, f"{file_stem}.mp3")

    if not os.path.exists(audio_path):
        existing_files = os.listdir(workdir)
        raise FileNotFoundError(
            f"Audio extraction failed. MP3 file was not created. Files found: {existing_files}"
        )

    return audio_path, video_title

def download_uploaded_media(
    media_blob_name: str,
    workdir: str,
) -> str:
    from azure.storage.blob import BlobServiceClient

    connection_string = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    container_name = os.environ.get("AZURE_UPLOADS_CONTAINER", "momentum-uploads")

    extension = os.path.splitext(media_blob_name)[1] or ".mp4"
    output_path = os.path.join(workdir, f"uploaded-media{extension}")

    blob_service = BlobServiceClient.from_connection_string(connection_string)

    blob_client = blob_service.get_blob_client(
        container=container_name,
        blob=media_blob_name,
    )

    with open(output_path, "wb") as file:
        stream = blob_client.download_blob()
        file.write(stream.readall())

    return output_path


def extract_audio_from_media(media_path: str, workdir: str) -> str:
    import subprocess

    output_path = os.path.join(workdir, "uploaded-audio.mp3")

    command = [
        "ffmpeg",
        "-y",
        "-i", media_path,
        "-vn",
        "-acodec", "libmp3lame",
        "-ar", "16000",
        "-ac", "1",
        "-b:a", "64k",
        output_path,
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr}")

    return output_path


def transcribe_with_groq(audio_path: str) -> List[Dict[str, Any]]:
    """
    Transcribes audio using Groq Whisper and returns timestamped segments.
    """

    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    with open(audio_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            file=audio_file,
            model="whisper-large-v3-turbo",
            response_format="verbose_json",
        )

    raw_segments = getattr(transcription, "segments", None)

    if raw_segments is None:
        raise RuntimeError(
            "Groq transcription did not return timestamp segments."
        )

    segments: List[Dict[str, Any]] = []

    for index, segment in enumerate(raw_segments):
        start = getattr(segment, "start", None)
        end = getattr(segment, "end", None)
        text = getattr(segment, "text", None)

        if isinstance(segment, dict):
            start = segment.get("start")
            end = segment.get("end")
            text = segment.get("text")

        if text:
            segments.append(
                {
                    "index": index,
                    "start": float(start or 0),
                    "end": float(end or 0),
                    "text": text.strip(),
                }
            )

    if not segments:
        raise RuntimeError("No transcript segments were produced.")

    return segments


def upload_transcript_to_azure(
    job_id: str,
    transcript_data: Dict[str, Any],
) -> tuple[str, str]:
    """
    Uploads transcript JSON to Azure Blob.
    Returns blob_name and blob_url.
    """

    from azure.storage.blob import BlobServiceClient, ContentSettings

    connection_string = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    container_name = os.environ["AZURE_TRANSCRIPTS_CONTAINER"]

    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = blob_service_client.get_container_client(container_name)

    try:
        container_client.create_container()
    except Exception:
        # Container already exists, or creation is not allowed.
        pass

    blob_name = f"{job_id}.json"
    json_text = json.dumps(transcript_data, ensure_ascii=False, indent=2)

    blob_client = container_client.get_blob_client(blob_name)

    blob_client.upload_blob(
        json_text,
        overwrite=True,
        content_settings=ContentSettings(content_type="application/json"),
    )

    return blob_name, blob_client.url


@app.function(
    image=image,
    timeout=60 * 60,
    secrets=[
        modal.Secret.from_name("momentum-youtube-v1-secrets"),
        modal.Secret.from_name("momentum-youtube-cookies"),
    ],
)
def process_youtube_video_background(
    job_id: str,
    source_type: str = "youtube",
    youtube_url: str | None = None,
    youtube_id: str | None = None,
    media_blob_name: str | None = None,
    media_blob_url: str | None = None,
    original_file_name: str | None = None,
) -> Dict[str, Any]:
    try:
        update_parent_job(
            job_id=job_id,
            status="processing",
            progress=10,
            message="Audio worker started.",
            error="",
        )

        update_audio_job(
            job_id=job_id,
            audio_status="processing",
        )

        with tempfile.TemporaryDirectory() as workdir:
            if source_type == "upload":
                if not media_blob_name:
                    raise ValueError("media_blob_name is required for upload source.")

                update_parent_job(
                    job_id=job_id,
                    status="processing",
                    progress=25,
                    message="Downloading uploaded file.",
                )

                media_path = download_uploaded_media(
                    media_blob_name=media_blob_name,
                    workdir=workdir,
                )

                update_parent_job(
                    job_id=job_id,
                    status="processing",
                    progress=40,
                    message="Extracting audio from uploaded file.",
                )

                audio_path = extract_audio_from_media(
                    media_path=media_path,
                    workdir=workdir,
                )

                video_title = original_file_name or "Uploaded audio"

            else:
                if not youtube_url:
                    raise ValueError("youtube_url is required for YouTube source.")

                audio_path, video_title = download_youtube_audio(
                    youtube_url=youtube_url,
                    workdir=workdir,
                )

            update_parent_job(
                job_id=job_id,
                status="processing",
                progress=55,
                message="Audio extracted. Transcribing with Groq.",
                video_title=video_title,
            )

            update_audio_job(
                job_id=job_id,
                audio_status="transcribing",
            )

            segments = transcribe_with_groq(audio_path)

            transcript_data = {
                "job_id": job_id,
                "source_type": source_type,
                "youtube_id": youtube_id,
                "youtube_url": youtube_url,
                "media_blob_url": media_blob_url,
                "original_file_name": original_file_name,
                "video_title": video_title,
                "created_at": now_iso(),
                "segments": segments,
            }

            update_parent_job(
                job_id=job_id,
                status="processing",
                progress=85,
                message="Transcription complete. Uploading transcript JSON.",
            )

            update_audio_job(
                job_id=job_id,
                audio_status="uploading",
            )

            blob_name, blob_url = upload_transcript_to_azure(
                job_id=job_id,
                transcript_data=transcript_data,
            )

        update_audio_job(
            job_id=job_id,
            audio_status="ready",
            transcript_blob_name=blob_name,
            transcript_blob_url=blob_url,
        )

        update_parent_job(
            job_id=job_id,
            status="ready",
            progress=100,
            message="Transcript ready.",
            video_title=video_title,
            error="",
        )

        return {
            "ok": True,
            "job_id": job_id,
            "status": "ready",
            "transcript_blob_name": blob_name,
        }

    except Exception as error:
        update_parent_job(
            job_id=job_id,
            status="failed",
            progress=0,
            message="Audio processing failed.",
            error=str(error),
        )

        update_audio_job(
            job_id=job_id,
            audio_status="failed",
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
def start_youtube_processing(payload: ProcessYouTubeRequest):
    """
    Public Modal web endpoint.

    This does NOT process the video directly.
    It only spawns the background worker and returns immediately.
    """

    function_call = process_youtube_video_background.spawn(
        job_id=payload.job_id,
        source_type=payload.source_type,
        youtube_url=payload.youtube_url,
        youtube_id=payload.youtube_id,
        media_blob_name=payload.media_blob_name,
        media_blob_url=payload.media_blob_url,
        original_file_name=payload.original_file_name,
    )

    update_parent_job(
        job_id=payload.job_id,
        status="queued",
        progress=5,
        message="Audio processing job submitted to Modal.",
        error="",
    )

    update_audio_job(
        job_id=payload.job_id,
        audio_status="queued",
    )

    return {
        "ok": True,
        "job_id": payload.job_id,
        "modal_call_id": function_call.object_id,
        "message": "Processing started in background.",
    }