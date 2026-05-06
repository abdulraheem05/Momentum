from pinecone import Pinecone
import os

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX"))


def upsert_batch(video_id: str, embeddings_batch: list):
    vectors = []

    for item in embeddings_batch:
        vector_id = f"{video_id}_{item['timestamp']}"

        vectors.append({
            "id": vector_id,
            "values": item["embedding"].tolist(),
            "metadata": {
                "video_id": video_id,
                "timestamp": item["timestamp"]
            }
        })

    index.upsert(vectors=vectors)


def query(vector, top_k=5):
    return index.query(
        vector=vector,
        top_k=top_k,
        include_metadata=True
    )