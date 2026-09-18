import os
from datetime import date
from dotenv import load_dotenv
load_dotenv()

PIPELINE_NAME: str = "VideoMind"
CURRENT_YEAR = date.today().year

ARTIFACT_DIR = "artifact"

AUDIO_INGESTION_DIR = "audio_ingestion"
AUDIO_DIR = "audio"
AUDIO_CHUNKS_DIR = "chunks"
AUDIO_FILE_NAME = "input_audio.mp3"
VIDEO_METADATA_FILE_NAME = "video_data.json"
VIDEO_URL: str = "https://www.youtube.com/watch?v=5HKaLStWNoc" 
CHUNKS_DURATION = 60


AUDIO_TRANSCRIPTION_DIR = "audio_transcription"
TRANSCRIPT_FILE_NAME = "transcript.jason"


TEXT_PROCESSING_DIR = "text_processing"
TEXT_CHUNKS_DIR = "text_chunks"

CHUNK_SIZE = 4000
CHUNK_OVERLAP = 200

TIMESTAMP_DIR = "timestamp"
TIMESTAMP_FILE_NAME = "timestamp.json"
MAX_CHARS_PER_TIMESTAMP_BATCH: int = 8000  
MAX_LLM_RETRIES = 3
LLM_RETRY_DELAY = 2.0


SUMMARY_DIR = "summary"
SUMMARY_FILE_NAME = "summary.json"
MAX_CHARS_PER_SUMMARY_BATCH: int = 8000

# Application constants
APP_HOST: str = "0.0.0.0"
APP_PORT: int = 5000