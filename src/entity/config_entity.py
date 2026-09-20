import os
from dataclasses import dataclass, field

from src.constants import *


@dataclass
class VideoPipelineConfig:
    pipeline_name: str = PIPELINE_NAME
    artifact_dir: str = ARTIFACT_DIR


video_pipeline_config = VideoPipelineConfig()


@dataclass
class AudioIngestionConfig:
    artifact_dir: str = video_pipeline_config.artifact_dir
    chunk_duration: int = CHUNKS_DURATION

    audio_ingestion_dir: str = field(init=False)
    audio_path: str = field(init=False)
    audio_chunks_dir: str = field(init=False)
    video_metadata_file_path: str = field(init=False)

    def __post_init__(self):
        self.audio_ingestion_dir = os.path.join(
            self.artifact_dir,
            AUDIO_INGESTION_DIR,
        )

        self.audio_path = os.path.join(
            self.audio_ingestion_dir,
            AUDIO_DIR,
            AUDIO_FILE_NAME,
        )

        self.audio_chunks_dir = os.path.join(
            self.audio_ingestion_dir,
            AUDIO_CHUNKS_DIR,
        )

        self.video_metadata_file_path = os.path.join(
            self.audio_ingestion_dir,
            VIDEO_METADATA_FILE_NAME,
        )


@dataclass
class AudioTranscriptionConfig:
    artifact_dir: str = video_pipeline_config.artifact_dir

    model_name: str = WHISPER_MODEL_NAME
    max_retries: int = TRANSCRIPTION_MAX_RETRIES
    retry_delay: float = TRANSCRIPTION_RETRY_DELAY

    audio_transcription_dir: str = field(init=False)
    transcript_file_path: str = field(init=False)

    def __post_init__(self):
        self.audio_transcription_dir = os.path.join(
            self.artifact_dir,
            AUDIO_TRANSCRIPTION_DIR,
        )

        self.transcript_file_path = os.path.join(
            self.audio_transcription_dir,
            TRANSCRIPT_FILE_NAME,
        )


@dataclass
class TextProcessingConfig:
    artifact_dir: str = video_pipeline_config.artifact_dir

    chunk_size: int = CHUNK_SIZE
    chunk_overlap: int = CHUNK_OVERLAP

    text_processing_dir: str = field(init=False)
    text_chunks_dir: str = field(init=False)

    def __post_init__(self):
        self.text_processing_dir = os.path.join(
            self.artifact_dir,
            TEXT_PROCESSING_DIR,
        )

        self.text_chunks_dir = os.path.join(
            self.text_processing_dir,
            TEXT_CHUNKS_DIR,
        )


@dataclass
class TimestampConfig:
    artifact_dir: str = video_pipeline_config.artifact_dir

    max_chars_per_batch: int = MAX_CHARS_PER_TIMESTAMP_BATCH
    max_retries: int = MAX_LLM_RETRIES
    retry_delay: float = LLM_RETRY_DELAY

    timestamp_dir: str = field(init=False)
    timestamp_file_path: str = field(init=False)

    def __post_init__(self):
        self.timestamp_dir = os.path.join(
            self.artifact_dir,
            TIMESTAMP_DIR,
        )

        self.timestamp_file_path = os.path.join(
            self.timestamp_dir,
            TIMESTAMP_FILE_NAME,
        )


@dataclass
class SummaryConfig:
    artifact_dir: str = video_pipeline_config.artifact_dir

    max_chars_per_batch: int = MAX_CHARS_PER_SUMMARY_BATCH
    max_retries: int = MAX_LLM_RETRIES
    retry_delay: float = LLM_RETRY_DELAY

    summary_dir: str = field(init=False)
    summary_file_path: str = field(init=False)

    def __post_init__(self):
        self.summary_dir = os.path.join(
            self.artifact_dir,
            SUMMARY_DIR,
        )

        self.summary_file_path = os.path.join(
            self.summary_dir,
            SUMMARY_FILE_NAME,
        )


@dataclass
class EmbeddingConfig:
    artifact_dir: str = video_pipeline_config.artifact_dir

    model_name: str = EMBEDDING_MODEL_NAME
    top_k: int = QA_TOP_K

    embedding_dir: str = field(init=False)
    index_file_path: str = field(init=False)
    metadata_file_path: str = field(init=False)

    def __post_init__(self):
        self.embedding_dir = os.path.join(
            self.artifact_dir,
            EMBEDDING_DIR,
        )

        self.index_file_path = os.path.join(
            self.embedding_dir,
            EMBEDDING_INDEX_FILE_NAME,
        )

        self.metadata_file_path = os.path.join(
            self.embedding_dir,
            EMBEDDING_METADATA_FILE_NAME,
        )