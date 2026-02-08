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

    vectors = embed_images_batched(image_paths, batch_size=batch_size)

    index = build_index_ip(vectors)

    index_path = INDEX_FRAMES_DIR/f"{video_id}.fiass"
    json_path = INDEX_FRAMES_DIR/f"{video_id}.json"

    timestamps = [i * every_n_seconds for i in range(len(image_paths))]

    save_index(index, index_path)

    save_json({
        "every_n_seconds": every_n_seconds,
        "resize_width": resize_width,
        "count": len(image_paths),
        "timestamps": timestamps
    }, json_path)

    shutil.rmtree(tmp_dir, ignore_errors=True)