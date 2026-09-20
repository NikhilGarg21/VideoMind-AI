import gc
import os
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
    """
    Orchestrates the full VideoMind pipeline.

    Improvements:
    - Supports a job-specific artifact directory.
    - LLM is initialized lazily.
    - Stage objects are released after their work is finished.
    - LLM is released immediately after the last LLM-dependent stage.
    - Heavy garbage collection is performed at useful stage boundaries.

    Existing pipeline behavior is preserved.
    """

    def __init__(
        self,
        artifact_dir: str | None = None,
    ):
        """
        Initialize pipeline configurations.

        Args:
            artifact_dir:
                Optional root directory for this pipeline's artifacts.

                Example:
                    artifact/jobs/abc123

                If omitted, the existing default:
                    artifact
                is used.
        """

        try:
            logger.info("Initializing VideoPipeline")

            # ----------------------------------------------------------
            # Artifact isolation
            # ----------------------------------------------------------

            if artifact_dir is None:
                artifact_dir = "artifact"

            self.artifact_dir = os.path.abspath(artifact_dir)

            os.makedirs(
                self.artifact_dir,
                exist_ok=True,
            )

            logger.info(f"Pipeline artifact directory: " f"{self.artifact_dir}")

            # ----------------------------------------------------------
            # Job-specific configurations
            # ----------------------------------------------------------

            self.audio_ingestion_config = AudioIngestionConfig(
                artifact_dir=self.artifact_dir
            )

            self.audio_transcription_config = AudioTranscriptionConfig(
                artifact_dir=self.artifact_dir
            )

            self.text_processing_config = TextProcessingConfig(
                artifact_dir=self.artifact_dir
            )

            self.timestamp_config = TimestampConfig(artifact_dir=self.artifact_dir)

            self.summary_config = SummaryConfig(artifact_dir=self.artifact_dir)

            self.embedding_config = EmbeddingConfig(artifact_dir=self.artifact_dir)

            # ----------------------------------------------------------
            # Lazy LLM
            # ----------------------------------------------------------

            # Do NOT initialize the LLM here.
            self.llm = None

            logger.info("VideoPipeline initialized successfully")

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

    # ------------------------------------------------------------------
    # LLM lifecycle
    # ------------------------------------------------------------------

    def get_llm(self):
        """
        Lazily create and reuse the LLM.

        The LLM is only needed by:
        - timestamp generation
        - summary generation
        """

        try:

            if self.llm is None:

                logger.info("Initializing LLM lazily")

                self.llm = LLMClient().get_llm()

                logger.info("LLM initialized successfully")

            return self.llm

        except Exception as e:

            raise MyException(
                e,
                sys,
            ) from e

    def release_llm(self) -> None:
        """
        Release the pipeline's LLM reference.

        Called after summary generation because summary is
        the last stage that needs the LLM.
        """

        try:

            if self.llm is not None:

                logger.info("Releasing pipeline LLM")

                self.llm = None

                gc.collect()

                logger.info("Pipeline LLM released")

        except Exception as e:

            logger.warning(f"Could not fully release LLM: {e}")

    # ------------------------------------------------------------------
    # Pipeline cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """
        Release pipeline-level references.

        The actual artifacts on disk are intentionally preserved
        because later Q&A depends on the embedding artifacts.
        """

        try:

            self.release_llm()

            # Remove references to configuration objects.
            # The job artifacts themselves remain on disk.
            self.audio_ingestion_config = None
            self.audio_transcription_config = None
            self.text_processing_config = None
            self.timestamp_config = None
            self.summary_config = None
            self.embedding_config = None

            gc.collect()

            logger.info("VideoPipeline resources released")

        except Exception as e:

            logger.warning(f"VideoPipeline cleanup failed: {e}")

    # ------------------------------------------------------------------
    # Audio ingestion
    # ------------------------------------------------------------------

    def start_audio_ingestion(
        self,
        video_url: str,
    ) -> AudioIngestionArtifact:
        """
        Run the audio ingestion stage.

        Returns:
            AudioIngestionArtifact
        """

        audio_ingestion = None

        try:

            logger.info(
                "Entered the start_audio_ingestion " "method of VideoPipeline class"
            )

            audio_ingestion = AudioIngestion(
                audio_ingestion_config=(self.audio_ingestion_config)
            )

            audio_ingestion_artifact = audio_ingestion.initiate_audio_ingestion(
                video_url=video_url
            )

            logger.info(
                "Exited the start_audio_ingestion " "method of VideoPipeline class"
            )

            return audio_ingestion_artifact

        except Exception as e:

            raise MyException(
                e,
                sys,
            ) from e

        finally:

            audio_ingestion = None

    # ------------------------------------------------------------------
    # Audio transcription
    # ------------------------------------------------------------------

    def start_audio_transcription(
        self,
        audio_ingestion_artifact: AudioIngestionArtifact,
    ) -> AudioTranscriptionArtifact:
        """
        Run the audio transcription stage.

        Returns:
            AudioTranscriptionArtifact
        """

        audio_transcription = None

        try:

            logger.info(
                "Entered the start_audio_transcription " "method of VideoPipeline class"
            )

            audio_transcription = AudioTranscription(
                audio_ingestion_artifact=(audio_ingestion_artifact),
                audio_transcription_config=(self.audio_transcription_config),
            )

            audio_transcription_artifact = (
                audio_transcription.initiate_audio_transcription()
            )

            logger.info(
                "Exited the start_audio_transcription " "method of VideoPipeline class"
            )

            return audio_transcription_artifact

        except Exception as e:

            raise MyException(
                e,
                sys,
            ) from e

        finally:

            audio_transcription = None

            # Transcription can hold relatively large
            # temporary Python objects.
            gc.collect()

    # ------------------------------------------------------------------
    # Text processing
    # ------------------------------------------------------------------

    def start_text_processing(
        self,
        audio_transcription_artifact: AudioTranscriptionArtifact,
    ) -> TextProcessingArtifact:
        """
        Run the text processing stage.

        Returns:
            TextProcessingArtifact
        """

        text_processing = None

        try:

            logger.info(
                "Entered the start_text_processing " "method of VideoPipeline class"
            )

            text_processing = TextProcessing(
                audio_transcription_artifact=(audio_transcription_artifact),
                text_processing_config=(self.text_processing_config),
            )

            text_processing_artifact = text_processing.initiate_text_processing()

            logger.info(
                "Exited the start_text_processing " "method of VideoPipeline class"
            )

            return text_processing_artifact

        except Exception as e:

            raise MyException(
                e,
                sys,
            ) from e

        finally:

            text_processing = None

            gc.collect()

    # ------------------------------------------------------------------
    # Timestamp generation
    # ------------------------------------------------------------------

    def start_timestamp_generation(
        self,
        audio_transcription_artifact: AudioTranscriptionArtifact,
    ) -> TimestampArtifact:
        """
        Run semantic timestamp/chapter generation.

        This is the first stage that needs the LLM.
        """

        timestamp_generator = None

        try:

            logger.info(
                "Entered the start_timestamp_generation "
                "method of VideoPipeline class"
            )

            timestamp_generator = TimestampGenerator(
                audio_transcription_artifact=(audio_transcription_artifact),
                timestamp_config=(self.timestamp_config),
                llm=self.get_llm(),
            )

            artifact = timestamp_generator.initiate_timestamp_generation()

            logger.info(
                "Exited the start_timestamp_generation " "method of VideoPipeline class"
            )

            return artifact

        except Exception as e:

            raise MyException(
                e,
                sys,
            ) from e

        finally:

            timestamp_generator = None

            gc.collect()

    # ------------------------------------------------------------------
    # Summary generation
    # ------------------------------------------------------------------

    def start_summary_generation(
        self,
        audio_transcription_artifact: AudioTranscriptionArtifact,
    ) -> SummaryArtifact:
        """
        Run summary generation.

        This is the last pipeline stage that needs the LLM,
        so the LLM is released immediately afterward.
        """

        summary_generator = None

        try:

            logger.info(
                "Entered the start_summary_generation " "method of VideoPipeline class"
            )

            summary_generator = SummaryGenerator(
                audio_transcription_artifact=(audio_transcription_artifact),
                summary_config=(self.summary_config),
                llm=self.get_llm(),
            )

            artifact = summary_generator.initiate_summary_generation()

            logger.info(
                "Exited the start_summary_generation " "method of VideoPipeline class"
            )

            return artifact

        except Exception as e:

            raise MyException(
                e,
                sys,
            ) from e

        finally:

            summary_generator = None

            # Summary is the final LLM-dependent stage.
            self.release_llm()

            gc.collect()

    # ------------------------------------------------------------------
    # Embedding indexing
    # ------------------------------------------------------------------

    def start_embedding_indexing(
        self,
        text_processing_artifact: TextProcessingArtifact,
    ) -> EmbeddingArtifact:
        """
        Run embedding generation and FAISS indexing.

        Returns:
            EmbeddingArtifact
        """

        embedding_indexer = None

        try:

            logger.info(
                "Entered the start_embedding_indexing " "method of VideoPipeline class"
            )

            embedding_indexer = EmbeddingIndexer(
                text_processing_artifact=(text_processing_artifact),
                embedding_config=(self.embedding_config),
            )

            artifact = embedding_indexer.initiate_embedding_indexing()

            logger.info(
                "Exited the start_embedding_indexing " "method of VideoPipeline class"
            )

            return artifact

        except Exception as e:

            raise MyException(
                e,
                sys,
            ) from e

        finally:

            embedding_indexer = None

            # FAISS / embedding stage can create sizeable
            # temporary NumPy arrays.
            gc.collect()
