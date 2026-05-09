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

