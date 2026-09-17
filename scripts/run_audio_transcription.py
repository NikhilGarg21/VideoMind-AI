import sys

from src.utils.main_utils import (
    load_artifact_json,
    save_artifact_json,
)

from src.entity.artifact_entity import AudioIngestionArtifact
from src.pipeline.video_pipeline import VideoPipeline
from src.exception import MyException
from src.logger import logger


def main():
    try:
        logger.info("Running audio_transcription stage")
        audio_ingestion_dict = load_artifact_json("audio_ingestion")
        audio_ingestion_artifact = AudioIngestionArtifact(**audio_ingestion_dict)

        pipeline = VideoPipeline()
        artifact = pipeline.start_audio_transcription(
            audio_ingestion_artifact=audio_ingestion_artifact
        )

        save_artifact_json(
            "audio_transcription",
            {
                "transcript_file_path": artifact.transcript_file_path,
            },
        )
        logger.info("audio_transcription stage completed successfully")

    except Exception as e:
        logger.error(f"audio_transcription stage failed: {e}")

        raise MyException(e, sys) from e


if __name__ == "__main__":
    main()
