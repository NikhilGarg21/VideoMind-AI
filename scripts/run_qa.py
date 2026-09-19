import sys

from src.utils.main_utils import load_artifact_json
from src.entity.artifact_entity import EmbeddingArtifact
from src.pipeline.qa_pipeline import QAPipeline
from src.exception import MyException
from src.logger import logger


def main():
    try:
        logger.info("Starting Q&A session")

        embedding_dict = load_artifact_json("embedding")
        embedding_artifact = EmbeddingArtifact(**embedding_dict)

        qa_pipeline = QAPipeline(embedding_artifact=embedding_artifact)

        print("Ask questions about the video (type 'exit' to quit):")
        while True:
            question = input("\n> ").strip()

            if not question:
                continue

            if question.lower() in ("exit", "quit"):
                break

            result = qa_pipeline.ask(question)

            print(f"\n{result['answer']}")

            if result["sources"]:
                source_str = ", ".join(
                    f"{s['start_time']}-{s['end_time']}" for s in result["sources"]
                )
                print(f"Sources: {source_str}")

        logger.info("Q&A session ended")

    except Exception as e:
        logger.error(f"Q&A session failed: {e}")
        raise MyException(e, sys) from e


if __name__ == "__main__":
    main()