import sys

from src.utils.main_utils import (
    load_artifact_json,
    save_artifact_json,
)
from src.entity.artifact_entity import AudioTranscriptionArtifact
from src.pipeline.video_pipeline import VideoPipeline
from src.exception import MyException
from src.logger import logger


def main():
    try:
        logger.info("Running summary stage")
        audio_transcription_dict = load_artifact_json("audio_transcription")

        audio_transcription_artifact = AudioTranscriptionArtifact(
            **audio_transcription_dict
        )

        pipeline = VideoPipeline()
        artifact = pipeline.start_summary_generation(
            audio_transcription_artifact=audio_transcription_artifact
        )

        save_artifact_json(
            "summary",
            {
                "summary_file_path": artifact.summary_file_path,
            },
        )
        logger.info("summary stage completed successfully")

    except Exception as e:
        logger.error(f"summary stage failed: {e}")
        raise MyException(e, sys) from e


if __name__ == "__main__":
    main()