from dataclasses import dataclass

from dataclasses import dataclass


@dataclass
class AudioIngestionArtifact:
    audio_file_path: str
    audio_chunks_dir: str
    video_metadata_file_path: str
    chunk_durations: int

@dataclass
class AudioTranscriptionArtifact:
    transcript_file_path: str

@dataclass
class TextProcessingArtifact:
    text_chunks_dir: str

@dataclass
class TimestampArtifact:
    timestamp_file_path: str

@dataclass
class SummaryArtifact:
    summary_file_path: str