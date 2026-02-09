# 🎬 Momentum
### Audio Search + Scene Search (FastAPI • React • CLIP • FAISS • Whisper)

[![Python](https://img.shields.io/badge/Python-3.10-blue.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688.svg)]()
[![React](https://img.shields.io/badge/React-Frontend-61DAFB.svg)]()
[![PyTorch](https://img.shields.io/badge/PyTorch-2.6+-EE4C2C.svg)]()
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()

> Find the exact moment inside a video using **dialogue memory** (speech-to-text) or **scene description** (visual semantic search).

---

## 🚀 Overview

**Video Finder** is a full-stack AI-powered video search system. It allows users to locate specific moments within a video using two independent, high-performance pipelines.

### 🔊 1. Audio Search (Dialogue-Based)
- **Transcription:** Uses **Whisper** to convert speech (English/Tamil) into time-stamped text.
- **Search:** Search the transcript using remembered dialogue.
- **Output:** Returns the exact timestamp and a generated **10-second video clip** of the moment.

### 🖼 2. Scene Search (Visual Semantic Search)
- **Indexing:** Samples frames every 3 seconds and generates **CLIP** embeddings.
- **Vector Search:** Uses **FAISS** for rapid similarity matching.
- **Output:** Search using natural language descriptions (e.g., "a person walking on the beach") to get the best matching timestamp and clip.

---

## 🏗 Architecture



```text
React Frontend (UI)
        ↓
FastAPI Backend (Orchestrator)
        ↓
┌───────────────────────────────┐      ┌───────────────────────────────┐
│        Audio Pipeline         │      │        Scene Pipeline         │
│ FFmpeg → Whisper → Search     │      │ Frames → CLIP → FAISS Search  │
└───────────────────────────────┘      └───────────────────────────────┘
                │                                      │
                └───────▶ 10s Clip Generator ◀─────────┘
                          (via FFmpeg)

```

---

## 🛠 Tech Stack

### Backend

* **FastAPI:** High-performance web framework.
* **SQLite:** Job and metadata tracking.
* **FFmpeg:** Audio extraction and dynamic video clipping.
* **AI Models:** `faster-whisper` (Speech), `Transformers/CLIP` (Vision).
* **Vector DB:** **FAISS** (Facebook AI Similarity Search).
* **PyTorch:** Backend engine for model inference (CPU/CUDA).

### Frontend

* **React + Vite:** Modern, fast frontend build tool.
* **Axios:** API communication.
* **HTML5 Video Player:** Native streaming support.

---

## ⚙️ Local Setup (Windows)

### 📦 Requirements

* Python 3.10.x
* Node 18+
* **FFmpeg** installed and added to your system `PATH`.

### ▶ Backend Setup

```bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1

# Upgrade pip and install requirements
python -m pip install --upgrade pip setuptools wheel

# FOR CPU:
pip install --no-cache-dir -r requirements\cpu.txt

# FOR GPU (Optional - CUDA 12.4):
pip install --no-cache-dir -r requirements\gpu-cu124.txt

# Start the server
python run.py

```

### 💻 Frontend Setup

```bash
cd frontend
npm install
npm run dev

```

* **Frontend:** `http://localhost:5173`
* **API Docs:** `http://localhost:8000/docs`

---

## 🐳 Docker Setup

### CPU Version (Recommended for testing)

```bash
docker compose up --build

```

### GPU Version (Requires NVIDIA Docker runtime)

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build

```

---

## 📁 Runtime Data Structure

*Note: These folders are created automatically and are ignored by `.gitignore`.*

```text
backend/data/
  ├── uploads/        # Original video files
  ├── audio/          # Extracted audio tracks
  ├── transcriptions/ # JSON segment data
  ├── index/          # FAISS vector indices
  ├── clips/          # Generated 10s result segments
  └── app.db          # Job tracking database

```

---

## 🛠 Troubleshooting

* **CUDA/cuDNN Error:** If on Windows, always start the backend via `python run.py`. It contains a custom patch to fix NVIDIA DLL pathing issues.
* **405 Method Not Allowed:** Double-check your URL in the frontend or use the Swagger UI (`/docs`) to verify the route.
* **FFmpeg Not Found:** Run `ffmpeg -version` in your terminal. If it fails, you must install FFmpeg and add the `bin` folder to your Environment Variables.
* **206 Partial Content:** This is expected! It means the server is successfully streaming video chunks to your browser.

---
