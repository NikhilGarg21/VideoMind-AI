import sys

import faiss
import numpy as np

from src.entity.artifact_entity import EmbeddingArtifact
from src.entity.config_entity import EmbeddingConfig
from src.exception import MyException
from src.logger import logger
from src.prompts import Prompt
from src.utils.hf_embeddings import embed_texts
from src.utils.main_utils import (
    format_timestamp,
    load_json,
)


class QAEngine:
    """
    Answers questions about a video by retrieving the most relevant
    transcript chunks and passing them to an LLM, along with timestamps.
    """

    def __init__(
        self,
        embedding_artifact: EmbeddingArtifact,
        embedding_config: EmbeddingConfig,
        llm,
    ):
        """
        Load the FAISS index and chunk metadata once so repeated questions
        in the same job/session do not reload them.

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

            logger.info("Loading FAISS index")

            self.index = faiss.read_index(embedding_artifact.index_file_path)

            logger.info("Loading embedding metadata")

            metadata = load_json(embedding_artifact.metadata_file_path)

            self.chunks = metadata.get(
                "chunks",
                [],
            )

            if not self.chunks:
                raise ValueError("Embedding metadata contains no chunks")

            if self.index.ntotal == 0:
                raise ValueError("FAISS index contains no vectors")

            if self.index.ntotal != len(self.chunks):
                raise ValueError("FAISS index size does not match metadata chunk count")

            logger.info(f"Loaded FAISS index with " f"{self.index.ntotal} vectors")

            logger.info(f"Loaded {len(self.chunks)} metadata chunks")

            logger.info("QAEngine initialized successfully")

        except Exception as e:
            raise MyException(e, sys) from e

    def retrieve_top_chunks(
        self,
        question: str,
    ) -> list:
        """
        Embed the question and retrieve the top-k most similar chunks
        from the FAISS index.

        Args:
            question: The user's question in natural language.

        Returns:
            A list of matching chunk dicts.

        Raises:
            MyException: If retrieval fails.
        """
        try:
            if not question or not question.strip():
                raise ValueError("Question cannot be empty")

            top_k = min(
                self.embedding_config.top_k,
                self.index.ntotal,
            )

            if top_k <= 0:
                return []

            logger.info(f"Retrieving top {top_k} chunks")

            query_embedding = embed_texts(
                [question.strip()],
                self.embedding_config.model_name,
            )

            query_vector = np.asarray(
                query_embedding,
                dtype="float32",
            )

            _distances, indices = self.index.search(
                query_vector,
                top_k,
            )

            retrieved_chunks = []

            for index in indices[0]:
                index = int(index)

                if index == -1:
                    continue

                if 0 <= index < len(self.chunks):
                    retrieved_chunks.append(self.chunks[index])

            logger.info(f"Retrieved {len(retrieved_chunks)} relevant chunks")

            return retrieved_chunks

        except Exception as e:
            raise MyException(e, sys) from e

    def build_context(
        self,
        chunks: list,
    ) -> str:
        """
        Build the context passed to the LLM from retrieved chunks.
        """
        try:
            return "\n\n".join(
                (f"[{format_timestamp(chunk['start_time'])}] " f"{chunk['text']}")
                for chunk in chunks
            )

        except Exception as e:
            raise MyException(e, sys) from e

    def build_sources(
        self,
        chunks: list,
    ) -> list:
        """
        Build timestamp sources for the API response.
        """
        try:
            return [
                {
                    "start_time": format_timestamp(chunk["start_time"]),
                    "end_time": format_timestamp(chunk["end_time"]),
                }
                for chunk in chunks
            ]

        except Exception as e:
            raise MyException(e, sys) from e

    def answer_question(
        self,
        question: str,
    ) -> dict:
        """
        Answer a question about the video using retrieval-augmented
        generation over the transcript chunks.

        Args:
            question: The user's question.

        Returns:
            A dict containing:
                - answer: Generated answer text.
                - sources: Timestamp ranges used for the answer.

        Raises:
            MyException: If retrieval or generation fails.
        """
        try:
            logger.info(f"Answering question: {question}")

            chunks = self.retrieve_top_chunks(question)

            if not chunks:
                logger.info("No relevant chunks found")

                return {
                    "answer": ("No relevant information found " "in this video."),
                    "sources": [],
                }

            context = self.build_context(chunks)

            prompt = Prompt.qa_prompt.format(
                context=context,
                question=question,
            )

            logger.info("Sending retrieved context to LLM")

            response = self.llm.invoke(prompt)

            sources = self.build_sources(chunks)

            logger.info("Question answered successfully")

            return {
                "answer": response.content.strip(),
                "sources": sources,
            }

        except Exception as e:
            raise MyException(e, sys) from e
