import os
from dataclasses import dataclass
from src.constants import *


@dataclass
class VideoPipelineConfig:
    pipeline_name: str = PIPELINE_NAME
    artifact_dir: str = ARTIFACT_DIR


video_pipeline_config = VideoPipelineConfig()


@dataclass
class AudioIngestionConfig:
    audio_ingestion_dir: str = os.path.join(
        video_pipeline_config.artifact_dir,
        AUDIO_INGESTION_DIR,
    )

    audio_path: str = os.path.join(
        audio_ingestion_dir,
        AUDIO_DIR,
        AUDIO_FILE_NAME,
    )

    audio_chunks_dir: str = os.path.join(
        audio_ingestion_dir,
        AUDIO_CHUNKS_DIR,
    )

    video_metadata_file_path: str = os.path.join(
        audio_ingestion_dir,
        VIDEO_METADATA_FILE_NAME,
    )


@dataclass
class AudioTranscriptionConfig:
    audio_transcription_dir: str = os.path.join(
        video_pipeline_config.artifact_dir,
        AUDIO_TRANSCRIPTION_DIR,
    )
    transcript_file_path: str = os.path.join(
        audio_transcription_dir,
        TRANSCRIPT_FILE_NAME,
    )


@dataclass
class TextProcessingConfig:
    text_processing_dir: str = os.path.join(
        video_pipeline_config.artifact_dir,
        TEXT_PROCESSING_DIR,
    )
    text_chunks_dir: str = os.path.join(
        text_processing_dir,
        TEXT_CHUNKS_DIR,
    )
    chunk_size: int = CHUNK_SIZE
    chunk_overlap: int = CHUNK_OVERLAP


@dataclass
class TimestampConfig:
    timestamp_dir: str = os.path.join(
        video_pipeline_config.artifact_dir,
        TIMESTAMP_DIR,
    )
    timestamp_file_path: str = os.path.join(
        timestamp_dir,
        TIMESTAMP_FILE_NAME,
    )
    max_chars_per_batch: int = MAX_CHARS_PER_TIMESTAMP_BATCH
