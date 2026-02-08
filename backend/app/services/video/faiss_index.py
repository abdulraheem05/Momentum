import json
from pathlib import Path
import numpy as np
import faiss


def build_index_ip(vectors: np.ndarray) -> faiss.Index:
    """
    Inner product index. If vectors are L2-normalized, IP == cosine similarity.
    vectors: [N, D] float32
    """
    n, d = vectors.shape
    index = faiss.IndexFlatIP(d)
    index.add(vectors)
    return index


def save_index(index: faiss.Index, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(path))


def load_index(path: Path) -> faiss.Index:
    return faiss.read_index(str(path))


def save_json(obj: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
