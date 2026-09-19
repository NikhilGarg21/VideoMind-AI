import os
import sys


from src.entity.config_entity import AudioTranscriptionConfig
from src.entity.artifact_entity import (
    AudioIngestionArtifact,
    AudioTranscriptionArtifact,
)
from src.exception import MyException
from src.logger import logger
from src.utils.main_utils import save_json


class AudioTranscription:
    """Transcribes audio chunks and preserves timestamp information."""

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
                path for the final transcript JSON.
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
                    f"Audio chunks directory not found: " f"{audio_chunks_dir}"
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

    def load_whisper_model(self):
        """
        Load the Whisper transcription model.

        Returns:
            The loaded Whisper model instance, ready for transcription.

        Raises:
            MyException: If the model fails to load.
        """
        try:
            logger.info("Loading Whisper model")
            import whisper
            model = whisper.load_model("base")
            logger.info("Whisper model loaded successfully")
            return model

        except Exception as e:
            raise MyException(e, sys) from e

    def transcribe_audio_chunks(self, audio_chunks: list, model) -> list:
        """
        Transcribe each audio chunk and adjust segment timestamps to be
        relative to the full (unchunked) audio timeline.

        Uses precomputed chunk durations from the ingestion artifact
        (rather than probing each file) to accumulate the timestamp
        offset across chunks.

        Args:
            audio_chunks: Sorted list of paths to audio chunk files.
            model: The loaded Whisper model to transcribe with.

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
                logger.info(f"Transcribing audio chunk " f"{chunk_index + 1}")

                result = model.transcribe(
                    audio_chunk,
                    language="en",
                    fp16=False,
                )

                for segment in result["segments"]:

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
                        "text": segment["text"].strip(),
                    }

                    all_segments.append(segment_data)

                cumulative_offset += chunk_duration

            if not all_segments:
                raise ValueError("No transcription segments were created")

            logger.info(f"Created {len(all_segments)} " f"transcription segments")
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

            logger.info("Structured transcript data " "created successfully")
            return transcript_data

        except Exception as e:
            raise MyException(e, sys) from e

    def initiate_audio_transcription(self) -> AudioTranscriptionArtifact:
        """
        Execute the complete audio transcription process: validate chunks,
        load the model, transcribe, structure the output, and save it.

        Returns:
            An AudioTranscriptionArtifact pointing to the saved transcript
            JSON file.

        Raises:
            MyException: If any stage of transcription fails.
        """
        try:
            logger.info("Starting audio transcription pipeline")
            audio_chunks = self.validate_audio_chunks()
            model = self.load_whisper_model()

            segments = self.transcribe_audio_chunks(
                audio_chunks=audio_chunks,
                model=model,
            )

            transcript_data = self.create_transcript_data(segments=segments)
            transcript_file_path = self.audio_transcription_config.transcript_file_path
            save_json(transcript_data, transcript_file_path)

            audio_transcription_artifact = AudioTranscriptionArtifact(
                transcript_file_path=transcript_file_path
            )

            logger.info("Audio transcription artifact " "created successfully")
            return audio_transcription_artifact

        except Exception as e:
            raise MyException(e, sys) from e