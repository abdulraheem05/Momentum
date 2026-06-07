import re
from typing import Any, Dict, List

from app.youtube_utils import build_youtube_timestamp_url


STOP_WORDS = {
    "the", "a", "an", "and", "or", "but",
    "is", "are", "am", "was", "were",
    "to", "of", "in", "on", "at", "for", "with",
    "this", "that", "these", "those",
    "i", "you", "he", "she", "it", "we", "they",
}


def format_timestamp(seconds: float) -> str:
    total_seconds = int(seconds)

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    return f"{minutes:02d}:{secs:02d}"


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("’", "'").replace("`", "'")

    text = re.sub(r"\bi'm\b", "i am", text)
    text = re.sub(r"\bim\b", "i am", text)

    text = re.sub(r"\byou're\b", "you are", text)
    text = re.sub(r"\bwe're\b", "we are", text)
    text = re.sub(r"\bthey're\b", "they are", text)
    text = re.sub(r"\bhe's\b", "he is", text)
    text = re.sub(r"\bshe's\b", "she is", text)
    text = re.sub(r"\bit's\b", "it is", text)

    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def tokenize(text: str) -> List[str]:
    normalized = normalize_text(text)
    words = normalized.split()

    important_words = [
        word for word in words
        if word not in STOP_WORDS and len(word) > 1
    ]

    return important_words


def calculate_match_score(query: str, segment_text: str) -> float:
    normalized_query = normalize_text(query)
    normalized_segment = normalize_text(segment_text)

    if not normalized_query:
        return 0.0

    if normalized_query in normalized_segment:
        return 1.0

    query_words = tokenize(query)
    segment_words = set(tokenize(segment_text))

    if not query_words:
        return 0.0

    matched_words = [
        word for word in query_words
        if word in segment_words
    ]

    word_match_ratio = len(matched_words) / len(query_words)

    if word_match_ratio == 1.0:
        return 0.93

    return word_match_ratio


def search_dialogue_in_transcript(
    transcript_data: Dict[str, Any],
    query: str,
    max_results: int = 3,
) -> List[Dict[str, Any]]:
    clean_query = query.strip()

    if not clean_query:
        return []

    source_type = transcript_data.get("source_type", "youtube")
    youtube_id = transcript_data.get("youtube_id")
    media_blob_url = transcript_data.get("media_blob_url")

    segments = transcript_data.get("segments", [])

    scored_results = []

    for segment in segments:
        text = segment.get("text", "")
        start = float(segment.get("start", 0))

        score = calculate_match_score(clean_query, text)

        if score >= 0.5:
            result = {
                "timestamp": int(start),
                "timestamp_label": format_timestamp(start),
                "text": text,
                "score": round(score, 3),
                "source_type": source_type,
            }

            if source_type == "youtube" and youtube_id:
                result["youtube_url"] = build_youtube_timestamp_url(
                    youtube_id=youtube_id,
                    seconds=start,
                )
            else:
                result["media_blob_url"] = media_blob_url

            scored_results.append(result)

    scored_results.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return scored_results[:max_results]