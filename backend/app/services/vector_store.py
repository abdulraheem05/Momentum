from pinecone import Pinecone
import os

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX"))

def upsert_vector(id, vector, metadata):
    index.upsert(
        vectors=[
            {
                "id": id,
                "values": vector,
                "metadata": metadata
            }
        ]
    )

def query_vector(vector, top_k, job_id):
    return index.query(
        vector=vector,
        top_k=top_k,
        filter={"job_id": job_id},
        include_metadata=True
    )