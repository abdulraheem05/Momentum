import numpy as np
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
import torch

_MODEL_NAME = "openai/clip-vit-base-patch32"

_clip_model= None
_clip_processor = None
_device = None

def get_clip_model_and_processor():
    global _clip_model, _clip_processor, _device

    if _device is None:
        _device = "cuda" if torch.cuda.is_available() else "cpu"

    if _clip_model is None or _clip_processor is None:
        _clip_model = CLIPModel.from_pretrained(_MODEL_NAME)
        _clip_processor = CLIPProcessor.from_pretrained(_MODEL_NAME, use_fast=True)
        _clip_model.eval()
        _clip_model.to(_device)

    return _clip_model, _clip_processor, _device


@torch.inference_mode()
def embed_images_batched(
    image_paths: list[str],
    batch_size: int = 64
) -> np.ndarray:
    
    model, processor, device = get_clip_model_and_processor()

    all_vectors = []

    for i in range (0, len(image_paths), batch_size):
        batch_paths = image_paths[i:i+batch_size]
        images = [Image.open(p).convert("RGB") for p in batch_paths]

        inputs = processor(images=images, return_tensors="pt", padding=True)
        inputs = {k:v.to(device) for k,v in inputs.items()}

        feat = model.get_image_features(**inputs)
        feat = feat/ feat.norm(p=2, dim=-1, keepdim=True)

        all_vectors.append(feat.detach().float().cpu().numpy())

    return np.vstack(all_vectors).astype("float32")

@torch.inference_mode()
def embed_text(text: str) -> np.ndarray:
    """
    Returns normalized text embedding [D] float32
    """
    model, processor, device = get_clip_model_and_processor()

    inputs = processor(text=[text], return_tensors="pt", padding=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}

    feats = model.get_text_features(**inputs)
    feats = feats / feats.norm(p=2, dim=-1, keepdim=True)

    return feats[0].detach().float().cpu().numpy().astype("float32")