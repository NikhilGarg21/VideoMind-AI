import copy
import glob
import os
import sys
import subprocess
import threading
import time

import yt_dlp

from src.utils.main_utils import save_json
from src.entity.config_entity import AudioIngestionConfig
from src.entity.artifact_entity import AudioIngestionArtifact
from src.exception import MyException
from src.logger import logger


# --------------------------------------------------------------------------
# yt-dlp prefetch cache
# --------------------------------------------------------------------------

YTDLP_PREFETCH_CACHE = {}
YTDLP_PREFETCH_LOCK = threading.Lock()

# Validation -> download reuse window.
YTDLP_PREFETCH_TTL = 120

# Allow the same validated extraction to serve two immediate
# download requests, which is useful during the two-user test.
YTDLP_PREFETCH_MAX_USES = 2


def cache_prefetched_info(
    video_url: str,
    info: dict,
) -> None:
    """
    Temporarily cache successful yt-dlp extraction info.

    This lets:

        /api/validate
              ↓
        expensive YouTube extraction
              ↓
        actual download

    reuse the extraction instead of starting from scratch.
    """

    try:

        key = video_url.strip()

        with YTDLP_PREFETCH_LOCK:

            YTDLP_PREFETCH_CACHE[
                key
            ] = {
                "created_at": time.monotonic(),
                "remaining_uses": (
                    YTDLP_PREFETCH_MAX_USES
                ),
                "info": copy.deepcopy(
                    info
                ),
            }

        logger.info(
            f"Cached yt-dlp extraction for: {key}"
        )

    except Exception as e:

        logger.warning(
            "Could not cache yt-dlp info: "
            f"{e}"
        )


def pop_prefetched_info(
    video_url: str,
) -> dict | None:
    """
    Consume one cached extraction if it is still fresh.
    """

    try:

        key = video_url.strip()

        with YTDLP_PREFETCH_LOCK:

            cached = (
                YTDLP_PREFETCH_CACHE.get(
                    key
                )
            )

            if cached is None:
                return None

            age = (
                time.monotonic()
                - cached["created_at"]
            )

            if age > YTDLP_PREFETCH_TTL:

                YTDLP_PREFETCH_CACHE.pop(
                    key,
                    None,
                )

                logger.info(
                    f"Expired yt-dlp cache: {key}"
                )

                return None

            info = copy.deepcopy(
                cached["info"]
            )

            cached[
                "remaining_uses"
            ] -= 1

            if (
                cached[
                    "remaining_uses"
                ]
                <= 0
            ):

                YTDLP_PREFETCH_CACHE.pop(
                    key,
                    None,
                )

            logger.info(
                "Reusing cached yt-dlp extraction"
            )

            return info

    except Exception as e:

        logger.warning(
            "Could not read yt-dlp cache: "
            f"{e}"
        )

        return None


# --------------------------------------------------------------------------
# Audio ingestion
# --------------------------------------------------------------------------

class AudioIngestion:
    """
    Handles YouTube audio download and audio chunking.
    """

    def __init__(
        self,
        audio_ingestion_config: AudioIngestionConfig,
    ):
        self.audio_ingestion_config = (
            audio_ingestion_config
        )

    # ----------------------------------------------------------------------
    # Find downloaded source
    # ----------------------------------------------------------------------

    def find_downloaded_audio(
        self,
        output_base: str,
    ) -> str:
        """
        Find the actual downloaded source file.

        yt-dlp may choose WebM, M4A, or another audio container,
        so we do not assume the extension.
        """

        candidates = [
            path
            for path in glob.glob(
                output_base + ".*"
            )
            if os.path.isfile(path)
            and not path.endswith(
                ".part"
            )
            and not path.endswith(
                ".ytdl"
            )
        ]

        if not candidates:

            raise FileNotFoundError(
                "Could not find downloaded "
                "audio source"
            )

        candidates.sort(
            key=os.path.getmtime,
            reverse=True,
        )

        return candidates[0]

    # ----------------------------------------------------------------------
    # Download
    # ----------------------------------------------------------------------

    def download_audio(
        self,
        video_url: str,
    ) -> tuple[str, dict]:
        """
        Download the best available audio source.

        Important:
        - No FFmpegExtractAudio postprocessor.
        - yt-dlp keeps the original container.
        - Validation extraction can be reused.
        """

        try:

            logger.info(
                "Starting audio validation and download"
            )

            output_dir = os.path.dirname(
                self.audio_ingestion_config.audio_path
            )

            if output_dir:

                os.makedirs(
                    output_dir,
                    exist_ok=True,
                )

            outtmpl_base = (
                os.path.splitext(
                    self.audio_ingestion_config.audio_path
                )[0]
            )

            # Remove stale output from a previous attempt.
            for stale_path in glob.glob(
                outtmpl_base + ".*"
            ):

                if (
                    stale_path.endswith(
                        ".part"
                    )
                    or stale_path.endswith(
                        ".ytdl"
                    )
                ):
                    continue

                try:

                    if os.path.isfile(
                        stale_path
                    ):

                        os.remove(
                            stale_path
                        )

                except Exception as e:

                    logger.warning(
                        f"Could not remove stale file "
                        f"{stale_path}: {e}"
                    )

            # --------------------------------------------------------------
            # KEEP THIS YT-DLP CONFIG
            # --------------------------------------------------------------

            ydl_opts = {
                "format": "ba/b",

                "outtmpl": (
                    outtmpl_base
                    + ".%(ext)s"
                ),

                "noplaylist": True,

                "quiet": False,

                "no_warnings": False,

                "verbose": True,

                "cookiefile": os.getenv(
                    "YOUTUBE_COOKIE_FILE",
                    "cookies.txt",
                ),

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

                "js_runtimes": {
                    "node": {}
                },
            }

            # --------------------------------------------------------------
            # REUSE VALIDATION EXTRACTION
            # --------------------------------------------------------------

            prefetched_info = (
                pop_prefetched_info(
                    video_url
                )
            )

            with yt_dlp.YoutubeDL(
                ydl_opts
            ) as ydl:

                if prefetched_info is not None:

                    logger.info(
                        "Using prefetched yt-dlp info "
                        "for actual download"
                    )

                    try:

                        info = (
                            ydl.process_ie_result(
                                prefetched_info,
                                download=True,
                            )
                        )

                    except yt_dlp.utils.DownloadError as e:

                        logger.warning(
                            "Prefetched yt-dlp result "
                            "could not be reused. "
                            "Falling back to fresh extraction: "
                            f"{e}"
                        )

                        info = (
                            ydl.extract_info(
                                video_url,
                                download=True,
                            )
                        )

                else:

                    logger.info(
                        "No prefetched yt-dlp info "
                        "available; performing fresh extraction"
                    )

                    info = (
                        ydl.extract_info(
                            video_url,
                            download=True,
                        )
                    )

            if info is None:

                raise ValueError(
                    f"Could not extract info for URL: "
                    f"{video_url}"
                )

            downloaded_path = (
                self.find_downloaded_audio(
                    outtmpl_base
                )
            )

            logger.info(
                "URL validation/download completed: "
                f"{info.get('extractor')} - "
                f"{info.get('title')}"
            )

            logger.info(
                f"Downloaded source audio: "
                f"{downloaded_path}"
            )

            return (
                downloaded_path,
                info,
            )

        except yt_dlp.utils.DownloadError as e:

            raise MyException(
                "Unsupported or invalid URL: "
                f"{video_url} ({e})",
                sys,
            ) from e

        except Exception as e:

            raise MyException(
                e,
                sys,
            ) from e

    # ----------------------------------------------------------------------
    # Media duration
    # ----------------------------------------------------------------------

    def get_media_duration(
        self,
        media_path: str,
    ) -> float:
        """
        Read media duration without fully converting the file.
        """

        try:

            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    media_path,
                ],
                capture_output=True,
                text=True,
            )

            if (
                result.returncode != 0
                or not result.stdout.strip()
            ):

                raise RuntimeError(
                    result.stderr
                    or "ffprobe could not read duration"
                )

            duration = float(
                result.stdout.strip()
            )

            if duration <= 0:
                raise ValueError(
                    "Media duration must be greater than zero"
                )

            return duration

        except Exception as e:

            raise MyException(
                e,
                sys,
            ) from e

    # ----------------------------------------------------------------------
    # Chunking
    # ----------------------------------------------------------------------

    def create_audio_chunks(
        self,
        audio_path: str,
    ) -> str:
        """
        Split the source media directly into MP3 chunks.

        IMPORTANT OPTIMIZATION:

        Old:
            YouTube WebM
                ↓
            full MP3 conversion
                ↓
            MP3 chunking

        New:
            YouTube WebM/M4A/etc.
                ↓
            directly create MP3 chunks

        So the full intermediate MP3 never exists.
        """

        try:

            logger.info(
                "Starting audio chunking"
            )

            chunk_duration = (
                self.audio_ingestion_config.chunk_duration
            )

            chunks_dir = (
                self.audio_ingestion_config.audio_chunks_dir
            )

            os.makedirs(
                chunks_dir,
                exist_ok=True,
            )

            chunk_pattern = os.path.join(
                chunks_dir,
                "chunk_%03d.mp3",
            )

            command = [
                "ffmpeg",

                "-y",

                "-i",
                audio_path,

                "-vn",

                "-map",
                "0:a:0",

                "-f",
                "segment",

                "-segment_time",
                str(chunk_duration),

                "-reset_timestamps",
                "1",

                "-c:a",
                "libmp3lame",

                "-q:a",
                "2",

                chunk_pattern,
            ]

            logger.info(
                "Running FFmpeg chunk command"
            )

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:

                logger.error(
                    "FFmpeg chunking failed: "
                    f"{result.stderr}"
                )

                raise RuntimeError(
                    f"ffmpeg failed with code "
                    f"{result.returncode}"
                )

            logger.info(
                "Audio chunking completed"
            )

            return chunks_dir

        except Exception as e:

            raise MyException(
                e,
                sys,
            ) from e

    # ----------------------------------------------------------------------
    # Cleanup
    # ----------------------------------------------------------------------

    def cleanup_audio_file(
        self,
        audio_path: str,
    ) -> None:
        """
        Delete full source audio immediately after
        successful chunk creation.
        """

        try:

            if os.path.exists(
                audio_path
            ):

                os.remove(
                    audio_path
                )

                logger.info(
                    f"Deleted original audio source: "
                    f"{audio_path}"
                )

        except Exception as e:

            logger.warning(
                "Could not delete original audio source "
                f"{audio_path}: {e}"
            )

    # ----------------------------------------------------------------------
    # Chunk durations
    # ----------------------------------------------------------------------

    def compute_chunk_durations(
        self,
        total_duration: float,
        chunk_duration: int,
    ) -> list:
        """
        Deterministically compute chunk durations.
        """

        try:

            if total_duration is None:

                raise ValueError(
                    "Video duration is not available"
                )

            if chunk_duration <= 0:

                raise ValueError(
                    "Chunk duration must be greater than zero"
                )

            full_chunks = int(
                total_duration
                // chunk_duration
            )

            remainder = (
                total_duration
                - (
                    full_chunks
                    * chunk_duration
                )
            )

            durations = [
                float(
                    chunk_duration
                )
            ] * full_chunks

            if remainder > 0:

                durations.append(
                    float(
                        remainder
                    )
                )

            return durations

        except Exception as e:

            raise MyException(
                e,
                sys,
            ) from e

    # ----------------------------------------------------------------------
    # Metadata
    # ----------------------------------------------------------------------

    def extract_video_metadata(
        self,
        info: dict,
    ) -> dict:
        """
        Extract a clean subset of video metadata.
        """

        try:

            return {
                "id": info.get(
                    "id"
                ),

                "title": info.get(
                    "title"
                ),

                "description": info.get(
                    "description"
                ),

                "duration": info.get(
                    "duration"
                ),

                "upload_date": info.get(
                    "upload_date"
                ),

                "uploader": info.get(
                    "uploader"
                ),

                "channel": info.get(
                    "channel"
                ),

                "view_count": info.get(
                    "view_count"
                ),

                "like_count": info.get(
                    "like_count"
                ),

                "thumbnail": info.get(
                    "thumbnail"
                ),

                "webpage_url": info.get(
                    "webpage_url"
                ),
            }

        except Exception as e:

            raise MyException(
                e,
                sys,
            ) from e

    # ----------------------------------------------------------------------
    # Full ingestion
    # ----------------------------------------------------------------------

    def initiate_audio_ingestion(
        self,
        video_url: str,
    ) -> AudioIngestionArtifact:
        """
        Execute complete audio ingestion.

        Lifecycle:

        1. Download original audio container.
        2. Chunk directly into MP3 pieces.
        3. Delete original source.
        4. Save metadata.
        """

        try:

            audio_file_path, info = (
                self.download_audio(
                    video_url
                )
            )

            # Prefer yt-dlp metadata.
            total_duration = (
                info.get(
                    "duration"
                )
            )

            # Fallback to ffprobe if metadata is missing.
            if not total_duration:

                total_duration = (
                    self.get_media_duration(
                        audio_file_path
                    )
                )

            audio_chunks_dir = (
                self.create_audio_chunks(
                    audio_file_path
                )
            )

            # Source container is no longer required.
            self.cleanup_audio_file(
                audio_file_path
            )

            chunk_duration = (
                self.audio_ingestion_config.chunk_duration
            )

            chunk_durations = (
                self.compute_chunk_durations(
                    total_duration=(
                        total_duration
                    ),
                    chunk_duration=(
                        chunk_duration
                    ),
                )
            )

            video_metadata = (
                self.extract_video_metadata(
                    info
                )
            )

            video_metadata_file_path = (
                save_json(
                    data=video_metadata,
                    file_path=(
                        self.audio_ingestion_config
                        .video_metadata_file_path
                    ),
                )
            )

            audio_ingestion_artifact = (
                AudioIngestionArtifact(
                    audio_file_path=(
                        audio_file_path
                    ),
                    audio_chunks_dir=(
                        audio_chunks_dir
                    ),
                    video_metadata_file_path=(
                        video_metadata_file_path
                    ),
                    chunk_durations=(
                        chunk_durations
                    ),
                )
            )

            logger.info(
                "Audio ingestion artifact created"
            )

            return (
                audio_ingestion_artifact
            )

        except Exception as e:

            raise MyException(
                e,
                sys,
            ) from e
