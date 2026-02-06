import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.paths import ensure_dir, UPLOADS_DIR

app = FastAPI(title="Video Scene Finder")

app.add_middleware(
    CORSMiddleware,
    allow_origins = ["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"]
)

ensure_dir()

CHUNK_SIZE = 1024*1024

@app.get("/health")
def health():
    return{"ok":True}

@app.post("/videos/upload")
async def upload_video(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException("File not found")
    
    if not file.filename.lower().endswith((".mp4", ".mov", ".mkv")):
        raise HTTPException("Fil format not supported")
    
    video_id = str(uuid.uuid4())

    ext = Path(file.filename).suffix.lower() or "mp4"
    dest = UPLOADS_DIR/f"{video_id}{ext}"

    bytes_written = 0

    try:
        with open (dest, "wb") as out:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break

                out.write(chunk)
                bytes_written += len(chunk)

    except Exception as e:
        if dest.exists():
            dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")
    
    return {
        "video_id": video_id,
        "saved_as": dest.name,
        "size_bytes": bytes_written
    }