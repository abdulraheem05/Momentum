import shutil
from pathlib import Path

from app.core.paths import FRAMES_TMP_DIR, INDEX_FRAMES_DIR
from app.services.video.frames import extract_frames
from app.services.video.clip_embed import embed_images_batched
from app.services.video.faiss_index import build_index_ip, save_index, save_json

def build_scene_index(
        video_id: str,
        video_path: str,
        every_n_seconds: int,
        resize_width: int = 320,
        batch_size: int = 64
) -> None:
    
    tmp_dir = FRAMES_TMP_DIR / video_id

    extract_frames(
        video_path=video_path,
        frame_out=tmp_dir,
        every_n_sec=every_n_seconds,
        width=resize_width
    )

    image_paths = sorted([str(p) for p in tmp_dir.glob("frame_*.jpg")])

    embed_images_batched(image_paths, batch_size=batch_size)
