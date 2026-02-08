# Video Finder — Audio Search + Scene Search (FastAPI + React)

This project helps you find a moment inside a video using two independent pipelines:

1) **Audio Search (Dialogue Search)**
   - Upload a video
   - Extract audio
   - Transcribe speech (English/Tamil)
   - Search the transcript for a phrase the user remembers
   - Return:
     - best timestamp (hh:mm:ss)
     - a 10-second clip around that time

2) **Scene Search (Visual Search / Scene Description)**
   - Upload a video
   - Sample frames (default: 1 frame every 3 seconds)
   - Compute CLIP embeddings for frames (GPU supported)
   - Build a FAISS index for fast similarity search
   - Search using a scene description prompt
   - Return:
     - best timestamp (hh:mm:ss)
     - a 10-second clip around that time

✅ Key design choice: **Audio and Scene are separate uploads/jobs**  
So a scene-only user never waits for transcription, and an audio-only user never waits for frame indexing.

---

## Tech Stack

- **Backend:** FastAPI (Python)
- **Frontend:** React + Vite
- **Audio:** FFmpeg → WAV → faster-whisper (GPU optional)
- **Scene:** Frame sampling → CLIP embeddings → FAISS index
- **Storage:** Local filesystem + SQLite job status

---

## How the pipelines work

### A) Audio Search pipeline
**Goal:** find timestamp based on dialogue the user remembers.

Steps:
1. Upload video as `job_id.mp4`
2. FFmpeg extracts mono 16kHz WAV:
   - `uploads/job_id.mp4` → `audio/job_id.wav`
3. Transcribe WAV with faster-whisper into segments:
   - Each segment includes:
     - `start` time (seconds)
     - `end` time
     - text
4. Search:
   - normalize query + segment text
   - score segments by word overlap + exact phrase bonus
5. Best match is returned with:
   - `timestamp` (hh:mm:ss)
   - `clip_url` to fetch a 10s clip

### B) Scene Search pipeline
**Goal:** find timestamp based on a visual description prompt.

Steps:
1. Upload video as `job_id.mp4`
2. Sample frames every N seconds (default `3s`):
   - frames saved temporarily or directly embedded
3. Compute CLIP embeddings:
   - image embeddings: `[N, 512]` float32 (normalized)
4. Build FAISS IndexFlatIP:
   - inner product on normalized vectors == cosine similarity
5. Search:
   - embed the text query using CLIP text encoder
   - retrieve top-k nearest frame embeddings
6. Best match returned with:
   - `timestamp` (hh:mm:ss)
   - `clip_url` to fetch a 10s clip

---

## Files/folders created at runtime (backend/data)

The backend writes runtime artifacts into `backend/data/` (ignored by Git).

Typical structure:

- `backend/data/uploads/` — uploaded videos (`{job_id}.mp4`)
- `backend/data/audio/` — extracted WAV (`{job_id}.wav`) (audio jobs)
- `backend/data/transcriptions/` — transcript JSON (audio jobs)
- `backend/data/index/` — FAISS index + metadata (scene jobs)
- `backend/data/clips/` — generated 10s clips (`{start}_{dur}.mp4`)
- `backend/data/app.db` — SQLite job status store

---

## API Endpoints

### Audio
- `POST /audio/videos`  
  Upload video + start transcription  
  Params: `file`, `language=en|ta`, `model_size=tiny|base|small|medium|large-v3`

- `GET /audio/videos/{job_id}/status`  
  Returns stage + progress + ready

- `POST /audio/videos/{job_id}/search`  
  Body: `{ query, top_k, clip_duration }`

- `GET /audio/videos/{job_id}/clip?start=...&dur=10`  
  Streams a 10-second clip

### Scene
- `POST /scene/videos`  
  Upload video + start frame indexing

- `GET /scene/videos/{job_id}/status`

- `POST /scene/videos/{job_id}/search`  
  Body: `{ query, top_k, clip_duration }`

- `GET /scene/videos/{job_id}/clip?start=...&dur=10`

---

## Prerequisites (Local Run)

### Required
- **Python 3.10.x**
- **Node 18+**
- **FFmpeg installed and available in PATH**
  - Check: `ffmpeg -version`

### Optional (GPU)
- NVIDIA GPU + drivers (for faster scene/audio)
- Torch CUDA build (installed via GPU requirements)

---

## Running locally (Windows)

### 1) Backend (CPU)
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir -r requirements\cpu.txt

python run.py
