from datetime import date
from app.db.supabase import supabase
from fastapi import HTTPException

MAX_DAILY_USAGE = 5


async def check_quota(user_id):
    response = (
        supabase
        .table("users")
        .select("*")
        .eq("id", user_id)
        .execute()
    )

    if not response.data:
        return

    user = response.data[0]

    if str(user["last_reset_date"]) != str(date.today()):
        (
            supabase
            .table("users")
            .update({
                "daily_usage_count": 0,
                "last_reset_date": str(date.today())
            })
            .eq("id", user_id)
            .execute()
        )

        user["daily_usage_count"] = 0

    if user["daily_usage_count"] >= MAX_DAILY_USAGE:
        raise HTTPException(
            status_code=429,
            detail="Daily limit reached"
        )


async def increment_usage(user_id):
    response = (
        supabase
        .table("users")
        .select("daily_usage_count")
        .eq("id", user_id)
        .execute()
    )

    count = response.data[0]["daily_usage_count"]

    (
        supabase
        .table("users")
        .update({
            "daily_usage_count": count + 1
        })
        .eq("id", user_id)
        .execute()
    )