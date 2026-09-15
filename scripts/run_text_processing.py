import sys
import os

from src.utils.dvc_utils import (
    load_artifact_json,
    save_artifact_json,
)

from src.entity.artifact_entity import (
    AudioTranscriptionArtifact,
)

from src.pipeline.video_pipeline import VideoPipeline
from src.exception import MyException
from src.logger import logger


def main():
    """Run the text processing DVC stage."""

    try:
        logger.info("Running text_processing stage")
        audio_transcription_dict = load_artifact_json("audio_transcription")

        audio_transcription_artifact = AudioTranscriptionArtifact(
            **audio_transcription_dict
        )

        pipeline = VideoPipeline()
        artifact = pipeline.start_text_processing(
            audio_transcription_artifact=audio_transcription_artifact
        )

        save_artifact_json(
            "text_processing",
            {
                "text_chunks_dir": artifact.text_chunks_dir,
            },
        )

        logger.info("text_processing stage completed successfully")


    except Exception as e:
        logger.error(f"text_processing stage failed: {e}")
        raise MyException(e, sys) from e


if __name__ == "__main__":
    main()
