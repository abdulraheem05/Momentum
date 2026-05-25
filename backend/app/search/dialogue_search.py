import re
from typing import Any, Dict, List

from app.youtube_utils import build_youtube_timestamp_url


STOP_WORDS = {
    "the", "a", "an", "and", "or", "but",
    "is", "are", "was", "were",
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
    """
    Lowercase text and remove punctuation.
    """

    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def tokenize(text: str) -> List[str]:
    """
    Converts text into searchable words.
    Removes very common words.
    """

    normalized = normalize_text(text)

    words = normalized.split()

    important_words = [
        word for word in words
        if word not in STOP_WORDS and len(word) > 1
    ]

    return important_words


def calculate_match_score(query: str, segment_text: str) -> float:
    """
    Returns a flexible score between 0 and 1.

    Higher score = better match.
    """

    normalized_query = normalize_text(query)
    normalized_segment = normalize_text(segment_text)

    if not normalized_query:
        return 0.0

    # 1. Best case: exact phrase appears
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

    # 2. If all important words are present, strong match
    if word_match_ratio == 1.0:
        return 0.93

    # 3. Partial match
    return word_match_ratio


def search_dialogue_in_transcript(
    transcript_data: Dict[str, Any],
    query: str,
    max_results: int = 3,
) -> List[Dict[str, Any]]:
    """
    Flexible dialogue search.

    It supports:
    - exact phrase matching
    - missing middle words
    - partial word matching

    No semantic embeddings used.
    """

    clean_query = query.strip()

    if not clean_query:
        return []

    youtube_id = transcript_data["youtube_id"]
    segments = transcript_data.get("segments", [])

    scored_results = []

    for segment in segments:
        text = segment.get("text", "")
        start = float(segment.get("start", 0))

        score = calculate_match_score(clean_query, text)

        # Tune this threshold.
        # 0.6 means at least around 60% of important query words should match.
        if score >= 0.6:
            scored_results.append(
                {
                    "timestamp": int(start),
                    "timestamp_label": format_timestamp(start),
                    "text": text,
                    "youtube_url": build_youtube_timestamp_url(
                        youtube_id=youtube_id,
                        seconds=start,
                    ),
                    "score": round(score, 3),
                }
            )

    scored_results.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return scored_results[:max_results]