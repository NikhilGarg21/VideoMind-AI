import os
import sys
import subprocess

import yt_dlp

from src.utils.main_utils import save_json
from src.entity.config_entity import AudioIngestionConfig
from src.entity.artifact_entity import AudioIngestionArtifact
from src.exception import MyException
from src.logger import logger


class AudioIngestion:
    """Handles video URL validation, audio download, and audio chunking."""

    def __init__(
        self,
        audio_ingestion_config: AudioIngestionConfig,
    ):
        """
        Initialize AudioIngestion with its configuration.

        Args:
            audio_ingestion_config: Configuration object holding paths for
                the downloaded audio file, chunk output directory, and
                video metadata file.
        """
        self.audio_ingestion_config = audio_ingestion_config

    def download_audio(
        self,
        video_url: str,
    ) -> tuple[str, dict]:
        """
        Validate the video URL, download its audio, and return metadata.

        Args:
            video_url: The source video URL.

        Returns:
            Tuple of downloaded audio path and raw yt-dlp info dict.

        Raises:
            MyException: If download or validation fails.
        """
        try:
            logger.info("Starting audio validation and download")

            output_dir = os.path.dirname(self.audio_ingestion_config.audio_path)

            if output_dir:
                os.makedirs(
                    output_dir,
                    exist_ok=True,
                )

            outtmpl_base = os.path.splitext(self.audio_ingestion_config.audio_path)[0]

            ydl_opts = {
                "format": "ba/b",
                "outtmpl": (outtmpl_base + ".%(ext)s"),
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
                    "youtubepot-bgutilhttp": {"base_url": ["http://127.0.0.1:4416"]},
                },
                "js_runtimes": {"node": {}},
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:

                info = ydl.extract_info(
                    video_url,
                    download=True,
                )

            if info is None:
                raise ValueError(f"Could not extract info for URL: {video_url}")

            logger.info(
                f"URL validated: " f"{info.get('extractor')} - " f"{info.get('title')}"
            )

            final_path = outtmpl_base + ".mp3"

            if not os.path.exists(final_path):
                raise FileNotFoundError(
                    "Expected audio file not found at " f"{final_path}"
                )

            logger.info("Audio download completed")

            return final_path, info

        except yt_dlp.utils.DownloadError as e:
            raise MyException(
                f"Unsupported or invalid URL: " f"{video_url} ({e})",
                sys,
            ) from e

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

    def create_audio_chunks(
        self,
        audio_path: str,
    ) -> str:
        """
        Split the downloaded audio file into fixed-length chunks.

        Args:
            audio_path: Path to full downloaded audio.

        Returns:
            Path to generated chunk directory.

        Raises:
            MyException: If FFmpeg chunking fails.
        """
        try:
            logger.info("Starting audio chunking")

            chunk_duration = self.audio_ingestion_config.chunk_duration

            chunks_dir = self.audio_ingestion_config.audio_chunks_dir

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

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.error("ffmpeg chunking failed: " f"{result.stderr}")

                raise RuntimeError(f"ffmpeg failed with code " f"{result.returncode}")

            logger.info("Audio chunking completed")

            return chunks_dir

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

    def cleanup_audio_file(
        self,
        audio_path: str,
    ) -> None:
        """
        Delete the original full audio file after chunking.

        Failure to delete the file is logged as a warning and does not
        fail the pipeline.
        """
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)

                logger.info(f"Deleted original audio file: " f"{audio_path}")

        except Exception as e:
            logger.warning(
                f"Could not delete original audio file " f"{audio_path}: {e}"
            )

    def compute_chunk_durations(
        self,
        total_duration: float,
        chunk_duration: int,
    ) -> list:
        """
        Deterministically compute each chunk duration.

        Args:
            total_duration: Total source duration in seconds.
            chunk_duration: Configured chunk length in seconds.

        Returns:
            List containing duration of each chunk.
        """
        try:
            if total_duration is None:
                raise ValueError("Video duration is not available")

            if chunk_duration <= 0:
                raise ValueError("Chunk duration must be greater than zero")

            full_chunks = int(total_duration // chunk_duration)

            remainder = total_duration - (full_chunks * chunk_duration)

            durations = [float(chunk_duration)] * full_chunks

            if remainder > 0:
                durations.append(float(remainder))

            return durations

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

    def extract_video_metadata(
        self,
        info: dict,
    ) -> dict:
        """
        Extract a clean subset of video metadata.
        """
        try:
            return {
                "id": info.get("id"),
                "title": info.get("title"),
                "description": info.get("description"),
                "duration": info.get("duration"),
                "upload_date": info.get("upload_date"),
                "uploader": info.get("uploader"),
                "channel": info.get("channel"),
                "view_count": info.get("view_count"),
                "like_count": info.get("like_count"),
                "thumbnail": info.get("thumbnail"),
                "webpage_url": info.get("webpage_url"),
            }

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

    def initiate_audio_ingestion(
        self,
        video_url: str,
    ) -> AudioIngestionArtifact:
        """
        Execute the complete audio ingestion process.

        Lifecycle:
            1. Download full audio.
            2. Create audio chunks.
            3. Delete full audio.
            4. Save metadata.
        """
        try:
            audio_file_path, info = self.download_audio(video_url)

            audio_chunks_dir = self.create_audio_chunks(audio_file_path)

            # Full audio is no longer needed after chunking.
            self.cleanup_audio_file(audio_file_path)

            chunk_duration = self.audio_ingestion_config.chunk_duration

            chunk_durations = self.compute_chunk_durations(
                total_duration=info.get("duration"),
                chunk_duration=chunk_duration,
            )

            video_metadata = self.extract_video_metadata(info)

            video_metadata_file_path = save_json(
                data=video_metadata,
                file_path=(self.audio_ingestion_config.video_metadata_file_path),
            )

            audio_ingestion_artifact = AudioIngestionArtifact(
                audio_file_path=audio_file_path,
                audio_chunks_dir=audio_chunks_dir,
                video_metadata_file_path=(video_metadata_file_path),
                chunk_durations=chunk_durations,
            )

            logger.info("Audio ingestion artifact created")

            return audio_ingestion_artifact

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e
