import re


YOUTUBE_ID_REGEX_PATTERNS = [
    r"(?:v=)([a-zA-Z0-9_-]{11})",
    r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
    r"(?:shorts/)([a-zA-Z0-9_-]{11})",
    r"(?:embed/)([a-zA-Z0-9_-]{11})",
]


def extract_youtube_id(url: str) -> str:
    """
    Extracts the 11-character YouTube video ID from common YouTube URL formats.
    """

    if not url:
        raise ValueError("YouTube URL is required.")

    for pattern in YOUTUBE_ID_REGEX_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    raise ValueError("Invalid YouTube URL. Could not extract video ID.")


def build_youtube_timestamp_url(youtube_id: str, seconds: float) -> str:
    seconds_int = int(seconds)
    return f"https://www.youtube.com/watch?v={youtube_id}&t={seconds_int}s"