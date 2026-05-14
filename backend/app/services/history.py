import uuid

from app.db.supabase import supabase


def save_history(
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
            "job_id": job_id,
            "query": query,
            "search_type": search_type,
            "clip_url": clip_url,
            "thumbnail_url": thumbnail_url,
            "timestamp": timestamp
        })
        .execute()
    )


def get_history():

    response = (
        supabase
        .table("search_history")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )

    return response.data