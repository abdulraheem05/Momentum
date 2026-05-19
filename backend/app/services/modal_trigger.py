import modal


process_video = modal.Function.from_name(
    "momentum-worker",
    "process_video"
)

search_scenes_modal = modal.Function.from_name(
    "momentum-worker",
    "search_scenes"
)

search_audio_modal = modal.Function.from_name(
    "momentum-worker",
    "search_audio"
)


async def trigger_worker(job_id, payload):
    await process_video.spawn.aio(job_id, payload)


async def run_scene_search(job_id, query):
    return await search_scenes_modal.remote.aio(
        job_id,
        query,
        5
    )


async def run_audio_search(job_id, query):
    return await search_audio_modal.remote.aio(
        job_id,
        query,
        5
    )