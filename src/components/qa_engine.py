import sys
import faiss
from sentence_transformers import SentenceTransformer

from src.entity.config_entity import EmbeddingConfig
from src.entity.artifact_entity import EmbeddingArtifact
from src.exception import MyException
from src.logger import logger
from src.prompts import Prompt
from src.utils.main_utils import load_json, format_timestamp


class QAEngine:
    """Answers questions about a video by retrieving the most relevant
    transcript chunks and passing them to an LLM, along with timestamps."""

    def __init__(
        self,
        embedding_artifact: EmbeddingArtifact,
        embedding_config: EmbeddingConfig,
        llm,
    ):
        """
        Load the FAISS index, chunk metadata, and embedding model once,
        so repeated questions in a session don't reload anything.

        Args:
            embedding_artifact: Output of the embedding indexing stage,
                pointing to the FAISS index and chunk metadata.
            embedding_config: Configuration for the embedding model and
                number of chunks to retrieve per query.
            llm: A LangChain-compatible chat model exposing `.invoke()`.
        """
        try:
            logger.info("Initializing QAEngine")

            self.embedding_config = embedding_config
            self.llm = llm

            self.model = SentenceTransformer(embedding_config.model_name)
            self.index = faiss.read_index(embedding_artifact.index_file_path)
            self.chunks = load_json(embedding_artifact.metadata_file_path)["chunks"]

            logger.info("QAEngine initialized successfully")

        except Exception as e:
            raise MyException(e, sys) from e

    def retrieve_top_chunks(self, question: str) -> list:
        """
        Embed the question and retrieve the top-k most similar chunks
        from the FAISS index.

        Args:
            question: The user's question, in natural language.

        Returns:
            A list of the top-k matching chunk dicts (at most
            `embedding_config.top_k`, typically 2).

        Raises:
            MyException: If retrieval fails.
        """
        try:
            query_vector = self.model.encode(
                [question], convert_to_numpy=True
            ).astype("float32")

            _distances, indices = self.index.search(
                query_vector, self.embedding_config.top_k
            )

            return [self.chunks[i] for i in indices[0] if i != -1]

        except Exception as e:
            raise MyException(e, sys) from e

    def answer_question(self, question: str) -> dict:
        """
        Answer a question about the video using retrieval-augmented
        generation over the transcript chunks.

        Args:
            question: The user's question, in natural language.

        Returns:
            A dict with `answer` (str) and `sources` (list of
            `{start_time, end_time}` dicts the answer was drawn from).

        Raises:
            MyException: If retrieval or generation fails.
        """
        try:
            logger.info(f"Answering question: {question}")

            chunks = self.retrieve_top_chunks(question)
            if not chunks:
                return {"answer": "No relevant information found in this video.", "sources": []}

            context = "\n\n".join(
                f"[{format_timestamp(chunk['start_time'])}] {chunk['text']}"
                for chunk in chunks
            )
            prompt = Prompt.qa_prompt.format(context=context, question=question)

            response = self.llm.invoke(prompt)

            sources = [
                {
                    "start_time": format_timestamp(chunk["start_time"]),
                    "end_time": format_timestamp(chunk["end_time"]),
                }
                for chunk in chunks
            ]

            return {"answer": response.content.strip(), "sources": sources}

        except Exception as e:
            raise MyException(e, sys) from e