import os
import sys
import json
import gc

import faiss
import numpy as np

from src.utils.hf_embeddings import embed_texts
from src.entity.config_entity import EmbeddingConfig
from src.entity.artifact_entity import (
    TextProcessingArtifact,
    EmbeddingArtifact,
)
from src.exception import MyException
from src.logger import logger
from src.utils.main_utils import save_json


class EmbeddingIndexer:
    """Embeds text chunks and builds a FAISS index for semantic retrieval."""

    BATCH_SIZE = 16

    def __init__(
        self,
        text_processing_artifact: TextProcessingArtifact,
        embedding_config: EmbeddingConfig,
    ):
        """
        Initialize EmbeddingIndexer.

        Args:
            text_processing_artifact: Output of the text processing stage.
            embedding_config: Embedding model and output configuration.
        """
        try:
            self.text_processing_artifact = text_processing_artifact
            self.embedding_config = embedding_config

        except Exception as e:
            raise MyException(e, sys) from e

    def load_text_chunks(self) -> list:
        """
        Load all saved text chunk JSON files.

        Returns:
            List of chunk dictionaries.
        """
        try:
            logger.info("Loading text chunks for embedding")

            text_chunks_dir = (
                self.text_processing_artifact.text_chunks_dir
            )

            if not os.path.exists(text_chunks_dir):
                raise FileNotFoundError(
                    f"Text chunks directory not found: "
                    f"{text_chunks_dir}"
                )

            chunk_files = sorted(
                file_name
                for file_name in os.listdir(text_chunks_dir)
                if file_name.endswith(".json")
            )

            if not chunk_files:
                raise ValueError("No text chunks found")

            chunks = []

            for file_name in chunk_files:
                file_path = os.path.join(
                    text_chunks_dir,
                    file_name,
                )

                with open(
                    file_path,
                    "r",
                    encoding="utf-8",
                ) as file:
                    chunks.append(
                        json.load(file)
                    )

            logger.info(
                f"Loaded {len(chunks)} text chunks"
            )

            return chunks

        except Exception as e:
            raise MyException(e, sys) from e

    def build_and_save_index(
        self,
        chunks: list,
    ) -> tuple:
        """
        Embed chunks in batches and incrementally build FAISS index.

        Returns:
            Tuple of index file path and metadata file path.
        """
        try:
            logger.info(
                f"Using embedding model: "
                f"{self.embedding_config.model_name}"
            )

            total_chunks = len(chunks)

            if total_chunks == 0:
                raise ValueError(
                    "No chunks available for embedding"
                )

            index = None

            logger.info(
                f"Embedding {total_chunks} chunks "
                f"in batches of {self.BATCH_SIZE}"
            )

            for start in range(
                0,
                total_chunks,
                self.BATCH_SIZE,
            ):
                end = min(
                    start + self.BATCH_SIZE,
                    total_chunks,
                )

                batch_chunks = chunks[start:end]

                texts = [
                    chunk["text"]
                    for chunk in batch_chunks
                ]

                logger.info(
                    f"Embedding chunks "
                    f"{start + 1}-{end}/{total_chunks}"
                )

                embeddings = np.asarray(
                    embed_texts(
                        texts,
                        self.embedding_config.model_name,
                    ),
                    dtype="float32",
                )

                if embeddings.ndim != 2:
                    raise ValueError(
                        "Embedding output must be a 2D array"
                    )

                if embeddings.shape[0] != len(texts):
                    raise ValueError(
                        "Number of embeddings does not match "
                        "number of input texts"
                    )

                if index is None:
                    embedding_dimension = (
                        embeddings.shape[1]
                    )

                    index = faiss.IndexFlatL2(
                        embedding_dimension
                    )

                    logger.info(
                        f"Created FAISS IndexFlatL2 "
                        f"with dimension "
                        f"{embedding_dimension}"
                    )

                elif (
                    embeddings.shape[1]
                    != index.d
                ):
                    raise ValueError(
                        "Embedding dimension changed "
                        "between batches"
                    )

                index.add(embeddings)

                logger.info(
                    f"Added batch to FAISS index. "
                    f"Current vectors: {index.ntotal}"
                )

                # Release batch memory immediately.
                del embeddings
                del texts
                del batch_chunks

                gc.collect()

            if index is None or index.ntotal == 0:
                raise ValueError(
                    "FAISS index contains no vectors"
                )

            logger.info(
                f"Built FAISS index with "
                f"{index.ntotal} vectors"
            )

            os.makedirs(
                self.embedding_config.embedding_dir,
                exist_ok=True,
            )

            faiss.write_index(
                index,
                self.embedding_config.index_file_path,
            )

            logger.info(
                "FAISS index saved successfully"
            )

            metadata_file_path = save_json(
                {
                    "chunks": chunks
                },
                self.embedding_config.metadata_file_path,
            )

            logger.info(
                "Embedding metadata saved successfully"
            )

            index_file_path = (
                self.embedding_config.index_file_path
            )

            # Release index from Python memory once
            # the serialized file has been written.
            del index
            gc.collect()

            return (
                index_file_path,
                metadata_file_path,
            )

        except Exception as e:
            raise MyException(e, sys) from e

    def initiate_embedding_indexing(
        self,
    ) -> EmbeddingArtifact:
        """
        Execute the complete embedding indexing pipeline.
        """
        try:
            logger.info(
                "Starting embedding indexing pipeline"
            )

            chunks = self.load_text_chunks()

            (
                index_file_path,
                metadata_file_path,
            ) = self.build_and_save_index(
                chunks
            )

            # Release chunk metadata from memory after
            # the metadata file has been persisted.
            del chunks
            gc.collect()

            logger.info(
                "Embedding indexing pipeline "
                "completed successfully"
            )

            return EmbeddingArtifact(
                index_file_path=index_file_path,
                metadata_file_path=metadata_file_path,
            )

        except Exception as e:
            raise MyException(e, sys) from e