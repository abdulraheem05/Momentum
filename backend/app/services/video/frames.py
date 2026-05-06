import cv2
import os
from typing import Generator, List

TMP_DIR = "/tmp/momentum_frames"


# app/services/video/frames.py

def extract_frames_in_batches(video_path, job_id, batch_size=16, frame_interval=4.0):
    # Create a unique folder for this specific job
    job_dir = os.path.join(TMP_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    
    batch = []
    saved_count = 0
    
    # Calculate exact timestamps to extract
    import numpy as np
    timestamps = np.arange(0, duration, frame_interval)

    for ts in timestamps:
        frame_idx = int(ts * fps)
        # FAST SEEK: Jump directly to the frame instead of reading through the whole file
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret: break

        # RESIZE: CLIP only needs 224x224. This saves massive Disk I/O time.
        small_frame = cv2.resize(frame, (224, 224))
        
        file_path = os.path.join(job_dir, f"frame_{saved_count}.jpg")
        cv2.imwrite(file_path, small_frame)

        batch.append({"path": file_path, "timestamp": float(ts)})
        saved_count += 1

        if len(batch) == batch_size:
            yield batch
            batch = []

    if batch: yield batch
    cap.release()
    # Cleanup directory after generator is exhausted happens in scene_index.py