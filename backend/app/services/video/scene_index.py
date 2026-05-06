import os
from app.services.video.frames import extract_frames_in_batches
from app.services.video.clip_embed import get_batch_embeddings
from app.services.vector_store import upsert_batch


# app/services/video/scene_index.py

def process_video(video_path: str, video_id: str):
    # Pass video_id here to use the job-specific directory
    for batch in extract_frames_in_batches(video_path, video_id, batch_size=16):
        embeddings_batch = get_batch_embeddings(batch)
        upsert_batch(video_id, embeddings_batch)
        
        # Cleanup batch files immediately
        for item in batch:
            if os.path.exists(item["path"]):
                os.remove(item["path"])
    
    # Final cleanup of the job directory
    job_dir = os.path.join("/tmp/momentum_frames", video_id)
    if os.path.exists(job_dir):
        import shutil
        shutil.rmtree(job_dir)