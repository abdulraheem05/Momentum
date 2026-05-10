import os

from pinecone import Pinecone
from transformers import (
    CLIPProcessor,
    CLIPModel
)
from PIL import Image
import torch


model = CLIPModel.from_pretrained(
    "openai/clip-vit-base-patch32"
)

processor = CLIPProcessor.from_pretrained(
    "openai/clip-vit-base-patch32"
)


def embed_text(query):

    inputs = processor(
        text=[query],
        return_tensors="pt",
        padding=True
    )

    with torch.no_grad():
        features = model.get_text_features(**inputs)

    return features[0].tolist()


def search_scenes(job_id, query):

    vector = embed_text(query)

    pc = Pinecone(
        api_key=os.getenv("PINECONE_API_KEY")
    )

    index = pc.Index(
        os.getenv("PINECONE_INDEX")
    )

    results = index.query(
        vector=vector,
        top_k=3,
        include_metadata=True,
        filter={
            "job_id": {"$eq": job_id}
        }
    )

    return [
        {
            "timestamp": match["metadata"]["timestamp"],
            "thumbnail_url": match["metadata"]["thumbnail_url"],
            "score": match["score"]
        }
        for match in results["matches"]
    ]