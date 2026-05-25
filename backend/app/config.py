import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    MODAL_AUDIO_PROCESS_URL: str = os.getenv("MODAL_AUDIO_PROCESS_URL", "")
    MODAL_VIDEO_PROCESS_URL: str = os.getenv("MODAL_VIDEO_PROCESS_URL", "")

    AZURE_STORAGE_CONNECTION_STRING: str = os.getenv(
        "AZURE_STORAGE_CONNECTION_STRING", ""
    )
    AZURE_TRANSCRIPTS_CONTAINER: str = os.getenv(
        "AZURE_TRANSCRIPTS_CONTAINER", "transcripts"
    )

    PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
    PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "")


settings = Settings()


def validate_required_env() -> None:
    missing = []

    if not settings.SUPABASE_URL:
        missing.append("SUPABASE_URL")

    if not settings.SUPABASE_KEY:
        missing.append("SUPABASE_KEY")

    if missing:
        raise RuntimeError(
            "Missing required environment variables: " + ", ".join(missing)
        )