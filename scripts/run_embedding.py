import sys

from src.utils.main_utils import (
    load_artifact_json,
    save_artifact_json,
)
from src.entity.artifact_entity import TextProcessingArtifact
from src.pipeline.video_pipeline import VideoPipeline
from src.exception import MyException
from src.logger import logger


def main():
    try:
        logger.info("Running embedding stage")
        text_processing_dict = load_artifact_json("text_processing")

        text_processing_artifact = TextProcessingArtifact(
            **text_processing_dict
        )

        pipeline = VideoPipeline()
        artifact = pipeline.start_embedding_indexing(
            text_processing_artifact=text_processing_artifact
        )

        save_artifact_json(
            "embedding",
            {
                "index_file_path": artifact.index_file_path,
                "metadata_file_path": artifact.metadata_file_path,
            },
        )

        logger.info("embedding stage completed successfully")

    except Exception as e:
        logger.error(f"embedding stage failed: {e}")
        raise MyException(e, sys) from e


if __name__ == "__main__":
    main()