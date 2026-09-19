import sys
from src.components.audio_ingestion import AudioIngestion
from src.components.audio_transcription import AudioTranscription
from src.components.text_processing import TextProcessing
from src.components.timestamps import TimestampGenerator
from src.components.summary import SummaryGenerator
from src.components.embedding_indexer import EmbeddingIndexer
from src.llm.llm_client import LLMClient
from src.entity.config_entity import (
    AudioIngestionConfig,
    AudioTranscriptionConfig,
    TextProcessingConfig,
    TimestampConfig,
    SummaryConfig,
    EmbeddingConfig,
)

from src.entity.artifact_entity import (
    AudioIngestionArtifact,
    AudioTranscriptionArtifact,
    TextProcessingArtifact,
    TimestampArtifact,
    SummaryArtifact,
    EmbeddingArtifact,
)

from src.exception import MyException
from src.logger import logger


class VideoPipeline:
    """Orchestrates the full video processing pipeline: audio ingestion,
    transcription, text chunking, timestamp generation, summarization,
    and embedding indexing for Q&A."""

    def __init__(self):
        """Initialize all stage configurations and the shared LLM client."""
        try:
            self.audio_ingestion_config = AudioIngestionConfig()
            self.audio_transcription_config = AudioTranscriptionConfig()
            self.text_processing_config = TextProcessingConfig()
            self.timestamp_config = TimestampConfig()
            self.summary_config = SummaryConfig()
            self.embedding_config = EmbeddingConfig()
            self.llm = LLMClient().get_llm()

        except Exception as e:
            raise MyException(e, sys) from e

    def start_audio_ingestion(self, video_url: str) -> AudioIngestionArtifact:
        """
        Run the audio ingestion stage: download and chunk the video's audio.

        Args:
            video_url: The source video URL to ingest.

        Returns:
            An AudioIngestionArtifact with paths to the downloaded audio,
            chunks, and metadata.
        """
        try:
            logger.info("Entered the start_audio_ingestion method of VideoPipeline class")

            audio_ingestion = AudioIngestion(
                audio_ingestion_config=self.audio_ingestion_config
            )
            audio_ingestion_artifact = audio_ingestion.initiate_audio_ingestion(
                video_url=video_url
            )

            logger.info("Exited the start_audio_ingestion method of VideoPipeline class")
            return audio_ingestion_artifact

        except Exception as e:
            raise MyException(e, sys) from e

    def start_audio_transcription(
        self, audio_ingestion_artifact: AudioIngestionArtifact
    ) -> AudioTranscriptionArtifact:
        """
        Run the audio transcription stage: transcribe audio chunks into a
        timestamped transcript.

        Args:
            audio_ingestion_artifact: Output of the audio ingestion stage.

        Returns:
            An AudioTranscriptionArtifact pointing to the saved transcript.
        """
        try:
            logger.info("Entered the start_audio_transcription method of VideoPipeline class")

            audio_transcription = AudioTranscription(
                audio_ingestion_artifact=audio_ingestion_artifact,
                audio_transcription_config=self.audio_transcription_config,
            )

            audio_transcription_artifact = (
                audio_transcription.initiate_audio_transcription()
            )

            logger.info("Exited the start_audio_transcription method of VideoPipeline class")
            return audio_transcription_artifact

        except Exception as e:
            raise MyException(e, sys) from e

    def start_text_processing(
        self,
        audio_transcription_artifact: AudioTranscriptionArtifact,
    ) -> TextProcessingArtifact:
        """
        Run the text processing stage: split the transcript into
        timestamp-preserving text chunks.

        Args:
            audio_transcription_artifact: Output of the transcription stage.

        Returns:
            A TextProcessingArtifact pointing to the saved text chunks.
        """
        try:
            logger.info("Entered the start_text_processing method of VideoPipeline class")

            text_processing = TextProcessing(
                audio_transcription_artifact=audio_transcription_artifact,
                text_processing_config=self.text_processing_config,
            )

            text_processing_artifact = text_processing.initiate_text_processing()

            logger.info("Exited the start_text_processing method of VideoPipeline class")
            return text_processing_artifact

        except Exception as e:
            raise MyException(e, sys) from e

    def start_timestamp_generation(
        self, audio_transcription_artifact: AudioTranscriptionArtifact
    ) -> TimestampArtifact:
        """
        Run the timestamp generation stage: identify semantic chapters
        and their timestamps using the LLM.

        Args:
            audio_transcription_artifact: Output of the transcription stage.

        Returns:
            A TimestampArtifact pointing to the saved timestamp JSON.
        """
        try:
            logger.info("Entered the start_timestamp_generation method of VideoPipeline class")

            timestamp_generator = TimestampGenerator(
                audio_transcription_artifact=audio_transcription_artifact,
                timestamp_config=self.timestamp_config,
                llm=self.llm,
            )

            artifact = timestamp_generator.initiate_timestamp_generation()

            logger.info("Exited the start_timestamp_generation method of VideoPipeline class")
            return artifact

        except Exception as e:
            raise MyException(e, sys) from e

    def start_summary_generation(
        self,
        audio_transcription_artifact: AudioTranscriptionArtifact,
    ) -> SummaryArtifact:
        """
        Run the summary generation stage: produce a TL;DR and key points
        using map-reduce summarization over the transcript.

        Args:
            audio_transcription_artifact: Output of the transcription stage.

        Returns:
            A SummaryArtifact pointing to the saved summary JSON.
        """
        try:
            logger.info("Entered the start_summary_generation method of VideoPipeline class")

            summary_generator = SummaryGenerator(
                audio_transcription_artifact=audio_transcription_artifact,
                summary_config=self.summary_config,
                llm=self.llm,
            )

            artifact = summary_generator.initiate_summary_generation()

            logger.info("Exited the start_summary_generation method of VideoPipeline class")
            return artifact

        except Exception as e:
            raise MyException(e, sys) from e

    def start_embedding_indexing(
        self,
        text_processing_artifact: TextProcessingArtifact,
    ) -> EmbeddingArtifact:
        """
        Run the embedding indexing stage: embed text chunks and build a
        FAISS index for downstream Q&A retrieval.

        Args:
            text_processing_artifact: Output of the text processing stage.

        Returns:
            An EmbeddingArtifact pointing to the saved FAISS index and
            chunk metadata.
        """
        try:
            logger.info("Entered the start_embedding_indexing method of VideoPipeline class")

            embedding_indexer = EmbeddingIndexer(
                text_processing_artifact=text_processing_artifact,
                embedding_config=self.embedding_config,
            )

            artifact = embedding_indexer.initiate_embedding_indexing()

            logger.info("Exited the start_embedding_indexing method of VideoPipeline class")
            return artifact

        except Exception as e:
            raise MyException(e, sys) from e