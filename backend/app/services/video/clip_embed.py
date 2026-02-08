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
        _clip_processor = CLIPProcessor.from_pretrained(_MODEL_NAME)
        _clip_model.eval()
        _clip_model.to(_device)

    return _clip_model, _clip_processor, _device