import os
import jwt
from fastapi import Header, HTTPException
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")


async def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing token")

    token = authorization.replace("Bearer ", "")

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated"
        )

        return payload

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")