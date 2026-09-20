import os
from dotenv import load_dotenv

load_dotenv()

# --- Pipeline ---
PIPELINE_NAME: str = "VideoMind"
ARTIFACT_DIR: str = "artifact"

# --- Audio Ingestion ---
AUDIO_INGESTION_DIR: str = "audio_ingestion"
AUDIO_DIR: str = "audio"
AUDIO_CHUNKS_DIR: str = "chunks"
AUDIO_FILE_NAME: str = "input_audio.mp3"
VIDEO_METADATA_FILE_NAME: str = "video_data.json"
VIDEO_URL: str = "https://www.youtube.com/shorts/-YHNCLTh1Gk"
CHUNKS_DURATION: int = 60

# --- Audio Transcription ---
WHISPER_MODEL_NAME: str = "whisper-large-v3-turbo"
TRANSCRIPTION_MAX_RETRIES: int = 3
TRANSCRIPTION_RETRY_DELAY: float = 2.0
AUDIO_TRANSCRIPTION_DIR: str = "audio_transcription"
TRANSCRIPT_FILE_NAME: str = "transcript.json"

# --- Text Processing ---
TEXT_PROCESSING_DIR: str = "text_processing"
TEXT_CHUNKS_DIR: str = "text_chunks"
CHUNK_SIZE: int = 4000
CHUNK_OVERLAP: int = 200

# --- Timestamp Generation ---
TIMESTAMP_DIR: str = "timestamp"
TIMESTAMP_FILE_NAME: str = "timestamp.json"
MAX_CHARS_PER_TIMESTAMP_BATCH: int = 8000
MAX_LLM_RETRIES: int = 3
LLM_RETRY_DELAY: float = 2.0

# --- Summary Generation ---
SUMMARY_DIR: str = "summary"
SUMMARY_FILE_NAME: str = "summary.json"
MAX_CHARS_PER_SUMMARY_BATCH: int = 8000

# --- Embedding / Q&A ---
EMBEDDING_DIR: str = "embedding"
EMBEDDING_INDEX_FILE_NAME: str = "index.faiss"
EMBEDDING_METADATA_FILE_NAME: str = "metadata.json"
EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
QA_TOP_K: int = 2

# --- Application ---
APP_HOST: str = "0.0.0.0"
APP_PORT: int = 5000