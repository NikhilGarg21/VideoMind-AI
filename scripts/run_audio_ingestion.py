import sys
from src.pipeline.video_pipeline import VideoPipeline
from src.constants import VIDEO_URL
from src.exception import MyException
from src.logger import logger
from src.utils.main_utils import save_artifact_json

def main():
    try:
        logger.info(f"Running audio_ingestion stage for URL: {VIDEO_URL}")
        pipeline = VideoPipeline()
        artifact = pipeline.start_audio_ingestion(video_url=VIDEO_URL)
        save_artifact_json(
            "audio_ingestion",
            {
                "audio_file_path": artifact.audio_file_path,
                "audio_chunks_dir": artifact.audio_chunks_dir,
                "video_metadata_file_path": artifact.video_metadata_file_path,
                "chunk_durations": artifact.chunk_durations
            },
        )

        logger.info("audio_ingestion stage completed successfully")

    except Exception as e:
        logger.error(f"audio_ingestion stage failed: {e}")
        raise MyException(e, sys) from e


if __name__ == "__main__":
    main()
