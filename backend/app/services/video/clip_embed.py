from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import torch
import numpy as np
from typing import List

device = "cuda" if torch.cuda.is_available() else "cpu"

model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(device)
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")


def get_batch_embeddings(frame_batch: List[dict]) -> List[dict]:
    images = [Image.open(f["path"]).convert("RGB") for f in frame_batch]

    inputs = processor(images=images, return_tensors="pt", padding=True).to(device)

    with torch.no_grad():
        outputs = model.get_image_features(**inputs)

    embeddings = outputs / outputs.norm(p=2, dim=-1, keepdim=True)
    embeddings = embeddings.cpu().numpy()

    results = []
    for i, item in enumerate(frame_batch):
        results.append({
            "embedding": embeddings[i],
            "timestamp": item["timestamp"],
            "path": item["path"]
        })

    return results

def get_text_embedding(text: str):
    inputs = processor(text=[text], return_tensors="pt", padding=True).to(device)

    with torch.no_grad():
        outputs = model.get_text_features(**inputs)

    embedding = outputs / outputs.norm(p=2, dim=-1, keepdim=True)
    return embedding.cpu().numpy()[0]