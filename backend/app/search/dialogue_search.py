from typing import Any, Dict, List

from app.youtube_utils import build_youtube_timestamp_url


def format_timestamp(seconds: float) -> str:
    total_seconds = int(seconds)

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    return f"{minutes:02d}:{secs:02d}"


def search_dialogue_in_transcript(
    transcript_data: Dict[str, Any],
    query: str,
    max_results: int = 3,
) -> List[Dict[str, Any]]:
    """
    Performs simple phrase matching using Python's `in`.

    No semantic search.
    No embeddings.
    """

    clean_query = query.strip().lower()

    if not clean_query:
        return []

    youtube_id = transcript_data["youtube_id"]
    segments = transcript_data.get("segments", [])

    results: List[Dict[str, Any]] = []

    for segment in segments:
        text = segment.get("text", "")
        start = float(segment.get("start", 0))

        if clean_query in text.lower():
            results.append(
                {
                    "timestamp": int(start),
                    "timestamp_label": format_timestamp(start),
                    "text": text,
                    "youtube_url": build_youtube_timestamp_url(
                        youtube_id=youtube_id,
                        seconds=start,
                    ),
                }
            )

        if len(results) == max_results:
            break

    return results