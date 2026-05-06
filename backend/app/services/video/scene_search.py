from app.services.vector_store import query
from app.services.video.clip_embed import get_text_embedding


def search_scene(video_id: str, query_text: str, top_k: int = 3):
    vector = get_text_embedding(query_text)

    results = query(vector, top_k=top_k)

    hits = []

    for match in results["matches"]:
        if match["metadata"]["video_id"] != video_id:
            continue

        hits.append({
            "start": match["metadata"]["timestamp"],
            "score": match["score"]
        })

    return hits