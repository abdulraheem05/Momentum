from supabase import create_client, Client
from app.config import settings, validate_required_env

validate_required_env()

supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_KEY
)