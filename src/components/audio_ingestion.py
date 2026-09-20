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
        """
        Initialize AudioIngestion with its configuration.

        Args:
            audio_ingestion_config: Configuration object holding paths for
                the downloaded audio file, chunk output directory, and
                video metadata file.
        """
        self.audio_ingestion_config = audio_ingestion_config

    def download_audio(self, video_url: str) -> tuple[str, dict]:
        """
        Validate the video URL, download its audio, and return metadata.

        Combines URL validation and download into a single yt_dlp session
        to avoid a redundant network round-trip.

        Args:
            video_url: The source video URL (e.g. a YouTube link).

        Returns:
            A tuple of (path to the downloaded mp3 file, raw yt_dlp info dict).

        Raises:
            MyException: If the URL is invalid/unsupported or the expected
                audio file is not produced after download.
        """
        try:
            logger.info("Starting audio validation and download")

            output_dir = os.path.dirname(self.audio_ingestion_config.audio_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            outtmpl_base = os.path.splitext(self.audio_ingestion_config.audio_path)[0]

            # Inside AudioIngestion.download_audio() in audio_ingestion.py
            ydl_opts = {
                "format": "bestaudio/best",  # Changed from "ba/b" to broaden format fallback
                "outtmpl": outtmpl_base + ".%(ext)s",
                "noplaylist": True,
                "quiet": False,
                "no_warnings": False,
                "cookiefile": os.getenv(
                    "YOUTUBE_COOKIE_FILE",
                    "cookies.txt",
                ),
                "extractor_args": {
                    "youtube": {"player_client": ["android", "ios"]}  # Replaced "mweb" with mobile clients
                },
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)

            if info is None:
                raise ValueError(f"Could not extract info for URL: {video_url}")

            logger.info(f"URL validated: {info.get('extractor')} - {info.get('title')}")

            final_path = outtmpl_base + ".mp3"
            if not os.path.exists(final_path):
                raise FileNotFoundError(
                    f"Expected audio file not found at {final_path}"
                )

            logger.info("Audio download completed")
            return final_path, info

        except yt_dlp.utils.DownloadError as e:
            raise MyException(f"Unsupported or invalid URL: {video_url} ({e})", sys)
        except Exception as e:
            raise MyException(e, sys)

    def create_audio_chunks(self, audio_path: str) -> str:
        """
        Split the downloaded audio file into fixed-length chunks using FFmpeg.

        Args:
            audio_path: Path to the full downloaded audio file.

        Returns:
            Path to the directory containing the generated audio chunks.

        Raises:
            MyException: If the ffmpeg segmentation command fails.
        """
        try:
            logger.info("Starting audio chunking")
            chunk_duration = self.audio_ingestion_config.chunk_duration
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

    def compute_chunk_durations(
        self, total_duration: float, chunk_duration: int
    ) -> list:
        """
        Deterministically compute each chunk's duration from the video's
        total length and the fixed segment size used by FFmpeg.

        Avoids probing each chunk file individually (e.g. via ffprobe),
        since ffmpeg's `-segment_time` split is exact and predictable.

        Args:
            total_duration: Total duration of the source video, in seconds.
            chunk_duration: The fixed segment length used during chunking.

        Returns:
            A list of durations (floats, in seconds), one per chunk, in
            the same order the chunks were created.
        """
        full_chunks = int(total_duration // chunk_duration)
        remainder = total_duration - (full_chunks * chunk_duration)

        durations = [float(chunk_duration)] * full_chunks
        if remainder > 0:
            durations.append(remainder)

        return durations

    def extract_video_metadata(self, info: dict) -> dict:
        """
        Extract a clean, storable subset of fields from the raw yt_dlp info dict.

        Args:
            info: The full metadata dict returned by yt_dlp.

        Returns:
            A dict containing only the fields relevant to downstream storage
            (id, title, description, duration, upload date, etc.).

        Raises:
            MyException: If extraction fails unexpectedly.
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
            raise MyException(e, sys)

    def initiate_audio_ingestion(self, video_url: str) -> AudioIngestionArtifact:
        """
        Execute the complete audio ingestion process: download, chunk,
        compute chunk durations, and save video metadata.

        Args:
            video_url: The source video URL to ingest.

        Returns:
            An AudioIngestionArtifact containing paths to the downloaded
            audio, the chunk directory, the metadata file, and the
            per-chunk duration list.

        Raises:
            MyException: If any stage of ingestion fails.
        """
        try:
            audio_file_path, info = self.download_audio(video_url)
            audio_chunks_dir = self.create_audio_chunks(audio_file_path)

            chunk_duration = self.audio_ingestion_config.chunk_duration
            chunk_durations = self.compute_chunk_durations(
                total_duration=info.get("duration"),
                chunk_duration=chunk_duration,
            )

            video_metadata = self.extract_video_metadata(info)
            video_metadata_file_path = save_json(
                data=video_metadata,
                file_path=self.audio_ingestion_config.video_metadata_file_path,
            )

            audio_ingestion_artifact = AudioIngestionArtifact(
                audio_file_path=audio_file_path,
                audio_chunks_dir=audio_chunks_dir,
                video_metadata_file_path=video_metadata_file_path,
                chunk_durations=chunk_durations,
            )

            logger.info("Audio ingestion artifact created")
            return audio_ingestion_artifact

        except Exception as e:
            raise MyException(e, sys)
