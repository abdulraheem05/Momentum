from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2")

def embed_text(text: str):
    return model.encode(text).tolist()

def embed_image(image_np: np.ndarray):
    return model.encode(image_np).tolist()