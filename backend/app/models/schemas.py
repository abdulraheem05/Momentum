from pydantic import BaseModel
from typing import Optional


class UploadCompleteRequest(BaseModel):
    source_type: str
    blob_url: Optional[str] = None
    youtube_url: Optional[str] = None
    mode: str


class SceneSearchRequest(BaseModel):
    job_id: str
    query: str


class AudioSearchRequest(BaseModel):
    job_id: str
    query: str