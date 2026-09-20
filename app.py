"""
VideoMind API — FastAPI backend for the video understanding pipeline.

Drop this file at the project root (alongside `src/`, `scripts/`, `dvc.yaml`)
and put the contents of `static/` in a `static/` folder next to it.

Run with:
    pip install fastapi "uvicorn[standard]" python-multipart
    uvicorn app:app --reload

This is a "for now" API, not a production task queue: it runs one video at
a time (a global lock) and keeps job state in memory. For real concurrent
users, swap the in-memory JOBS dict + threading.Thread for Celery/RQ and a
real datastore — the pipeline calls themselves don't need to change.
"""

from __future__ import annotations
import sys
import os
import shutil
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.utils.main_utils import load_json, save_json, format_timestamp
from src.exception import MyException
from src.logger import logger

app = FastAPI(title="VideoMind API")


STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
UPLOAD_DIR = os.path.join("artifact", "uploads")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --------------------------------------------------------------------------
# Pipeline stage definitions — single source of truth, served to the
# frontend via /api/config so the UI never hardcodes stage copy.
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
PIPELINE_LOCK = threading.Lock()
BUSY = {"active": False}


def new_job(source_type: str, source_label: str) -> str:
    """Create and register a fresh job entry, returning its id."""

    job_id = uuid.uuid4().hex[:12]

    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "source_type": source_type,
            "source_label": source_label,
            "status": "queued",
            "current_stage": None,
            "stages": {stage["key"]: "pending" for stage in STAGE_DEFS},
            "error": None,
            "warning": None,
            "video_id": None,
            "media_url": None,
            "results": None,
            "qa_pipeline": None,
        }

    return job_id


def set_stage(job_id: str, key: str, status: str) -> None:
    """Update one stage's status and, if it's now running, mark it current."""

    with JOBS_LOCK:
        job = JOBS[job_id]

        job["stages"][key] = status

        if status == "running":
            job["current_stage"] = key
            job["status"] = "running"


def set_failed(job_id: str, key: Optional[str], message: str) -> None:
    """Mark a job and the stage it failed on as failed."""

    with JOBS_LOCK:
        job = JOBS[job_id]

        if key:
            job["stages"][key] = "error"

        job["status"] = "failed"
        job["error"] = message

    logger.error(f"Job {job_id} failed at stage {key}: {message}")


def public_job_view(job: dict) -> dict:
    """Strip internal objects before sending to the client."""

    view = {k: v for k, v in job.items() if k != "qa_pipeline"}

    if job.get("results"):
        view["results"] = {
            **job["results"],
            "qa_ready": job.get("qa_pipeline") is not None,
        }

    return view


# --------------------------------------------------------------------------
# Upload handling
# --------------------------------------------------------------------------


def extract_duration_from_ffmpeg_stderr(stderr: str) -> float:
    """
    Parse the source duration ffmpeg already prints to stderr during
    conversion, instead of running a separate ffprobe call to get it.
    """
    import re

    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", stderr)
    if not match:
        raise ValueError("Could not determine audio duration from ffmpeg output")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def ingest_uploaded_file(
    job_id: str, saved_path: str, original_filename: str, pipeline
):
    """
    Build an AudioIngestionArtifact from an uploaded file.

    Heavy pipeline-related imports are intentionally performed here,
    only when an uploaded video is actually processed.
    """
    from src.components.audio_ingestion import AudioIngestion
    from src.entity.artifact_entity import AudioIngestionArtifact

    config = pipeline.audio_ingestion_config
    audio_ingestion = AudioIngestion(audio_ingestion_config=config)

    output_dir = os.path.dirname(config.audio_path)
    os.makedirs(output_dir, exist_ok=True)

    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            saved_path,
            "-vn",
            "-acodec",
            "libmp3lame",
            "-q:a",
            "2",
            config.audio_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    duration = extract_duration_from_ffmpeg_stderr(result.stderr)
    audio_chunks_dir = audio_ingestion.create_audio_chunks(config.audio_path)
    chunk_durations = audio_ingestion.compute_chunk_durations(
        duration, config.chunk_duration
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

    video_metadata_file_path = save_json(
        video_metadata,
        config.video_metadata_file_path,
    )

    return AudioIngestionArtifact(
        audio_file_path=config.audio_path,
        audio_chunks_dir=audio_chunks_dir,
        video_metadata_file_path=video_metadata_file_path,
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
    Run the full pipeline for one job.

    Heavy ML-related imports happen here rather than when FastAPI starts.
    """

    # Lazy imports
    from src.pipeline.video_pipeline import VideoPipeline
    from src.pipeline.qa_pipeline import QAPipeline

    with PIPELINE_LOCK:

        try:

            pipeline = VideoPipeline()

            # --------------------------------------------------------------
            # INGESTION
            # --------------------------------------------------------------

            set_stage(
                job_id,
                "ingestion",
                "running",
            )

            if source_type == "url":

                ingestion_artifact = pipeline.start_audio_ingestion(
                    video_url=source_value
                )

                video_meta = load_json(ingestion_artifact.video_metadata_file_path)

                with JOBS_LOCK:
                    JOBS[job_id]["video_id"] = video_meta.get("id")

            else:

                ingestion_artifact = ingest_uploaded_file(
                    job_id,
                    source_value,
                    original_filename,
                    pipeline,
                )

                video_meta = load_json(ingestion_artifact.video_metadata_file_path)

                with JOBS_LOCK:
                    JOBS[job_id]["media_url"] = (
                        f"/media/{job_id}/" f"{os.path.basename(source_value)}"
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

            transcription_artifact = pipeline.start_audio_transcription(
                ingestion_artifact
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

            text_processing_artifact = pipeline.start_text_processing(
                transcription_artifact
            )

            set_stage(
                job_id,
                "text_processing",
                "done",
            )

            # --------------------------------------------------------------
            # CHAPTERS + SUMMARY
            # --------------------------------------------------------------

            set_stage(job_id, "timestamp", "running")
            set_stage(job_id, "summary", "running")

            timestamp_artifact = None
            summary_artifact = None
            stage_errors = {}

            with ThreadPoolExecutor(max_workers=2) as executor:
                future_timestamp = executor.submit(
                    pipeline.start_timestamp_generation, transcription_artifact
                )
                future_summary = executor.submit(
                    pipeline.start_summary_generation, transcription_artifact
                )

                for future, key in (
                    (future_timestamp, "timestamp"),
                    (future_summary, "summary"),
                ):
                    try:
                        result = future.result()
                        if key == "timestamp":
                            timestamp_artifact = result
                        else:
                            summary_artifact = result
                        set_stage(job_id, key, "done")
                    except Exception as e:
                        stage_errors[key] = str(e)
                        set_stage(job_id, key, "error")

                if stage_errors:
                    logger.warning(
                        "Non-critical stage failures: " + ", ".join(stage_errors.keys())
                    )

            # --------------------------------------------------------------
            # EMBEDDING
            # --------------------------------------------------------------

            set_stage(
                job_id,
                "embedding",
                "running",
            )

            embedding_artifact = pipeline.start_embedding_indexing(
                text_processing_artifact
            )

            set_stage(
                job_id,
                "embedding",
                "done",
            )
            if stage_errors:
                with JOBS_LOCK:
                    JOBS[job_id]["warning"] = (
                        "Some stages failed, but the pipeline completed. "
                        "Q&A is still available."
                    )
            # --------------------------------------------------------------
            # QA PIPELINE
            # --------------------------------------------------------------

            qa_pipeline = QAPipeline(embedding_artifact=embedding_artifact)

            # --------------------------------------------------------------
            # LOAD RESULTS
            # --------------------------------------------------------------

            timestamps = []

            if timestamp_artifact is not None:
                timestamps = load_json(timestamp_artifact.timestamp_file_path)["topics"]

            summary = {}

            if summary_artifact is not None:
                summary = load_json(summary_artifact.summary_file_path)

            segments = load_json(transcription_artifact.transcript_file_path)[
                "segments"
            ]

            transcript = [
                {
                    "start_time": format_timestamp(seg["start"]),
                    "end_time": format_timestamp(seg["end"]),
                    "text": seg["text"],
                }
                for seg in segments
            ]

            # --------------------------------------------------------------
            # COMPLETE JOB
            # --------------------------------------------------------------

            with JOBS_LOCK:

                job = JOBS[job_id]

                job["qa_pipeline"] = qa_pipeline

                job["status"] = "completed"

                job["current_stage"] = None

                job["results"] = {
                    "metadata": video_meta,
                    "summary": summary,
                    "timestamps": timestamps,
                    "transcript": transcript,
                }

            logger.info(f"Job {job_id} completed successfully")

        except Exception as e:
            with JOBS_LOCK:
                job = JOBS[job_id]

                if job["status"] != "failed":
                    job["status"] = "failed"
                    job["error"] = str(e)

                current = job.get("current_stage")

                if current and job["stages"].get(current) == "running":
                    job["stages"][current] = "error"

            logger.error(f"Job {job_id} failed: {e}")

        finally:
            with JOBS_LOCK:
                BUSY["active"] = False


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@app.get("/")
def index():
    """Serve the single-page app."""

    return FileResponse(
        os.path.join(
            STATIC_DIR,
            "index.html",
        )
    )


@app.get("/api/config")
def get_config():
    """
    Return stage definitions so the frontend never
    hardcodes pipeline copy.
    """

    return {"stages": STAGE_DEFS}


# --------------------------------------------------------------------------
# URL validation
# --------------------------------------------------------------------------


class ValidateRequest(BaseModel):
    url: str


@app.post("/api/validate")
def validate_url(payload: ValidateRequest):
    """
    Quick pre-flight probe of a video URL.
    """

    try:
        import os
        import yt_dlp

        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "format": "ba/b",
            "cookiefile": os.getenv("YOUTUBE_COOKIE_FILE", "/tmp/cookies.txt"),
            "extractor_args": {
                "youtubepot-bgutilhttp": {"base_url": ["http://127.0.0.1:4416"]},
            },
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                payload.url,
                download=False,
            )

        if info is None:
            raise ValueError("Could not read this link")

        return {
            "valid": True,
            "title": info.get("title"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "channel": (info.get("channel") or info.get("uploader")),
            "video_id": info.get("id"),
        }

    except Exception as e:
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
    url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    """Start processing a video."""

    if not url and not file:

        raise HTTPException(
            status_code=400,
            detail="Provide a video URL or upload a video file",
        )

    with JOBS_LOCK:

        if BUSY["active"]:

            raise HTTPException(
                status_code=409,
                detail=("Already processing a video — " "wait for it to finish"),
            )

        BUSY["active"] = True

    try:

        # --------------------------------------------------------------
        # URL
        # --------------------------------------------------------------

        if url:

            job_id = new_job(
                "url",
                url,
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

            return {"job_id": job_id}

        # --------------------------------------------------------------
        # UPLOADED FILE
        # --------------------------------------------------------------

        job_id = new_job(
            "upload",
            file.filename,
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
            file.filename,
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
                file.filename,
            ),
            daemon=True,
        ).start()

        return {"job_id": job_id}

    except Exception as e:

        with JOBS_LOCK:
            BUSY["active"] = False

        raise HTTPException(
            status_code=500,
            detail=f"Couldn't start processing: {e}",
        )


# --------------------------------------------------------------------------
# Job status
# --------------------------------------------------------------------------


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    """
    Poll a job's current status and return results
    once completed.
    """

    with JOBS_LOCK:

        job = JOBS.get(job_id)

        if job is None:

            raise HTTPException(
                status_code=404,
                detail="Job not found",
            )

        return public_job_view(job)


# --------------------------------------------------------------------------
# Q&A
# --------------------------------------------------------------------------


class AskRequest(BaseModel):
    question: str


@app.post("/api/jobs/{job_id}/ask")
def ask_question(
    job_id: str,
    payload: AskRequest,
):
    """Answer a question about a completed video."""

    with JOBS_LOCK:

        job = JOBS.get(job_id)

        if job is None:

            raise HTTPException(
                status_code=404,
                detail="Job not found",
            )

        qa_pipeline = job.get("qa_pipeline")

    if qa_pipeline is None:

        raise HTTPException(
            status_code=409,
            detail=("This video isn't ready " "for questions yet"),
        )

    try:

        return qa_pipeline.ask(payload.question)

    except MyException as e:

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# --------------------------------------------------------------------------
# Uploaded media
# --------------------------------------------------------------------------


@app.get("/media/{job_id}/{filename}")
def get_media(
    job_id: str,
    filename: str,
):
    """Serve an uploaded file back for in-browser playback."""

    file_path = os.path.join(
        UPLOAD_DIR,
        job_id,
        filename,
    )

    if not os.path.exists(file_path):

        raise HTTPException(
            status_code=404,
            detail="File not found",
        )

    return FileResponse(file_path)
