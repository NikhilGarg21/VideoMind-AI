import os
import sys
import json
import subprocess
import whisper

from src.entity.config_entity import AudioTranscriptionConfig
from src.entity.artifact_entity import (
    AudioIngestionArtifact,
    AudioTranscriptionArtifact,
)
from src.exception import MyException
from src.logger import logger


class AudioTranscription:
    """Transcribes audio chunks and preserves timestamp information."""

    def __init__(
        self,
        audio_ingestion_artifact: AudioIngestionArtifact,
        audio_transcription_config: AudioTranscriptionConfig,
    ):
        """Initialize AudioTranscription with artifacts and configuration."""

        self.audio_ingestion_artifact = audio_ingestion_artifact
        self.audio_transcription_config = audio_transcription_config

    def validate_audio_chunks(self) -> list:
        """Validate and retrieve available audio chunk files."""

        try:
            logger.info("Validating audio chunks")

            audio_chunks_dir = self.audio_ingestion_artifact.audio_chunks_dir

            if not os.path.exists(audio_chunks_dir):
                raise FileNotFoundError(
                    f"Audio chunks directory not found: " f"{audio_chunks_dir}"
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

            logger.info(f"Found {len(audio_chunks)} audio chunks")

            return audio_chunks

        except Exception as e:
            raise MyException(e, sys) from e

    def get_audio_duration(self, audio_path: str) -> float:
        """Return the real duration (seconds) of an audio file via ffprobe."""
        try:
            command = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ]
            result = subprocess.run(command, capture_output=True, text=True)

            if result.returncode != 0:
                raise RuntimeError(f"ffprobe failed for {audio_path}: {result.stderr}")

            return float(result.stdout.strip())

        except Exception as e:
            raise MyException(e, sys) from e

    def load_whisper_model(self):
        """Load the Whisper transcription model."""
        try:
            logger.info("Loading Whisper model")
            model = whisper.load_model("base")
            logger.info("Whisper model loaded successfully")
            return model

        except Exception as e:
            raise MyException(e, sys) from e

    def transcribe_audio_chunks(
        self,
        audio_chunks: list,
        model,
    ) -> list:
        """Transcribe audio chunks and preserve segment timestamps."""

        try:
            logger.info("Starting audio transcription")
            all_segments = []
            cumulative_offset = 0.0

            for chunk_index, audio_chunk in enumerate(audio_chunks):
                logger.info(f"Transcribing audio chunk " f"{chunk_index + 1}")

                result = model.transcribe(
                    audio_chunk,
                    language="en",
                    fp16=False,
                )

                for segment in result["segments"]:
                    segment_data = {
                        "id": len(all_segments),
                        "start": round(cumulative_offset + segment["start"], 2),
                        "end": round(cumulative_offset + segment["end"], 2),
                        "text": segment["text"].strip(),
                    }

                    all_segments.append(segment_data)

                cumulative_offset += self.get_audio_duration(audio_chunk)
            if not all_segments:
                raise ValueError("No transcription segments were created")

            logger.info(f"Created {len(all_segments)} " f"transcription segments")

            return all_segments

        except Exception as e:
            raise MyException(e, sys) from e

    def create_transcript_data(
        self,
        segments: list,
    ) -> dict:
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

    def save_transcript(
        self,
        transcript_data: dict,
    ) -> str:
        """Save timestamped transcript data as JSON."""

        try:
            logger.info("Saving transcript")

            output_dir = os.path.dirname(
                self.audio_transcription_config.transcript_file_path
            )

            os.makedirs(
                output_dir,
                exist_ok=True,
            )

            with open(
                self.audio_transcription_config.transcript_file_path,
                "w",
                encoding="utf-8",
            ) as file:

                json.dump(
                    transcript_data,
                    file,
                    ensure_ascii=False,
                    indent=4,
                )

            logger.info("Transcript saved successfully")

            return self.audio_transcription_config.transcript_file_path

        except Exception as e:
            raise MyException(e, sys) from e

    def initiate_audio_transcription(
        self,
    ) -> AudioTranscriptionArtifact:
        """Execute the complete audio transcription process."""

        try:
            audio_chunks = self.validate_audio_chunks()

            model = self.load_whisper_model()

            segments = self.transcribe_audio_chunks(
                audio_chunks=audio_chunks,
                model=model,
            )

            transcript_data = self.create_transcript_data(segments=segments)

            transcript_file_path = self.save_transcript(transcript_data=transcript_data)

            audio_transcription_artifact = AudioTranscriptionArtifact(
                transcript_file_path=transcript_file_path
            )

            logger.info("Audio transcription artifact " "created successfully")

            return audio_transcription_artifact

        except Exception as e:
            raise MyException(e, sys) from e
