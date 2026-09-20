import gc
import os
import shutil
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yt_dlp

from src.exception import MyException
from src.logger import logger

load_dotenv()

app = FastAPI(title="VideoMind")

app.mount("/static", StaticFiles(directory="static"), name="static")


# ============================================================
# GLOBAL STATE
# ============================================================

JOBS = {}
ACTIVE_JOB_ID = None

JOB_LOCK = threading.Lock()

# Keep only the currently active job in memory.
MAX_COMPLETED_JOBS = 1


# ============================================================
# REQUEST MODELS
# ============================================================


class URLRequest(BaseModel):
    url: str


class AskRequest(BaseModel):
    question: str


# ============================================================
# HELPERS
# ============================================================


def sanitize_filename(filename: str) -> str:
    filename = os.path.basename(filename)
    filename = filename.replace("\x00", "")
    return filename or "uploaded_video"


def safe_artifact_path(path: str) -> bool:
    try:
        artifact_base = os.path.abspath("artifact")
        target_path = os.path.abspath(path)

        return os.path.commonpath([artifact_base, target_path]) == artifact_base
    except Exception:
        return False


def cleanup_job_artifacts(job: dict) -> None:
    """
    Delete all artifacts belonging to an old job.

    Safety:
    - Only deletes paths inside ./artifact
    - Never deletes arbitrary filesystem paths
    """
    try:
        artifact_root = job.get("artifact_root")

        if not artifact_root:
            return

        artifact_root = os.path.abspath(artifact_root)

        if not safe_artifact_path(artifact_root):
            logger.warning(f"Skipping unsafe artifact cleanup: {artifact_root}")
            return

        if os.path.exists(artifact_root):
            shutil.rmtree(artifact_root)
            logger.info(f"Deleted previous job artifacts: {artifact_root}")

    except Exception as e:
        logger.warning(f"Could not delete previous job artifacts: {e}")


def cleanup_old_job_memory() -> None:
    """
    Remove old job objects from in-memory JOBS.

    This does NOT delete the active job.
    """
    global ACTIVE_JOB_ID

    with JOB_LOCK:
        active_id = ACTIVE_JOB_ID

        removable = [
            job_id
            for job_id, job in JOBS.items()
            if job_id != active_id and job.get("status") in {"completed", "failed"}
        ]

        if len(removable) > MAX_COMPLETED_JOBS:
            for job_id in removable[:-MAX_COMPLETED_JOBS]:
                JOBS.pop(job_id, None)


def public_job_view(job: dict) -> dict:
    """
    Never expose internal objects such as QAPipeline.
    """
    if not job:
        return {}

    return {
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "url": job.get("url"),
        "filename": job.get("filename"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "current_stage": job.get("current_stage"),
        "progress": job.get("progress", 0),
        "error": job.get("error"),
        "results": job.get("results", {}),
        "media_url": job.get("media_url"),
    }


def update_job(job_id: str, **updates) -> None:
    with JOB_LOCK:
        if job_id not in JOBS:
            return

        JOBS[job_id].update(
            updates,
            updated_at=datetime.utcnow().isoformat(),
        )


def get_job(job_id: str) -> dict:
    with JOB_LOCK:
        return JOBS.get(job_id)


def get_artifact_root_from_pipeline(
    video_pipeline,
    job_id: str,
) -> str | None:
    """
    Try to obtain the pipeline's artifact root.

    Different versions of VideoPipeline may expose artifact
    information differently, so we check the common locations.
    """
    candidates = []

    for attr_name in (
        "artifact_root",
        "artifact_dir",
        "artifact_path",
    ):
        value = getattr(video_pipeline, attr_name, None)
        if value:
            candidates.append(value)

    config = getattr(video_pipeline, "config", None)

    if config:
        for attr_name in (
            "artifact_root",
            "artifact_dir",
            "artifact_path",
        ):
            value = getattr(config, attr_name, None)
            if value:
                candidates.append(value)

    # Find the newest artifact directory if pipeline does not directly expose the path.
    if os.path.exists("artifact"):
        try:
            directories = [
                os.path.join("artifact", item)
                for item in os.listdir("artifact")
                if os.path.isdir(os.path.join("artifact", item))
            ]

            if directories:
                directories.sort(
                    key=os.path.getmtime,
                    reverse=True,
                )
                candidates.append(directories[0])

        except Exception:
            pass

    for candidate in candidates:
        try:
            candidate = os.path.abspath(str(candidate))

            if safe_artifact_path(candidate):
                return candidate

        except Exception:
            continue

    return None


# ============================================================
# YOUTUBE VALIDATION
# DO NOT CHANGE THIS YT-DLP CONFIG
# ============================================================


def validate_youtube_url(video_url: str) -> dict:
    try:
        logger.info(f"Validating YouTube URL: {video_url}")

        ydl_opts = {
            "quiet": False,
            "no_warnings": False,
            "verbose": True,
            "noplaylist": True,
            "cookiefile": os.getenv(
                "YOUTUBE_COOKIE_FILE",
                "cookies.txt",
            ),
            "extractor_args": {
                "youtube": {"player_client": ["mweb", "web_safari"]},
                "youtubepot-bgutilhttp": {"base_url": ["http://127.0.0.1:4416"]},
            },
            "js_runtimes": {"node": {}},
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                video_url,
                download=False,
            )

        if info is None:
            raise ValueError("Could not retrieve video information")

        return {
            "valid": True,
            "title": info.get("title"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "webpage_url": info.get("webpage_url", video_url),
        }

    except yt_dlp.utils.DownloadError as e:
        logger.exception("YouTube validation failed")
        raise MyException(e, sys) from e

    except Exception as e:
        logger.exception("YouTube validation failed")
        raise MyException(e, sys) from e


# ============================================================
# PIPELINE
# ============================================================


def run_job(job_id: str) -> None:
    """
    Execute the complete VideoMind pipeline.

    QAPipeline is intentionally NOT kept inside JOBS.
    """
    try:
        update_job(
            job_id,
            status="processing",
            current_stage="initializing",
            progress=2,
        )

        job = get_job(job_id)

        if not job:
            logger.warning(f"Job {job_id} no longer exists")
            return

        video_url = job["url"]
        uploaded_file_path = job.get("source_file_path")

        logger.info(f"Starting VideoMind pipeline for job: {job_id}")

        from src.pipeline.video_pipeline import VideoPipeline

        video_pipeline = VideoPipeline()

        update_job(
            job_id,
            current_stage="video_processing",
            progress=5,
        )

        # ----------------------------------------------------
        # RUN MAIN VIDEO PIPELINE
        # ----------------------------------------------------

        if uploaded_file_path:
            pipeline_result = video_pipeline.run(uploaded_file_path)
        else:
            pipeline_result = video_pipeline.run(video_url)

        logger.info(f"VideoPipeline completed for job: {job_id}")

        # ----------------------------------------------------
        # SAVE ARTIFACT ROOT
        # ----------------------------------------------------

        artifact_root = get_artifact_root_from_pipeline(
            video_pipeline,
            job_id,
        )

        if artifact_root:
            update_job(
                job_id,
                artifact_root=artifact_root,
            )

        # ----------------------------------------------------
        # RELEASE VIDEO PIPELINE
        # ----------------------------------------------------

        del video_pipeline
        gc.collect()

        # ----------------------------------------------------
        # PIPELINE RESULT EXTRACTION
        # ----------------------------------------------------

        transcript_file_path = None
        embedding_artifact = None
        media_file_path = None

        if pipeline_result is not None:

            if isinstance(pipeline_result, dict):
                transcript_file_path = pipeline_result.get("transcript_file_path")

                embedding_artifact = pipeline_result.get("embedding_artifact")

                media_file_path = pipeline_result.get("media_file_path")

            else:
                transcript_file_path = getattr(
                    pipeline_result,
                    "transcript_file_path",
                    None,
                )

                embedding_artifact = getattr(
                    pipeline_result,
                    "embedding_artifact",
                    None,
                )

                media_file_path = getattr(
                    pipeline_result,
                    "media_file_path",
                    None,
                )

        if transcript_file_path:
            update_job(
                job_id,
                transcript_file_path=transcript_file_path,
            )

        if embedding_artifact:
            update_job(
                job_id,
                embedding_artifact=embedding_artifact,
            )

        if media_file_path:
            update_job(
                job_id,
                media_file_path=media_file_path,
            )

        # ----------------------------------------------------
        # TIMESTAMP + SUMMARY
        # ----------------------------------------------------

        update_job(
            job_id,
            current_stage="generating_results",
            progress=90,
        )

        transcript_data = None

        if transcript_file_path and os.path.exists(transcript_file_path):
            try:
                import json

                with open(
                    transcript_file_path,
                    "r",
                    encoding="utf-8",
                ) as file:
                    transcript_data = json.load(file)

            except Exception as e:
                logger.warning(f"Could not load transcript: {e}")

        timestamp_result = None
        summary_result = None

        # Keep these imports lazy.
        try:
            from src.components.timestamp_generator import (
                TimestampGenerator,
            )
        except Exception:
            TimestampGenerator = None

        try:
            from src.components.summary_generator import (
                SummaryGenerator,
            )
        except Exception:
            SummaryGenerator = None

        # ----------------------------------------------------
        # GENERATE TIMESTAMPS
        # ----------------------------------------------------

        if TimestampGenerator and transcript_data:

            try:
                timestamp_generator = TimestampGenerator()

                if isinstance(transcript_data, dict):
                    segments = transcript_data.get(
                        "segments",
                        [],
                    )
                else:
                    segments = transcript_data

                timestamp_result = timestamp_generator.generate(segments)

                del timestamp_generator
                gc.collect()

            except Exception as e:
                logger.warning(f"Timestamp generation failed: {e}")

        # ----------------------------------------------------
        # GENERATE SUMMARY
        # ----------------------------------------------------

        if SummaryGenerator and transcript_data:

            try:
                summary_generator = SummaryGenerator()

                if isinstance(transcript_data, dict):
                    segments = transcript_data.get(
                        "segments",
                        [],
                    )
                else:
                    segments = transcript_data

                summary_result = summary_generator.generate(segments)

                del summary_generator
                gc.collect()

            except Exception as e:
                logger.warning(f"Summary generation failed: {e}")

        # ----------------------------------------------------
        # SAVE RESULTS
        # ----------------------------------------------------

        update_job(
            job_id,
            results={
                "summary": summary_result,
                "timestamps": timestamp_result,
            },
            status="completed",
            current_stage="completed",
            progress=100,
        )

        logger.info(f"Job completed successfully: {job_id}")

    except Exception as e:
        logger.exception(f"Job failed: {job_id}")

        update_job(
            job_id,
            status="failed",
            current_stage="failed",
            progress=100,
            error=str(e),
        )

    finally:
        gc.collect()
        cleanup_old_job_memory()


# ============================================================
# FRONTEND
# ============================================================


@app.get("/")
def index():
    return FileResponse("static/index.html")


# ============================================================
# YOUTUBE VALIDATION
# ============================================================


@app.post("/api/validate")
def validate_url(request: URLRequest):
    try:
        video_url = request.url.strip()

        if not video_url:
            raise HTTPException(
                status_code=400,
                detail="URL is required",
            )

        result = validate_youtube_url(video_url)

        return result

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("URL validation endpoint failed")

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


# ============================================================
# CREATE JOB FROM URL
# ============================================================


@app.post("/api/jobs")
def create_url_job(request: URLRequest):
    global ACTIVE_JOB_ID

    try:
        video_url = request.url.strip()

        if not video_url:
            raise HTTPException(
                status_code=400,
                detail="URL is required",
            )

        # ----------------------------------------------------
        # STEP 1: VALIDATE NEW URL FIRST
        # Old job remains fully alive if validation fails.
        # ----------------------------------------------------

        validation = validate_youtube_url(video_url)

        # ----------------------------------------------------
        # STEP 2: CREATE NEW JOB
        # ----------------------------------------------------

        new_job_id = str(uuid.uuid4())

        new_job = {
            "job_id": new_job_id,
            "status": "queued",
            "url": video_url,
            "filename": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "current_stage": "queued",
            "progress": 0,
            "error": None,
            "artifact_root": None,
            "transcript_file_path": None,
            "embedding_artifact": None,
            "media_file_path": None,
            "source_file_path": None,
            "media_url": None,
            "results": {
                "summary": None,
                "timestamps": None,
            },
        }

        # ----------------------------------------------------
        # STEP 3: ADD NEW JOB FIRST
        # ----------------------------------------------------

        with JOB_LOCK:
            old_job_id = ACTIVE_JOB_ID
            old_job = JOBS.get(old_job_id)

            JOBS[new_job_id] = new_job

            ACTIVE_JOB_ID = new_job_id

        logger.info(f"Created new job: {new_job_id}")

        # ----------------------------------------------------
        # STEP 4: ONLY AFTER NEW JOB EXISTS, DELETE OLD JOB ARTIFACTS
        # ----------------------------------------------------

        if old_job and old_job_id != new_job_id:

            logger.info(f"Cleaning artifacts for old job: {old_job_id}")

            cleanup_job_artifacts(old_job)

            with JOB_LOCK:
                JOBS.pop(old_job_id, None)

        # ----------------------------------------------------
        # STEP 5: RETURN NEW JOB
        # ----------------------------------------------------

        response = public_job_view(JOBS[new_job_id])

        response["validation"] = validation

        return response

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("Could not create URL job")

        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


# ============================================================
# CREATE JOB FROM UPLOAD
# ============================================================


@app.post("/api/jobs/upload")
async def create_upload_job(file: UploadFile = File(...)):
    global ACTIVE_JOB_ID

    try:
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="Filename is missing",
            )

        filename = sanitize_filename(file.filename)

        upload_dir = os.path.abspath("artifact/uploads")

        os.makedirs(
            upload_dir,
            exist_ok=True,
        )

        file_path = os.path.join(
            upload_dir,
            filename,
        )

        # Prevent accidental overwrite collisions.
        if os.path.exists(file_path):

            stem, ext = os.path.splitext(filename)

            file_path = os.path.join(
                upload_dir,
                f"{stem}_{uuid.uuid4().hex[:8]}{ext}",
            )

        with open(
            file_path,
            "wb",
        ) as destination:

            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                destination.write(chunk)

        new_job_id = str(uuid.uuid4())

        new_job = {
            "job_id": new_job_id,
            "status": "queued",
            "url": None,
            "filename": os.path.basename(file_path),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "current_stage": "queued",
            "progress": 0,
            "error": None,
            "artifact_root": None,
            "transcript_file_path": None,
            "embedding_artifact": None,
            "media_file_path": file_path,
            "source_file_path": file_path,
            "media_url": f"/api/jobs/{new_job_id}/media",
            "results": {
                "summary": None,
                "timestamps": None,
            },
        }

        with JOB_LOCK:
            old_job_id = ACTIVE_JOB_ID
            old_job = JOBS.get(old_job_id)

            JOBS[new_job_id] = new_job

            ACTIVE_JOB_ID = new_job_id

        logger.info(f"Created upload job: {new_job_id}")

        if old_job and old_job_id != new_job_id:

            cleanup_job_artifacts(old_job)

            with JOB_LOCK:
                JOBS.pop(old_job_id, None)

        threading.Thread(
            target=run_job,
            args=(new_job_id,),
            daemon=True,
        ).start()

        return public_job_view(new_job)

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("Could not create upload job")

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )

    finally:
        try:
            await file.close()
        except Exception:
            pass


# ============================================================
# START URL JOB PIPELINE
# ============================================================


@app.post("/api/jobs/{job_id}/start")
def start_job(job_id: str):
    job = get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    if job.get("status") not in {
        "queued",
        "pending",
    }:
        return public_job_view(job)

    update_job(
        job_id,
        status="starting",
        current_stage="starting",
        progress=1,
    )

    threading.Thread(
        target=run_job,
        args=(job_id,),
        daemon=True,
    ).start()

    return public_job_view(get_job(job_id))


# ============================================================
# JOB STATUS
# ============================================================


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):

    job = get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return public_job_view(job)


# ============================================================
# TRANSCRIPT
# ============================================================


@app.get("/api/jobs/{job_id}/transcript")
def get_transcript(job_id: str):

    job = get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    transcript_file_path = job.get("transcript_file_path")

    if not transcript_file_path:
        raise HTTPException(
            status_code=404,
            detail="Transcript not available",
        )

    if not os.path.exists(transcript_file_path):
        raise HTTPException(
            status_code=404,
            detail="Transcript file not found",
        )

    try:
        import json

        with open(
            transcript_file_path,
            "r",
            encoding="utf-8",
        ) as file:
            transcript = json.load(file)

        return transcript

    except Exception as e:

        logger.exception("Could not read transcript")

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )


# ============================================================
# MEDIA
# ============================================================


@app.get("/api/jobs/{job_id}/media")
def get_media(job_id: str):

    job = get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    media_file_path = job.get("media_file_path")

    if not media_file_path:
        raise HTTPException(
            status_code=404,
            detail="Media not available",
        )

    media_file_path = os.path.abspath(media_file_path)

    artifact_base = os.path.abspath("artifact")

    try:
        if (
            os.path.commonpath(
                [
                    artifact_base,
                    media_file_path,
                ]
            )
            != artifact_base
        ):
            raise HTTPException(
                status_code=403,
                detail="Invalid media path",
            )

    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Invalid media path",
        )

    if not os.path.exists(media_file_path):
        raise HTTPException(
            status_code=404,
            detail="Media file not found",
        )

    return FileResponse(media_file_path)


# ============================================================
# ASK QUESTION
# ============================================================


@app.post("/api/jobs/{job_id}/ask")
def ask_question(
    job_id: str,
    request: AskRequest,
):

    job = get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    if job.get("status") != "completed":
        raise HTTPException(
            status_code=400,
            detail="Job is not completed yet",
        )

    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question is required",
        )

    embedding_artifact = job.get("embedding_artifact")

    if embedding_artifact is None:

        raise HTTPException(
            status_code=500,
            detail="Embedding artifact is not available",
        )

    qa_pipeline = None

    try:

        from src.pipeline.qa_pipeline import (
            QAPipeline,
        )

        qa_pipeline = QAPipeline(embedding_artifact)

        answer = qa_pipeline.ask(question)

        return answer

    except HTTPException:
        raise

    except Exception as e:

        logger.exception("Question answering failed")

        raise HTTPException(
            status_code=500,
            detail=str(e),
        )

    finally:

        qa_pipeline = None
        gc.collect()


# ============================================================
# HEALTH
# ============================================================


@app.get("/health")
def health():
    return {
        "status": "ok",
    }
