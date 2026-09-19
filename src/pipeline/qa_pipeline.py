import sys
from src.components.qa_engine import QAEngine
from src.llm.llm_client import LLMClient
from src.entity.config_entity import EmbeddingConfig
from src.entity.artifact_entity import EmbeddingArtifact
from src.exception import MyException
from src.logger import logger


class QAPipeline:
    """Loads a video's embedding index and answers questions about it,
    reusing the same loaded index and model across multiple questions."""

    def __init__(self, embedding_artifact: EmbeddingArtifact):
        """
        Initialize the Q&A pipeline by loading the FAISS index, chunk
        metadata, and embedding model once for reuse across questions.

        Args:
            embedding_artifact: Output of the embedding indexing stage,
                pointing to the FAISS index and chunk metadata for the
                video being queried.
        """
        try:
            logger.info("Initializing QAPipeline")

            self.embedding_config = EmbeddingConfig()
            self.llm = LLMClient().get_llm()

            self.qa_engine = QAEngine(
                embedding_artifact=embedding_artifact,
                embedding_config=self.embedding_config,
                llm=self.llm,
            )

            logger.info("QAPipeline initialized successfully")

        except Exception as e:
            raise MyException(e, sys) from e

    def ask(self, question: str) -> dict:
        """
        Answer a question about the video.

        Args:
            question: The user's question, in natural language.

        Returns:
            A dict with `answer` (str) and `sources` (list of
            `{start_time, end_time}` dicts the answer was drawn from).
        """
        try:
            logger.info("Entered the ask method of QAPipeline class")

            result = self.qa_engine.answer_question(question)

            logger.info("Exited the ask method of QAPipeline class")
            return result

        except Exception as e:
            raise MyException(e, sys) from e