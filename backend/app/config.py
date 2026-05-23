import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    MODAL_PROCESS_URL: str = os.getenv("MODAL_PROCESS_URL", "")


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