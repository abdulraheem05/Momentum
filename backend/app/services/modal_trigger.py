import modal

process_video = modal.Function.lookup(
    "momentum-worker",
    "process_video"
)


def trigger_worker(job_id, payload):
    process_video.spawn(job_id, payload)