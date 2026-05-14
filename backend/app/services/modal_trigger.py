import modal

process_video = modal.Function.from_name(
    "momentum-worker",
    "process_video"
)


def trigger_worker(job_id, payload):
    process_video.spawn(job_id, payload)