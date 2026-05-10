import os
import json
import requests

from azure.storage.blob import BlobServiceClient
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np


model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)


def search_audio(job_id, query):

    blob_service = BlobServiceClient.from_connection_string(
        os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    )

    blob_client = blob_service.get_blob_client(
        container = os.getenv("AZURE_RESULTS_CONTAINER"),
        blob=f"{job_id}.json"
    )

    transcript = json.loads(
        blob_client.download_blob().readall()
    )

    query_embedding = model.encode([query])[0]

    scored = []

    for item in transcript["segments"]:

        text_embedding = model.encode(
            [item["text"]]
        )[0]

        similarity = cosine_similarity(
            [query_embedding],
            [text_embedding]
        )[0][0]

        scored.append({
            "timestamp": item["start"],
            "text": item["text"],
            "score": float(similarity)
        })

    scored.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return scored[:3]