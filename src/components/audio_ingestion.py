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

    def __init__(self, audio_ingestion_config: AudioIngestionConfig):
        """Initialize AudioIngestion with its configuration."""
        self.audio_ingestion_config = audio_ingestion_config

    def validate_url(self, video_url: str) -> dict:
        """Validate the video URL and extract its metadata."""
        try:
            logger.info("Validating video URL")

            probe_opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "skip_download": True,
            }

            with yt_dlp.YoutubeDL(probe_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)

            if info is None:
                raise ValueError(f"Could not extract info for URL: {video_url}")

            logger.info(f"URL validated: {info.get('extractor')} - {info.get('title')}")

            return info

        except yt_dlp.utils.DownloadError as e:
            raise MyException(f"Unsupported or invalid URL: {video_url} ({e})", sys)

        except Exception as e:
            raise MyException(e, sys)

    def download_audio(self, video_url: str) -> tuple[str, dict]:
        """Download audio and return the audio path with video metadata."""
        try:
            video_metadata = self.validate_url(video_url)
            logger.info("Starting audio download")

            output_dir = os.path.dirname(self.audio_ingestion_config.audio_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            outtmpl_base = os.path.splitext(self.audio_ingestion_config.audio_path)[0]

            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": outtmpl_base + ".%(ext)s",
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

            final_path = outtmpl_base + ".mp3"

            if not os.path.exists(final_path):
                raise FileNotFoundError(
                    f"Expected audio file not found at {final_path}"
                )

            logger.info("Audio download completed")
            return final_path, video_metadata

        except Exception as e:
            raise MyException(e, sys)

    def create_audio_chunks(self, audio_path: str, chunk_duration: int = 60) -> str:
        """Split the audio file into smaller chunks using FFmpeg."""
        try:
            logger.info("Starting audio chunking")

            os.makedirs(self.audio_ingestion_config.audio_chunks_dir, exist_ok=True)

            chunk_pattern = os.path.join(
                self.audio_ingestion_config.audio_chunks_dir, "chunk_%03d.mp3"
            )

            command = [
                "ffmpeg",
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

            result = subprocess.run(command, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"ffmpeg chunking failed: {result.stderr}")

                raise RuntimeError(f"ffmpeg failed with code {result.returncode}")

            logger.info("Audio chunking completed")

            return self.audio_ingestion_config.audio_chunks_dir

        except Exception as e:
            raise MyException(e, sys)

    def extract_video_metadata(self, info: dict) -> dict:
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
            raise MyException(e, sys)

    def initiate_audio_ingestion(self, video_url: str) -> AudioIngestionArtifact:
        """Execute the complete audio ingestion process."""
        try:
            audio_file_path, info = self.download_audio(video_url)
            audio_chunks_dir = self.create_audio_chunks(audio_file_path)
            video_metadata = self.extract_video_metadata(info)
            video_metadata_file_path = save_json(
                data=video_metadata,
                file_path=self.audio_ingestion_config.video_metadata_file_path,
            )
            audio_ingestion_artifact = AudioIngestionArtifact(
                audio_file_path=audio_file_path,
                audio_chunks_dir=audio_chunks_dir,
                video_metadata_file_path=video_metadata_file_path,
            )

            logger.info("Audio ingestion artifact created")
            return audio_ingestion_artifact

        except Exception as e:
            raise MyException(e, sys)
