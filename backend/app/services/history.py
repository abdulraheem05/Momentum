import uuid

from app.db.supabase import supabase


def save_history(
    user_id,
    job_id,
    query,
    search_type,
    clip_url,
    thumbnail_url,
    timestamp
):

    (
        supabase
        .table("search_history")
        .insert({
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "job_id": job_id,
            "query": query,
            "search_type": search_type,
            "clip_url": clip_url,
            "thumbnail_url": thumbnail_url,
            "timestamp": timestamp
        })
        .execute()
    )


def get_history(user_id):

    response = (
        supabase
        .table("search_history")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )

    return response.data