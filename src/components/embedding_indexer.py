import os
import sys
import json
import faiss
from src.utils.hf_embeddings import embed_texts
import numpy as np
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

    def __init__(
        self,
        text_processing_artifact: TextProcessingArtifact,
        embedding_config: EmbeddingConfig,
    ):
        """
        Initialize EmbeddingIndexer with the text chunks artifact and config.

        Args:
            text_processing_artifact: Output of the text processing stage,
                pointing to the directory of saved text chunk JSON files.
            embedding_config: Configuration for the embedding model and
                output paths for the FAISS index and chunk metadata.
        """
        try:
            self.text_processing_artifact = text_processing_artifact
            self.embedding_config = embedding_config

        except Exception as e:
            raise MyException(e, sys) from e

    def load_text_chunks(self) -> list:
        """
        Load every saved text chunk JSON file from the text processing stage.

        Returns:
            A list of chunk dicts, each with `chunk_id`, `start_time`,
            `end_time`, and `text`.

        Raises:
            MyException: If the chunks directory is missing or empty.
        """
        try:
            logger.info("Loading text chunks for embedding")

            text_chunks_dir = self.text_processing_artifact.text_chunks_dir
            if not os.path.exists(text_chunks_dir):
                raise FileNotFoundError(
                    f"Text chunks directory not found: {text_chunks_dir}"
                )

            chunk_files = sorted(
                f for f in os.listdir(text_chunks_dir) if f.endswith(".json")
            )

            if not chunk_files:
                raise ValueError("No text chunks found")

            chunks = []
            for file_name in chunk_files:
                with open(
                    os.path.join(text_chunks_dir, file_name), "r", encoding="utf-8"
                ) as file:
                    chunks.append(json.load(file))

            logger.info(f"Loaded {len(chunks)} text chunks")
            return chunks

        except Exception as e:
            raise MyException(e, sys) from e

    def build_and_save_index(self, chunks: list) -> tuple:
        """
        Embed each chunk's text, build a FAISS index over the vectors, and
        persist both the index and chunk metadata to disk.

        Args:
            chunks: List of chunk dicts to embed.

        Returns:
            A tuple of (index_file_path, metadata_file_path).

        Raises:
            MyException: If embedding, indexing, or saving fails.
        """
        try:
            logger.info(f"Loading embedding model: {self.embedding_config.model_name}")
            logger.info("Embedding text chunks")
            texts = [chunk["text"] for chunk in chunks]
            embeddings = np.array(embed_texts(texts, self.embedding_config.model_name), dtype="float32")
            index = faiss.IndexFlatL2(embeddings.shape[1])
            index.add(embeddings)
            logger.info(f"Built FAISS index with {index.ntotal} vectors")

            os.makedirs(self.embedding_config.embedding_dir, exist_ok=True)
            faiss.write_index(index, self.embedding_config.index_file_path)

            metadata_file_path = save_json(
                {"chunks": chunks},
                self.embedding_config.metadata_file_path,
            )

            logger.info("FAISS index and metadata saved successfully")
            return self.embedding_config.index_file_path, metadata_file_path

        except Exception as e:
            raise MyException(e, sys) from e

    def initiate_embedding_indexing(self) -> EmbeddingArtifact:
        """
        Execute the complete embedding indexing pipeline: load chunks,
        embed them, build the FAISS index, and save it.

        Returns:
            An EmbeddingArtifact pointing to the saved index and metadata
            files.

        Raises:
            MyException: If any stage of indexing fails.
        """
        try:
            logger.info("Starting embedding indexing pipeline")

            chunks = self.load_text_chunks()
            index_file_path, metadata_file_path = self.build_and_save_index(chunks)

            logger.info("Embedding indexing pipeline completed successfully")

            return EmbeddingArtifact(
                index_file_path=index_file_path,
                metadata_file_path=metadata_file_path,
            )

        except Exception as e:
            raise MyException(e, sys) from e
    