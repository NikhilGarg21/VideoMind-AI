import os
import sys
import time
import shutil

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
    """
    Transcribes audio chunks via Groq's hosted Whisper API
    and preserves timestamp information.
    """

    def __init__(
        self,
        audio_ingestion_artifact: AudioIngestionArtifact,
        audio_transcription_config: AudioTranscriptionConfig,
    ):
        """
        Initialize AudioTranscription.
        """
        try:
            self.audio_ingestion_artifact = audio_ingestion_artifact

            self.audio_transcription_config = audio_transcription_config

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

    def validate_audio_chunks(self) -> list:
        """
        Validate the audio chunks directory and return sorted chunk paths.
        """
        try:
            logger.info("Validating audio chunks")

            audio_chunks_dir = self.audio_ingestion_artifact.audio_chunks_dir

            if not os.path.exists(audio_chunks_dir):
                raise FileNotFoundError(
                    "Audio chunks directory not found: " f"{audio_chunks_dir}"
                )

            audio_chunks = sorted(
                [
                    os.path.join(
                        audio_chunks_dir,
                        file_name,
                    )
                    for file_name in os.listdir(audio_chunks_dir)
                    if file_name.endswith(".mp3")
                ]
            )

            if not audio_chunks:
                raise ValueError("No audio chunks found")

            logger.info(f"Found {len(audio_chunks)} " "audio chunks")

            return audio_chunks

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

    def load_transcription_client(self) -> Groq:
        """
        Initialize Groq transcription client.
        """
        try:
            logger.info("Initializing Groq transcription client")

            api_key = os.getenv("GROQ_API_KEY")

            if not api_key:
                raise ValueError("GROQ_API_KEY is not set " "in environment variables")

            client = Groq(api_key=api_key)

            logger.info("Groq transcription client " "initialized successfully")

            return client

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

    def transcribe_chunk_with_retry(
        self,
        client: Groq,
        audio_chunk: str,
    ) -> list:
        """
        Transcribe a single audio chunk via Groq.

        The file object is passed directly to Groq so the complete
        audio file is not loaded into memory with file.read().
        """
        max_retries = self.audio_transcription_config.max_retries

        retry_delay = self.audio_transcription_config.retry_delay

        last_error = None

        for attempt in range(
            1,
            max_retries + 1,
        ):
            try:
                logger.info(
                    f"Transcription attempt "
                    f"{attempt}/{max_retries} "
                    f"for "
                    f"{os.path.basename(audio_chunk)}"
                )

                with open(
                    audio_chunk,
                    "rb",
                ) as file:

                    response = client.audio.transcriptions.create(
                        file=file,
                        model=(self.audio_transcription_config.model_name),
                        language="en",
                        response_format="verbose_json",
                    )

                segments = response.segments or []

                logger.info(
                    f"Transcription completed for " f"{os.path.basename(audio_chunk)}"
                )

                return segments

            except Exception as e:
                last_error = e

                logger.warning(
                    f"Transcription attempt "
                    f"{attempt}/{max_retries} failed "
                    f"for "
                    f"{os.path.basename(audio_chunk)}: "
                    f"{e}"
                )

                if attempt < max_retries:
                    wait_time = retry_delay * attempt

                    logger.info(f"Retrying in " f"{wait_time} seconds...")

                    time.sleep(wait_time)

        raise MyException(
            last_error,
            sys,
        ) from last_error

    def transcribe_audio_chunks(
        self,
        audio_chunks: list,
        client: Groq,
    ) -> list:
        """
        Transcribe all chunks and convert local timestamps
        into global timestamps.
        """
        try:
            logger.info("Starting audio transcription")

            chunk_durations = self.audio_ingestion_artifact.chunk_durations

            all_segments = []
            cumulative_offset = 0.0

            for chunk_index, (
                audio_chunk,
                chunk_duration,
            ) in enumerate(
                zip(
                    audio_chunks,
                    chunk_durations,
                )
            ):
                logger.info(
                    f"Transcribing audio chunk "
                    f"{chunk_index + 1}/"
                    f"{len(audio_chunks)}"
                )

                raw_segments = self.transcribe_chunk_with_retry(
                    client=client,
                    audio_chunk=audio_chunk,
                )

                for segment in raw_segments:

                    segment_data = {
                        "id": len(all_segments),
                        "start": round(
                            cumulative_offset + segment["start"],
                            2,
                        ),
                        "end": round(
                            cumulative_offset + segment["end"],
                            2,
                        ),
                        "text": (segment["text"].strip()),
                    }

                    all_segments.append(segment_data)

                cumulative_offset += chunk_duration

            if not all_segments:
                raise ValueError("No transcription segments " "were created")

            logger.info(f"Created {len(all_segments)} " "transcription segments")

            return all_segments

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

    def create_transcript_data(
        self,
        segments: list,
    ) -> dict:
        """
        Wrap segments into the persisted transcript format.
        """
        try:
            logger.info("Creating structured transcript data")

            transcript_data = {
                "total_segments": len(segments),
                "segments": segments,
            }

            logger.info("Structured transcript data " "created successfully")

            return transcript_data

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

    def cleanup_audio_chunks(self) -> None:
        """
        Delete all audio chunks after successful transcription.

        This is intentionally called only after the transcript has
        been successfully saved.
        """
        try:
            chunks_dir = self.audio_ingestion_artifact.audio_chunks_dir

            if os.path.exists(chunks_dir):
                shutil.rmtree(chunks_dir)

                logger.info(f"Deleted audio chunks directory: " f"{chunks_dir}")

        except Exception as e:
            logger.warning(f"Could not delete audio chunks: " f"{e}")

    def initiate_audio_transcription(
        self,
    ) -> AudioTranscriptionArtifact:
        """
        Execute the transcription pipeline.

        Lifecycle:
            1. Read audio chunks.
            2. Transcribe all chunks.
            3. Save transcript.
            4. Delete chunks.

        If transcription fails, chunks remain available for retry.
        """
        client = None

        try:
            logger.info("Starting audio transcription pipeline")

            audio_chunks = self.validate_audio_chunks()

            client = self.load_transcription_client()

            segments = self.transcribe_audio_chunks(
                audio_chunks=audio_chunks,
                client=client,
            )

            transcript_data = self.create_transcript_data(
                segments=segments,
            )

            transcript_file_path = self.audio_transcription_config.transcript_file_path

            # Save transcript first.
            save_json(
                transcript_data,
                transcript_file_path,
            )

            # Only after the transcript is safely persisted,
            # delete the source audio chunks.
            self.cleanup_audio_chunks()

            audio_transcription_artifact = AudioTranscriptionArtifact(
                transcript_file_path=(transcript_file_path)
            )

            logger.info("Audio transcription artifact " "created successfully")

            return audio_transcription_artifact

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

        finally:
            if client is not None:
                try:
                    client.close()

                    logger.info("Groq transcription client closed")

                except Exception as e:
                    logger.warning(f"Failed to close Groq client: {e}")
