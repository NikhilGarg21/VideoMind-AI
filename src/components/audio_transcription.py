import os
import sys
import time

from groq import Groq

from src.entity.config_entity import AudioTranscriptionConfig
from src.entity.artifact_entity import (
    AudioIngestionArtifact,
    AudioTranscriptionArtifact,
)
from src.exception import MyException
from src.logger import logger
from src.utils.main_utils import save_json


class AudioTranscription:
    """Transcribes audio chunks via Groq's hosted Whisper API and preserves
    timestamp information."""

    def __init__(
        self,
        audio_ingestion_artifact: AudioIngestionArtifact,
        audio_transcription_config: AudioTranscriptionConfig,
    ):
        """
        Initialize AudioTranscription with artifacts and configuration.

        Args:
            audio_ingestion_artifact: Output of the audio ingestion stage,
                including the chunk directory and per-chunk durations.
            audio_transcription_config: Configuration holding the output
                transcript path, the Groq Whisper model name, and retry
                settings.
        """
        try:
            self.audio_ingestion_artifact = audio_ingestion_artifact
            self.audio_transcription_config = audio_transcription_config

        except Exception as e:
            raise MyException(e, sys) from e

    def validate_audio_chunks(self) -> list:
        """
        Validate that the audio chunks directory exists and contains files.

        Returns:
            A sorted list of full paths to each .mp3 chunk file.

        Raises:
            MyException: If the chunks directory is missing or empty.
        """
        try:
            logger.info("Validating audio chunks")
            audio_chunks_dir = self.audio_ingestion_artifact.audio_chunks_dir
            if not os.path.exists(audio_chunks_dir):
                raise FileNotFoundError(
                    f"Audio chunks directory not found: {audio_chunks_dir}"
                )

            audio_chunks = sorted(
                [
                    os.path.join(audio_chunks_dir, file_name)
                    for file_name in os.listdir(audio_chunks_dir)
                    if file_name.endswith(".mp3")
                ]
            )

            if not audio_chunks:
                raise ValueError("No audio chunks found")

            logger.info(f"Found {len(audio_chunks)} audio chunks")
            return audio_chunks

        except Exception as e:
            raise MyException(e, sys) from e

    def load_transcription_client(self) -> Groq:
        """
        Load the Groq API client used for hosted Whisper transcription.

        Returns:
            An initialized Groq client.

        Raises:
            MyException: If GROQ_API_KEY is not set or the client fails
                to initialize.
        """
        try:
            logger.info("Initializing Groq transcription client")

            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY is not set in environment variables")

            client = Groq(api_key=api_key)

            logger.info("Groq transcription client initialized successfully")
            return client

        except Exception as e:
            raise MyException(e, sys) from e

    def transcribe_chunk_with_retry(self, client: Groq, audio_chunk: str) -> list:
        """
        Transcribe a single audio chunk via Groq's Whisper API, retrying
        on transient failures (network errors, rate limits).

        Args:
            client: The initialized Groq client.
            audio_chunk: Path to the audio chunk file.

        Returns:
            The list of segment dicts returned by Groq for this chunk,
            each with `start`, `end`, and `text`.

        Raises:
            MyException: If all retries are exhausted.
        """
        max_retries = self.audio_transcription_config.max_retries
        retry_delay = self.audio_transcription_config.retry_delay
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                with open(audio_chunk, "rb") as file:
                    response = client.audio.transcriptions.create(
                        file=(os.path.basename(audio_chunk), file.read()),
                        model=self.audio_transcription_config.model_name,
                        language="en",
                        response_format="verbose_json",
                    )

                segments = response.segments or []
                return segments

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Transcription attempt {attempt}/{max_retries} failed "
                    f"for {os.path.basename(audio_chunk)}: {e}"
                )
                if attempt < max_retries:
                    time.sleep(retry_delay * attempt)

        raise MyException(last_error, sys) from last_error

    def transcribe_audio_chunks(self, audio_chunks: list, client: Groq) -> list:
        """
        Transcribe each audio chunk via Groq and adjust segment timestamps
        to be relative to the full (unchunked) audio timeline.

        Uses precomputed chunk durations from the ingestion artifact
        (rather than probing each file) to accumulate the timestamp
        offset across chunks.

        Args:
            audio_chunks: Sorted list of paths to audio chunk files.
            client: The initialized Groq client to transcribe with.

        Returns:
            A list of segment dicts, each with a global `id`, `start`,
            `end` (in seconds, offset-adjusted), and `text`.

        Raises:
            MyException: If no segments are produced.
        """
        try:
            logger.info("Starting audio transcription")

            chunk_durations = self.audio_ingestion_artifact.chunk_durations
            all_segments = []
            cumulative_offset = 0.0

            for chunk_index, (audio_chunk, chunk_duration) in enumerate(
                zip(audio_chunks, chunk_durations)
            ):
                logger.info(f"Transcribing audio chunk {chunk_index + 1}")

                raw_segments = self.transcribe_chunk_with_retry(client, audio_chunk)

                for segment in raw_segments:
                    segment_data = {
                        "id": len(all_segments),
                        "start": round(cumulative_offset + segment["start"], 2),
                        "end": round(cumulative_offset + segment["end"], 2),
                        "text": segment["text"].strip(),
                    }
                    all_segments.append(segment_data)

                cumulative_offset += chunk_duration

            if not all_segments:
                raise ValueError("No transcription segments were created")

            logger.info(f"Created {len(all_segments)} transcription segments")
            return all_segments

        except Exception as e:
            raise MyException(e, sys) from e

    def create_transcript_data(self, segments: list) -> dict:
        """
        Wrap the flat segment list into the structured transcript format
        that gets persisted to disk.

        Args:
            segments: List of segment dicts produced by transcription.

        Returns:
            A dict with `total_segments` count and the `segments` list.

        Raises:
            MyException: If structuring fails unexpectedly.
        """
        try:
            logger.info("Creating structured transcript data")

            transcript_data = {
                "total_segments": len(segments),
                "segments": segments,
            }

            logger.info("Structured transcript data created successfully")
            return transcript_data

        except Exception as e:
            raise MyException(e, sys) from e

    def initiate_audio_transcription(self) -> AudioTranscriptionArtifact:
        """
        Execute the complete audio transcription process: validate chunks,
        load the Groq client, transcribe, structure the output, and save it.

        Returns:
            An AudioTranscriptionArtifact pointing to the saved transcript
            JSON file.

        Raises:
            MyException: If any stage of transcription fails.
        """
        try:
            logger.info("Starting audio transcription pipeline")
            audio_chunks = self.validate_audio_chunks()
            client = self.load_transcription_client()

            segments = self.transcribe_audio_chunks(
                audio_chunks=audio_chunks,
                client=client,
            )

            transcript_data = self.create_transcript_data(segments=segments)
            transcript_file_path = self.audio_transcription_config.transcript_file_path
            save_json(transcript_data, transcript_file_path)

            audio_transcription_artifact = AudioTranscriptionArtifact(
                transcript_file_path=transcript_file_path
            )

            logger.info("Audio transcription artifact created successfully")
            return audio_transcription_artifact

        except Exception as e:
            raise MyException(e, sys) from e