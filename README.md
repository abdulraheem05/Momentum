🎬 Video Finder
Audio Search + Scene Search (FastAPI • React • CLIP • FAISS • Whisper)












Find the exact moment inside a video using dialogue memory or scene description.

🚀 Overview

Video Finder is a full-stack AI-powered video search system that allows users to locate specific moments inside a video using:

🔊 1) Audio Search (Dialogue-Based Search)

Upload a video

Extract audio

Transcribe speech (English / Tamil)

Search transcript using remembered dialogue

Get:

⏱ Timestamp (hh:mm:ss)

🎥 10-second video clip

🖼 2) Scene Search (Visual Semantic Search)

Upload a video

Sample frames (default: every 3 seconds)

Generate CLIP embeddings

Index using FAISS

Search using a natural language scene description

Get:

⏱ Timestamp

🎥 10-second clip

💡 Design Principle

Audio and Scene pipelines are completely independent.

✔ Scene users do NOT wait for transcription
✔ Audio users do NOT wait for frame embedding

Each upload creates its own job and status lifecycle.

🏗 Architecture
React Frontend
       ↓
FastAPI Backend
       ↓
 ┌───────────────────────────────┐
 │         Audio Pipeline        │
 │ FFmpeg → Whisper → Search     │
 └───────────────────────────────┘
               │
 ┌───────────────────────────────┐
 │         Scene Pipeline        │
 │ Frames → CLIP → FAISS Search  │
 └───────────────────────────────┘
               ↓
      10s Clip Generator (FFmpeg)

🛠 Tech Stack
Backend

FastAPI

SQLite (job tracking)

FFmpeg (audio extraction & clip cutting)

faster-whisper

Transformers (CLIP)

FAISS

PyTorch (CPU or CUDA)

Frontend

React + Vite

Axios

HTML5 Video Player

🔍 How It Works
🔊 Audio Search Pipeline

Upload video → job_id.mp4

Extract mono 16kHz WAV via FFmpeg

Transcribe using Whisper

Store transcript segments:

start

end

text

Search scoring:

Word overlap

Exact phrase bonus

Return best match:

Timestamp

10-second clip

🖼 Scene Search Pipeline

Upload video

Sample frames every 3 seconds

Generate CLIP embeddings (512-dim normalized vectors)

Build FAISS IndexFlatIP

Embed text query

Retrieve top-k nearest frames

Return best timestamp + clip

📁 Runtime Data (Ignored by Git)
backend/data/
  uploads/
  audio/
  transcriptions/
  index/
  clips/
  app.db

⚙️ Local Setup (Windows)
📦 Requirements

Python 3.10

Node 18+

FFmpeg installed & in PATH

ffmpeg -version

▶ Backend (CPU)
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir -r requirements\cpu.txt

python run.py


Backend:

http://localhost:8000

http://localhost:8000/docs

🚀 Backend (GPU Optional)
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir -r requirements\gpu-cu124.txt

python run.py


Verify GPU:

python -c "import torch; import torch.backends.cudnn as cudnn; print('Torch:', torch.__version__); print('GPU:', torch.cuda.is_available()); print('cuDNN:', cudnn.version())"

💻 Frontend
cd frontend
npm install
npm run dev


Frontend:

http://localhost:5173

🐳 Docker Setup
CPU Docker (Recommended)
docker compose up --build


Frontend:

http://localhost:5173


Backend:

http://localhost:8000/docs

GPU Docker (Advanced)

Requires NVIDIA Docker runtime.

docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build

📡 API Endpoints
Audio

POST /audio/videos

GET /audio/videos/{job_id}/status

POST /audio/videos/{job_id}/search

GET /audio/videos/{job_id}/clip?start=...&dur=10

Scene

POST /scene/videos

GET /scene/videos/{job_id}/status

POST /scene/videos/{job_id}/search

GET /scene/videos/{job_id}/clip?start=...&dur=10

🧠 Key Technical Highlights

Multimodal AI search (text ↔ video frames)

FAISS inner-product cosine similarity

GPU-accelerated embedding

Efficient frame sampling strategy

Separate asynchronous job pipelines

Production-style Docker setup

Windows CUDA DLL resolution handling

🛠 Troubleshooting
405 Method Not Allowed

Use Swagger:

http://localhost:8000/docs

206 Partial Content

Normal behavior for video streaming (HTTP range requests).

CUDA/cuDNN Error on Windows

Start backend via:

python run.py


This project patches NVIDIA DLL paths before importing torch.

FFmpeg Not Found

Install FFmpeg and add to PATH.

📈 Future Improvements

Temporal smoothing for scene ranking

Background task queue (Celery/Redis)

YouTube ingestion

Auto cleanup of large files

Model quantization support

WebSocket progress updates

📄 License

MIT License
