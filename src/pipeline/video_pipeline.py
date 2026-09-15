import sys
from src.components.audio_ingestion import AudioIngestion
from src.components.audio_transcription import AudioTranscription
from src.components.text_processing import TextProcessing
from src.components.timestamps import TimestampGenerator
from src.llm.llm_client import LLMClient
from src.entity.config_entity import (
    AudioIngestionConfig,
    AudioTranscriptionConfig,
    TextProcessingConfig,
    TimestampConfig,
)

from src.entity.artifact_entity import (
    AudioIngestionArtifact,
    AudioTranscriptionArtifact,
    TextProcessingArtifact,
    TimestampArtifact,
)

from src.exception import MyException
from src.logger import logger


class VideoPipeline:
    """Pipeline for audio ingestion and transcription."""

    def __init__(self):
        """Initialize pipeline configurations."""
        self.audio_ingestion_config = AudioIngestionConfig()
        self.audio_transcription_config = AudioTranscriptionConfig()
        self.text_processing_config = TextProcessingConfig()
        self.timestamp_conig = TimestampConfig
        self.llm = LLMClient().get_llm()
    def start_audio_ingestion(self, video_url: str) -> AudioIngestionArtifact:
        """Start the audio ingestion component."""

        try:
            logger.info(
                "Entered the start_audio_ingestion method " "of TrainingPipeline class"
            )

            audio_ingestion = AudioIngestion(
                audio_ingestion_config=self.audio_ingestion_config
            )
            audio_ingestion_artifact = audio_ingestion.initiate_audio_ingestion(
                video_url=video_url
            )

            logger.info(
                "Exited the start_audio_ingestion method " "of TrainingPipeline class"
            )
            return audio_ingestion_artifact

        except Exception as e:
            raise MyException(e, sys) from e

    def start_audio_transcription(
        self, audio_ingestion_artifact: AudioIngestionArtifact
    ) -> AudioTranscriptionArtifact:
        """Start the audio transcription component."""

        try:
            logger.info(
                "Entered the start_audio_transcription method "
                "of TrainingPipeline class"
            )

            audio_transcription = AudioTranscription(
                audio_ingestion_artifact=audio_ingestion_artifact,
                audio_transcription_config=self.audio_transcription_config,
            )

            audio_transcription_artifact = (
                audio_transcription.initiate_audio_transcription()
            )

            logger.info(
                "Exited the start_audio_transcription method "
                "of TrainingPipeline class"
            )

            return audio_transcription_artifact

        except Exception as e:
            raise MyException(e, sys) from e

    def start_text_processing(
        self,
        audio_transcription_artifact: AudioTranscriptionArtifact,
    ) -> TextProcessingArtifact:
        """Start the text processing component."""

        try:
            logger.info("Entered start_text_processing method")
            text_processing = TextProcessing(
                audio_transcription_artifact=audio_transcription_artifact,
                text_processing_config=self.text_processing_config,
            )

            text_processing_artifact = text_processing.initiate_text_processing()
            logger.info("Exited start_text_processing method")
            return text_processing_artifact

        except Exception as e:
            raise MyException(e, sys) from e

    def start_timestamp_generation(
        self,
        audio_transcription_artifact: AudioTranscriptionArtifact,
    ) -> TimestampArtifact:
        try:
            logger.info("Starting timestamp generation")

            timestamp_config = TimestampConfig()

            timestamp_generator = TimestampGenerator(
                audio_transcription_artifact=audio_transcription_artifact,
                timestamp_config=timestamp_config,
                llm=self.llm,
            )

            artifact = timestamp_generator.initiate_timestamp_generation()

            logger.info("Timestamp generation completed successfully")

            return artifact

        except Exception as e:
            raise MyException(e, sys) from e
