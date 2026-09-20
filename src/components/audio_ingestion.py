"""
VideoMind API — FastAPI backend for the video understanding pipeline.

Lightweight deployment version:
- Heavy pipeline imports remain lazy.
- Up to 2 users can process videos concurrently.
- Each job gets its own artifact directory.
- Old finished artifacts are cleaned when the same user starts a fresh job.
- Uploaded source files are deleted after successful audio chunking.
- QAPipeline remains available for completed-job Q&A.
- Timestamp and summary stages run sequentially to reduce peak memory.
- yt-dlp validation results are temporarily reused by the real download.
"""

from __future__ import annotations

import gc
import os
import shutil
import subprocess
import threading
import uuid

from typing import Optional

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException,
    Request,
)

from fastapi.responses import (
    FileResponse,
    JSONResponse,
)

from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.logger import logger


app = FastAPI(
    title="VideoMind API"
)


# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

STATIC_DIR = os.path.join(
    os.path.dirname(__file__),
    "static",
)

UPLOAD_DIR = os.path.join(
    "artifact",
    "uploads",
)

JOB_ARTIFACT_DIR = os.path.join(
    "artifact",
    "jobs",
)


os.makedirs(
    JOB_ARTIFACT_DIR,
    exist_ok=True,
)

os.makedirs(
    UPLOAD_DIR,
    exist_ok=True,
)


app.mount(
    "/static",
    StaticFiles(
        directory=STATIC_DIR
    ),
    name="static",
)


# --------------------------------------------------------------------------
# Concurrency
# --------------------------------------------------------------------------

# Allow two heavy pipelines simultaneously.
MAX_CONCURRENT_PIPELINES = 2

# Do not allow more than two jobs to be queued/running.
MAX_OPEN_JOBS = 2

PIPELINE_SEMAPHORE = (
    threading.BoundedSemaphore(
        MAX_CONCURRENT_PIPELINES
    )
)


# --------------------------------------------------------------------------
# Client identity
# --------------------------------------------------------------------------

CLIENT_COOKIE_NAME = (
    "videomind_client_id"
)


# Keep only two finished jobs globally.
# Per-client cleanup happens first, so normally
# each active user keeps their latest finished job.
MAX_FINISHED_JOBS = 2


# --------------------------------------------------------------------------
# Pipeline stage definitions
# --------------------------------------------------------------------------

STAGE_DEFS = [
    {
        "key": "ingestion",
        "label": "Ingest",
        "desc": "Pulling the audio track from the source.",
    },
    {
        "key": "transcription",
        "label": "Transcribe",
        "desc": "Listening to the audio, word by word, with exact timing.",
    },
    {
        "key": "text_processing",
        "label": "Structure",
        "desc": "Splitting the transcript into meaning-sized pieces.",
    },
    {
        "key": "timestamp",
        "label": "Chapters",
        "desc": "Finding where the topic actually changes — not just every N minutes.",
    },
    {
        "key": "summary",
        "label": "Summary",
        "desc": "Writing the TL;DR and checking its numbers against the transcript.",
    },
    {
        "key": "embedding",
        "label": "Index",
        "desc": "Making every moment searchable, so you can ask it anything.",
    },
]


# --------------------------------------------------------------------------
# In-memory job store
# --------------------------------------------------------------------------

JOBS: dict = {}

JOBS_LOCK = threading.Lock()


# --------------------------------------------------------------------------
# Client helpers
# --------------------------------------------------------------------------

def get_or_create_client_id(
    request: Request,
) -> tuple[str, bool]:
    """
    Return the browser/client id.

    Returns:
        (client_id, is_new)
    """

    existing_id = (
        request.cookies.get(
            CLIENT_COOKIE_NAME
        )
    )

    if existing_id:
        return (
            existing_id,
            False,
        )

    return (
        uuid.uuid4().hex,
        True,
    )


# --------------------------------------------------------------------------
# Artifact helpers
# --------------------------------------------------------------------------

def safe_artifact_path(
    path: str,
) -> bool:
    """
    Ensure a path is inside ./artifact.
    """

    try:

        artifact_base = os.path.abspath(
            "artifact"
        )

        target_path = os.path.abspath(
            path
        )

        return (
            os.path.commonpath(
                [
                    artifact_base,
                    target_path,
                ]
            )
            == artifact_base
        )

    except Exception:
        return False


def cleanup_job_resources(
    job: dict,
) -> None:
    """
    Remove all disk resources belonging to one job.
    """

    try:

        artifact_root = job.get(
            "artifact_root"
        )

        if artifact_root:

            artifact_root = os.path.abspath(
                artifact_root
            )

            if safe_artifact_path(
                artifact_root
            ):

                if os.path.exists(
                    artifact_root
                ):

                    shutil.rmtree(
                        artifact_root,
                        ignore_errors=True,
                    )

                    logger.info(
                        f"Deleted job artifacts: "
                        f"{artifact_root}"
                    )

        upload_dir = os.path.join(
            UPLOAD_DIR,
            job["id"],
        )

        if os.path.exists(
            upload_dir
        ):

            shutil.rmtree(
                upload_dir,
                ignore_errors=True,
            )

            logger.info(
                f"Deleted uploaded files: "
                f"{upload_dir}"
            )

    except Exception as e:

        logger.warning(
            f"Could not fully clean job "
            f"{job.get('id')}: {e}"
        )


def prune_finished_jobs_locked() -> list:
    """
    Keep only the newest finished/failed jobs.

    Caller must hold JOBS_LOCK.

    Returns:
        Jobs that were removed and should have
        their disk resources cleaned.
    """

    finished_jobs = [
        job
        for job in JOBS.values()
        if job["status"]
        in {
            "completed",
            "failed",
        }
    ]

    finished_jobs.sort(
        key=lambda job: job.get(
            "created_at",
            0,
        )
    )

    removed_jobs = []

    while (
        len(finished_jobs)
        > MAX_FINISHED_JOBS
    ):

        old_job = finished_jobs.pop(
            0
        )

        old_job_id = old_job["id"]

        removed = JOBS.pop(
            old_job_id,
            None,
        )

        if removed:

            removed["qa_pipeline"] = None
            removed["results"] = None

            removed_jobs.append(
                removed
            )

    return removed_jobs


def cleanup_previous_finished_jobs_for_client(
    client_id: str,
) -> None:
    """
    When a user starts a fresh job, remove that user's
    old finished/failed jobs.

    This prevents one user's new URL from deleting
    another user's artifacts.
    """

    removed_jobs = []

    with JOBS_LOCK:

        old_ids = [
            job_id
            for job_id, job in JOBS.items()
            if job.get("client_id")
            == client_id
            and job["status"]
            in {
                "completed",
                "failed",
            }
        ]

        for job_id in old_ids:

            old_job = JOBS.pop(
                job_id,
                None,
            )

            if old_job:

                old_job["qa_pipeline"] = None
                old_job["results"] = None

                removed_jobs.append(
                    old_job
                )

    for job in removed_jobs:
        cleanup_job_resources(
            job
        )


# --------------------------------------------------------------------------
# Job helpers
# --------------------------------------------------------------------------

def count_open_jobs_locked() -> int:
    """
    Caller must hold JOBS_LOCK.
    """

    return sum(
        1
        for job in JOBS.values()
        if job["status"]
        in {
            "queued",
            "running",
        }
    )


def has_open_job_for_client_locked(
    client_id: str,
) -> bool:
    """
    Caller must hold JOBS_LOCK.
    """

    return any(
        job.get("client_id")
        == client_id
        and job["status"]
        in {
            "queued",
            "running",
        }
        for job in JOBS.values()
    )


def new_job(
    source_type: str,
    source_label: str,
    client_id: str,
) -> str:
    """
    Create a fresh job entry.
    """

    job_id = uuid.uuid4().hex[:12]

    with JOBS_LOCK:

        JOBS[job_id] = {
            "id": job_id,

            "client_id": client_id,

            "source_type": source_type,

            "source_label": source_label,

            "status": "queued",

            "current_stage": None,

            "stages": {
                stage["key"]: "pending"
                for stage in STAGE_DEFS
            },

            "error": None,

            "warning": None,

            "video_id": None,

            "media_url": None,

            "artifact_root": None,

            "results": None,

            "qa_pipeline": None,
        }

    return job_id


def set_stage(
    job_id: str,
    key: str,
    status: str,
) -> None:
    """
    Update one stage's status.
    """

    with JOBS_LOCK:

        job = JOBS[job_id]

        job["stages"][key] = status

        if status == "running":

            job["current_stage"] = key

            job["status"] = "running"


def public_job_view(
    job: dict,
) -> dict:
    """
    Strip internal state before sending to frontend.
    """

    view = {
        key: value
        for key, value in job.items()
        if key
        not in {
            "qa_pipeline",
            "client_id",
            "artifact_root",
        }
    }

    if job.get(
        "results"
    ):

        view["results"] = {
            **job["results"],

            "qa_ready": (
                job.get(
                    "qa_pipeline"
                )
                is not None
            ),
        }

    return view


# --------------------------------------------------------------------------
# Pipeline artifact isolation
# --------------------------------------------------------------------------

def isolate_pipeline_artifacts(
    pipeline,
    job_id: str,
) -> str:
    """
    Move every config path currently pointing inside
    ./artifact/... into:

        ./artifact/jobs/<job_id>/...

    This is important because your logs showed shared
    paths such as:

        artifact/audio_ingestion/audio/input_audio.webm

    Two concurrent users cannot safely share those paths.
    """

    job_root = os.path.abspath(
        os.path.join(
            JOB_ARTIFACT_DIR,
            job_id,
        )
    )

    os.makedirs(
        job_root,
        exist_ok=True,
    )

    artifact_base = os.path.abspath(
        "artifact"
    )

    for attr_name, config in vars(
        pipeline
    ).items():

        if not (
            attr_name.endswith(
                "_config"
            )
            or "config" in attr_name.lower()
        ):
            continue

        if not hasattr(
            config,
            "__dict__",
        ):
            continue

        for key, value in vars(
            config
        ).items():

            if not isinstance(
                value,
                (str, os.PathLike),
            ):
                continue

            value_str = os.fspath(
                value
            )

            try:

                absolute_value = (
                    os.path.abspath(
                        value_str
                    )
                )

                if (
                    os.path.commonpath(
                        [
                            artifact_base,
                            absolute_value,
                        ]
                    )
                    != artifact_base
                ):
                    continue

            except Exception:
                continue

            relative_path = (
                os.path.relpath(
                    absolute_value,
                    artifact_base,
                )
            )

            new_path = os.path.join(
                job_root,
                relative_path,
            )

            setattr(
                config,
                key,
                new_path,
            )

            logger.info(
                f"Job {job_id}: isolated "
                f"{attr_name}.{key} -> {new_path}"
            )

    return job_root


# --------------------------------------------------------------------------
# Upload handling
# --------------------------------------------------------------------------

def extract_duration_from_ffmpeg_stderr(
    stderr: str,
) -> float:
    """
    Parse source duration from FFmpeg stderr.
    """

    import re

    match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+\.\d+)",
        stderr,
    )

    if not match:

        raise ValueError(
            "Could not determine media duration"
        )

    hours, minutes, seconds = (
        match.groups()
    )

    return (
        int(hours) * 3600
        + int(minutes) * 60
        + float(seconds)
    )


def ingest_uploaded_file(
    job_id: str,
    saved_path: str,
    original_filename: str,
    pipeline,
):
    """
    Process uploaded media.

    Optimization:
    - No full uploaded-video -> MP3 conversion.
    - FFmpeg chunks directly from the source file.
    - Original source is deleted after chunking.
    """

    from src.components.audio_ingestion import (
        AudioIngestion,
    )

    from src.entity.artifact_entity import (
        AudioIngestionArtifact,
    )

    from src.utils.main_utils import (
        save_json,
    )

    config = (
        pipeline.audio_ingestion_config
    )

    audio_ingestion = (
        AudioIngestion(
            audio_ingestion_config=config
        )
    )

    duration = (
        audio_ingestion.get_media_duration(
            saved_path
        )
    )

    audio_chunks_dir = (
        audio_ingestion.create_audio_chunks(
            saved_path
        )
    )

    audio_ingestion.cleanup_audio_file(
        saved_path
    )

    chunk_durations = (
        audio_ingestion.compute_chunk_durations(
            duration,
            config.chunk_duration,
        )
    )

    video_metadata = {
        "id": job_id,
        "title": original_filename,
        "description": None,
        "duration": duration,
        "upload_date": None,
        "uploader": "Uploaded file",
        "channel": None,
        "view_count": None,
        "like_count": None,
        "thumbnail": None,
        "webpage_url": None,
    }

    video_metadata_file_path = (
        save_json(
            video_metadata,
            config.video_metadata_file_path,
        )
    )

    return AudioIngestionArtifact(
        audio_file_path=saved_path,
        audio_chunks_dir=audio_chunks_dir,
        video_metadata_file_path=(
            video_metadata_file_path
        ),
        chunk_durations=chunk_durations,
    )


# --------------------------------------------------------------------------
# Background pipeline runner
# --------------------------------------------------------------------------

def run_job(
    job_id: str,
    source_type: str,
    source_value: str,
    original_filename: Optional[str] = None,
) -> None:
    """
    Run one complete VideoMind pipeline.

    Maximum two jobs execute concurrently.
    """

    pipeline = None

    PIPELINE_SEMAPHORE.acquire()

    try:

        logger.info(
            f"Pipeline slot acquired for job {job_id}"
        )

        from src.pipeline.video_pipeline import (
            VideoPipeline,
        )

        from src.pipeline.qa_pipeline import (
            QAPipeline,
        )

        from src.utils.main_utils import (
            load_json,
            format_timestamp,
        )

        # --------------------------------------------------------------
        # PIPELINE
        # --------------------------------------------------------------

        pipeline = VideoPipeline()

        # Give every job its own artifact tree.
        artifact_root = (
            isolate_pipeline_artifacts(
                pipeline,
                job_id,
            )
        )

        with JOBS_LOCK:

            if job_id in JOBS:

                JOBS[job_id][
                    "artifact_root"
                ] = artifact_root

        logger.info(
            f"Job {job_id} artifact root: "
            f"{artifact_root}"
        )

        # --------------------------------------------------------------
        # INGESTION
        # --------------------------------------------------------------

        set_stage(
            job_id,
            "ingestion",
            "running",
        )

        if source_type == "url":

            ingestion_artifact = (
                pipeline.start_audio_ingestion(
                    video_url=source_value
                )
            )

            video_meta = load_json(
                ingestion_artifact.video_metadata_file_path
            )

            with JOBS_LOCK:

                JOBS[job_id][
                    "video_id"
                ] = video_meta.get(
                    "id"
                )

        else:

            ingestion_artifact = (
                ingest_uploaded_file(
                    job_id=job_id,
                    saved_path=source_value,
                    original_filename=original_filename,
                    pipeline=pipeline,
                )
            )

            video_meta = load_json(
                ingestion_artifact.video_metadata_file_path
            )

            with JOBS_LOCK:

                JOBS[job_id][
                    "media_url"
                ] = (
                    f"/media/{job_id}/"
                    f"{os.path.basename(source_value)}"
                )

        set_stage(
            job_id,
            "ingestion",
            "done",
        )

        # --------------------------------------------------------------
        # TRANSCRIPTION
        # --------------------------------------------------------------

        set_stage(
            job_id,
            "transcription",
            "running",
        )

        transcription_artifact = (
            pipeline.start_audio_transcription(
                ingestion_artifact
            )
        )

        set_stage(
            job_id,
            "transcription",
            "done",
        )

        # --------------------------------------------------------------
        # TEXT PROCESSING
        # --------------------------------------------------------------

        set_stage(
            job_id,
            "text_processing",
            "running",
        )

        text_processing_artifact = (
            pipeline.start_text_processing(
                transcription_artifact
            )
        )

        set_stage(
            job_id,
            "text_processing",
            "done",
        )

        # --------------------------------------------------------------
        # TIMESTAMP + SUMMARY
        # --------------------------------------------------------------

        set_stage(
            job_id,
            "timestamp",
            "running",
        )

        set_stage(
            job_id,
            "summary",
            "running",
        )

        timestamp_artifact = None
        summary_artifact = None

        stage_errors = {}

        try:

            timestamp_artifact = (
                pipeline.start_timestamp_generation(
                    transcription_artifact
                )
            )

            set_stage(
                job_id,
                "timestamp",
                "done",
            )

        except Exception as e:

            stage_errors[
                "timestamp"
            ] = str(e)

            set_stage(
                job_id,
                "timestamp",
                "error",
            )

        try:

            summary_artifact = (
                pipeline.start_summary_generation(
                    transcription_artifact
                )
            )

            set_stage(
                job_id,
                "summary",
                "done",
            )

        except Exception as e:

            stage_errors[
                "summary"
            ] = str(e)

            set_stage(
                job_id,
                "summary",
                "error",
            )

        if stage_errors:

            logger.warning(
                "Non-critical stage failures: "
                + ", ".join(
                    stage_errors.keys()
                )
            )

        # --------------------------------------------------------------
        # EMBEDDING
        # --------------------------------------------------------------

        set_stage(
            job_id,
            "embedding",
            "running",
        )

        embedding_artifact = (
            pipeline.start_embedding_indexing(
                text_processing_artifact
            )
        )

        set_stage(
            job_id,
            "embedding",
            "done",
        )

        # --------------------------------------------------------------
        # WARNING
        # --------------------------------------------------------------

        if stage_errors:

            with JOBS_LOCK:

                JOBS[job_id][
                    "warning"
                ] = (
                    "Some stages failed, but the "
                    "pipeline completed. Q&A is still available."
                )

        # --------------------------------------------------------------
        # QA PIPELINE
        # --------------------------------------------------------------

        qa_pipeline = (
            QAPipeline(
                embedding_artifact=(
                    embedding_artifact
                )
            )
        )

        # --------------------------------------------------------------
        # RESULTS
        # --------------------------------------------------------------

        timestamps = []

        if timestamp_artifact is not None:

            timestamps = load_json(
                timestamp_artifact.timestamp_file_path
            )[
                "topics"
            ]

        summary = {}

        if summary_artifact is not None:

            summary = load_json(
                summary_artifact.summary_file_path
            )

        segments = load_json(
            transcription_artifact.transcript_file_path
        )[
            "segments"
        ]

        transcript = [
            {
                "start_time": format_timestamp(
                    seg["start"]
                ),
                "end_time": format_timestamp(
                    seg["end"]
                ),
                "text": seg["text"],
            }
            for seg in segments
        ]

        # --------------------------------------------------------------
        # COMPLETE
        # --------------------------------------------------------------

        with JOBS_LOCK:

            job = JOBS[job_id]

            job[
                "qa_pipeline"
            ] = qa_pipeline

            job[
                "status"
            ] = "completed"

            job[
                "current_stage"
            ] = None

            job[
                "results"
            ] = {
                "metadata": video_meta,
                "summary": summary,
                "timestamps": timestamps,
                "transcript": transcript,
            }

        logger.info(
            f"Job {job_id} completed successfully"
        )

        # --------------------------------------------------------------
        # RELEASE TEMPORARY REFERENCES
        # --------------------------------------------------------------

        pipeline = None

        ingestion_artifact = None
        transcription_artifact = None
        text_processing_artifact = None
        timestamp_artifact = None
        summary_artifact = None
        embedding_artifact = None

        gc.collect()

    except Exception as e:

        logger.exception(
            f"Job {job_id} failed"
        )

        with JOBS_LOCK:

            if job_id in JOBS:

                job = JOBS[job_id]

                if job["status"] != "failed":

                    job[
                        "status"
                    ] = "failed"

                    job[
                        "error"
                    ] = str(e)

                current = job.get(
                    "current_stage"
                )

                if (
                    current
                    and job["stages"].get(
                        current
                    )
                    == "running"
                ):

                    job[
                        "stages"
                    ][current] = "error"

    finally:

        pipeline = None

        try:

            PIPELINE_SEMAPHORE.release()

            logger.info(
                f"Pipeline slot released for job {job_id}"
            )

        except Exception as e:

            logger.warning(
                f"Could not release pipeline slot: {e}"
            )

        # Global finished-job cleanup.
        removed_jobs = []

        with JOBS_LOCK:

            removed_jobs = (
                prune_finished_jobs_locked()
            )

        for removed_job in removed_jobs:

            cleanup_job_resources(
                removed_job
            )

        gc.collect()


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.get("/")
def index(
    request: Request,
):
    """
    Serve frontend and establish client identity.
    """

    response = FileResponse(
        os.path.join(
            STATIC_DIR,
            "index.html",
        )
    )

    client_id = request.cookies.get(
        CLIENT_COOKIE_NAME
    )

    if not client_id:

        client_id = uuid.uuid4().hex

        response.set_cookie(
            key=CLIENT_COOKIE_NAME,
            value=client_id,
            httponly=True,
            samesite="lax",
            secure=(
                request.url.scheme
                == "https"
            ),
        )

    return response


@app.get("/api/config")
def get_config():
    """
    Return stage definitions.
    """

    return {
        "stages": STAGE_DEFS
    }


# --------------------------------------------------------------------------
# URL validation
# --------------------------------------------------------------------------

class ValidateRequest(
    BaseModel
):
    url: str


@app.post("/api/validate")
def validate_url(
    payload: ValidateRequest,
):
    """
    Pre-flight YouTube extraction.

    The extracted info is cached so the real
    download can reuse it.
    """

    try:

        import yt_dlp

        opts = {
            "quiet": False,
            "no_warnings": False,
            "verbose": True,
            "noplaylist": True,
            "skip_download": True,

            "cookiefile": os.getenv(
                "YOUTUBE_COOKIE_FILE",
                "/tmp/cookies.txt",
            ),

            "js_runtimes": {
                "node": {}
            },

            "extractor_args": {
                "youtube": {
                    "player_client": [
                        "mweb",
                        "web_safari",
                    ]
                },

                "youtubepot-bgutilhttp": {
                    "base_url": [
                        "http://127.0.0.1:4416"
                    ]
                },
            },
        }

        with yt_dlp.YoutubeDL(
            opts
        ) as ydl:

            info = ydl.extract_info(
                payload.url,
                download=False,
            )

        if info is None:

            raise ValueError(
                "Could not read this link"
            )

        # Cache only after successful extraction.
        from src.components.audio_ingestion import (
            cache_prefetched_info,
        )

        cache_prefetched_info(
            payload.url,
            info,
        )

        return {
            "valid": True,
            "title": info.get(
                "title"
            ),
            "duration": info.get(
                "duration"
            ),
            "thumbnail": info.get(
                "thumbnail"
            ),
            "channel": (
                info.get(
                    "channel"
                )
                or info.get(
                    "uploader"
                )
            ),
            "video_id": info.get(
                "id"
            ),
        }

    except Exception as e:

        logger.exception(
            "URL validation failed"
        )

        return JSONResponse(
            status_code=400,
            content={
                "valid": False,
                "error": str(e),
            },
        )


# --------------------------------------------------------------------------
# Create job
# --------------------------------------------------------------------------

@app.post("/api/jobs")
def create_job(
    request: Request,
    url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    """
    Start processing a video.

    Maximum:
        2 open jobs globally.
        1 open job per browser/client.
    """

    if not url and not file:

        raise HTTPException(
            status_code=400,
            detail=(
                "Provide a video URL or upload "
                "a video file"
            ),
        )

    client_id, is_new_client = (
        get_or_create_client_id(
            request
        )
    )

    with JOBS_LOCK:

        if has_open_job_for_client_locked(
            client_id
        ):

            raise HTTPException(
                status_code=409,
                detail=(
                    "Your previous video is still "
                    "processing — wait for it to finish."
                ),
            )

        if (
            count_open_jobs_locked()
            >= MAX_OPEN_JOBS
        ):

            raise HTTPException(
                status_code=409,
                detail=(
                    "Two videos are already "
                    "processing. Please try again "
                    "after one finishes."
                ),
            )

    try:

        # --------------------------------------------------------------
        # Clean this user's old finished state
        # AFTER the new request is accepted.
        # --------------------------------------------------------------

        cleanup_previous_finished_jobs_for_client(
            client_id
        )

        # --------------------------------------------------------------
        # URL
        # --------------------------------------------------------------

        if url:

            job_id = new_job(
                "url",
                url,
                client_id,
            )

            threading.Thread(
                target=run_job,
                args=(
                    job_id,
                    "url",
                    url,
                ),
                daemon=True,
            ).start()

            response = JSONResponse(
                {
                    "job_id": job_id
                }
            )

            if is_new_client:

                response.set_cookie(
                    key=CLIENT_COOKIE_NAME,
                    value=client_id,
                    httponly=True,
                    samesite="lax",
                    secure=(
                        request.url.scheme
                        == "https"
                    ),
                )

            return response

        # --------------------------------------------------------------
        # UPLOAD
        # --------------------------------------------------------------

        filename = os.path.basename(
            file.filename or "uploaded_video"
        )

        job_id = new_job(
            "upload",
            filename,
            client_id,
        )

        job_dir = os.path.join(
            UPLOAD_DIR,
            job_id,
        )

        os.makedirs(
            job_dir,
            exist_ok=True,
        )

        saved_path = os.path.join(
            job_dir,
            filename,
        )

        with open(
            saved_path,
            "wb",
        ) as out:

            shutil.copyfileobj(
                file.file,
                out,
            )

        threading.Thread(
            target=run_job,
            args=(
                job_id,
                "upload",
                saved_path,
                filename,
            ),
            daemon=True,
        ).start()

        response = JSONResponse(
            {
                "job_id": job_id
            }
        )

        if is_new_client:

            response.set_cookie(
                key=CLIENT_COOKIE_NAME,
                value=client_id,
                httponly=True,
                samesite="lax",
                secure=(
                    request.url.scheme
                    == "https"
                ),
            )

        return response

    except HTTPException:
        raise

    except Exception as e:

        logger.exception(
            "Could not start processing"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                f"Couldn't start processing: "
                f"{e}"
            ),
        )

    finally:

        if file is not None:

            try:
                file.file.close()
            except Exception:
                pass


# --------------------------------------------------------------------------
# Job status
# --------------------------------------------------------------------------

@app.get("/api/jobs/{job_id}")
def get_job(
    job_id: str,
):
    """
    Poll job status and return results once completed.
    """

    with JOBS_LOCK:

        job = JOBS.get(
            job_id
        )

        if job is None:

            raise HTTPException(
                status_code=404,
                detail="Job not found",
            )

        return public_job_view(
            job
        )


# --------------------------------------------------------------------------
# Q&A
# --------------------------------------------------------------------------

class AskRequest(
    BaseModel
):
    question: str


@app.post(
    "/api/jobs/{job_id}/ask"
)
def ask_question(
    job_id: str,
    payload: AskRequest,
):
    """
    Answer a question about a completed video.
    """

    with JOBS_LOCK:

        job = JOBS.get(
            job_id
        )

        if job is None:

            raise HTTPException(
                status_code=404,
                detail="Job not found",
            )

        qa_pipeline = job.get(
            "qa_pipeline"
        )

    if qa_pipeline is None:

        raise HTTPException(
            status_code=409,
            detail=(
                "This video isn't ready "
                "for questions yet"
            ),
        )

    try:

        return qa_pipeline.ask(
            payload.question
        )

    except Exception as e:

        from src.exception import (
            MyException,
        )

        if isinstance(
            e,
            MyException,
        ):

            raise HTTPException(
                status_code=500,
                detail=str(e),
            )

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# --------------------------------------------------------------------------
# Uploaded media
# --------------------------------------------------------------------------

@app.get(
    "/media/{job_id}/{filename}"
)
def get_media(
    job_id: str,
    filename: str,
):
    """
    Serve uploaded media.
    """

    safe_filename = os.path.basename(
        filename
    )

    file_path = os.path.join(
        UPLOAD_DIR,
        job_id,
        safe_filename,
    )

    if not os.path.exists(
        file_path
    ):

        raise HTTPException(
            status_code=404,
            detail="File not found",
        )

    return FileResponse(
        file_path
    )
