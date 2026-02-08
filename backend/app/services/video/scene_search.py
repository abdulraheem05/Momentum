from app.core.paths import INDEX_FRAMES_DIR
from app.services.video.faiss_index import load_index, load_json
from app.services.video.clip_embed import embed_text

def search_scene(
        video_id: str,
        query: str,
        top_k: int = 3
) -> list[dict]:
    
    index_path = INDEX_FRAMES_DIR/f"{video_id}.faiss"
    json_path = INDEX_FRAMES_DIR/f"{video_id}.json"

    if not index_path or not json_path:
        raise RuntimeError("Scene index not found")
    
    index = load_index(index_path)
    json = load_json(json_path)
    timestamps = json["timestamps"]

    
