from typing import Any, Dict, List

import numpy as np
import torch
from pinecone import Pinecone
from transformers import CLIPModel, CLIPProcessor

from app.config import settings


_clip_model = None
_clip_processor = None
_pinecone_index = None


def get_clip_model_and_processor():
    global _clip_model, _clip_processor

    if _clip_model is not None and _clip_processor is not None:
        return _clip_model, _clip_processor

    print("[CLIP] Loading CLIP model in backend...")

    model_name = "openai/clip-vit-base-patch32"

    _clip_model = CLIPModel.from_pretrained(model_name)
    _clip_processor = CLIPProcessor.from_pretrained(model_name)

    _clip_model.eval()

    print("[CLIP] Backend CLIP model loaded.")

    return _clip_model, _clip_processor


def warmup_clip_model() -> None:
    model, processor = get_clip_model_and_processor()

    inputs = processor(
        text=["warmup"],
        return_tensors="pt",
        padding=True,
        truncation=True,
    )

    with torch.no_grad():
        text_outputs = model.text_model(
            input_ids=inputs.input_ids,
            attention_mask=inputs.attention_mask,
        )

        pooled_output = text_outputs.pooler_output
        _ = model.text_projection(pooled_output)

    print("[CLIP] Backend CLIP warmup complete.")


def normalize_vector(values):
    array = np.array(values, dtype="float32").reshape(-1)

    if array.shape[0] != 512:
        raise ValueError(
            f"CLIP text embedding dimension is wrong. Expected 512, got {array.shape[0]}"
        )

    norm = np.linalg.norm(array)

    if norm == 0:
        return array.tolist()

    return (array / norm).tolist()


def embed_text_query(query: str) -> List[float]:
    model, processor = get_clip_model_and_processor()

    inputs = processor(
        text=[query],
        return_tensors="pt",
        padding=True,
        truncation=True,
    )

    with torch.no_grad():
        text_outputs = model.text_model(
            input_ids=inputs.input_ids,
            attention_mask=inputs.attention_mask,
        )

        pooled_output = text_outputs.pooler_output
        text_features = model.text_projection(pooled_output)

    vector = text_features.squeeze(0).detach().cpu().numpy()

    return normalize_vector(vector)


def get_pinecone_index():
    global _pinecone_index

    if _pinecone_index is not None:
        return _pinecone_index

    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    _pinecone_index = pc.Index(settings.PINECONE_INDEX_NAME)

    return _pinecone_index


def search_visual_scenes_backend(
    job_id: str,
    namespace: str,
    query: str,
    top_k: int = 3,
) -> Dict[str, Any]:
    query_vector = embed_text_query(query)

    index = get_pinecone_index()

    search_response = index.query(
        vector=query_vector,
        top_k=top_k,
        namespace=namespace,
        include_metadata=True,
        filter={
            "job_id": {"$eq": job_id}
        },
    )

    matches = search_response.get("matches", [])

    results = []

    for match in matches:
        metadata = match.get("metadata", {})

        results.append({
            "score": match.get("score"),
            "timestamp": metadata.get("timestamp"),
            "timestamp_label": metadata.get("timestamp_label"),
            "youtube_url": metadata.get("youtube_url"),
            "media_blob_url": metadata.get("media_blob_url"),
            "source_type": metadata.get("source_type", "youtube"),
            "scene_index": metadata.get("scene_index"),
            "scene_start": metadata.get("scene_start"),
            "scene_end": metadata.get("scene_end"),
        })

    return {
        "query": query,
        "count": len(results),
        "results": results,
    }