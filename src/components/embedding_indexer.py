import gc
import json
import os
import sys

import faiss
import numpy as np

from src.entity.artifact_entity import (
    EmbeddingArtifact,
    TextProcessingArtifact,
)
from src.entity.config_entity import EmbeddingConfig
from src.exception import MyException
from src.logger import logger
from src.utils.hf_embeddings import embed_texts


class EmbeddingIndexer:
    """
    Embeds text chunks in batches and builds a FAISS index
    for semantic retrieval.

    Memory optimizations:
    - Text chunks are loaded batch-by-batch.
    - All text chunks are NOT kept in RAM.
    - Embedding arrays are released after every batch.
    - Metadata is written incrementally to disk.
    - FAISS index is released after serialization.
    """

    BATCH_SIZE = 16

    def __init__(
        self,
        text_processing_artifact: TextProcessingArtifact,
        embedding_config: EmbeddingConfig,
    ):
        try:
            self.text_processing_artifact = text_processing_artifact

            self.embedding_config = embedding_config

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

    # ------------------------------------------------------------------
    # Chunk files
    # ------------------------------------------------------------------

    def get_chunk_files(self) -> list[str]:
        """
        Return sorted text chunk JSON files.

        Only filenames are kept in memory here, not
        the actual chunk contents.
        """
        try:
            logger.info("Finding text chunk files")

            text_chunks_dir = self.text_processing_artifact.text_chunks_dir

            if not os.path.exists(text_chunks_dir):
                raise FileNotFoundError(
                    f"Text chunks directory not found: " f"{text_chunks_dir}"
                )

            chunk_files = sorted(
                file_name
                for file_name in os.listdir(text_chunks_dir)
                if file_name.endswith(".json")
            )

            if not chunk_files:
                raise ValueError("No text chunks found")

            logger.info(f"Found {len(chunk_files)} " "text chunk files")

            return [
                os.path.join(
                    text_chunks_dir,
                    file_name,
                )
                for file_name in chunk_files
            ]

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

    # ------------------------------------------------------------------
    # Load batch
    # ------------------------------------------------------------------

    def load_chunk_batch(
        self,
        chunk_files: list[str],
    ) -> list[dict]:
        """
        Load only one batch of text chunks into memory.
        """
        try:
            chunks = []

            for file_path in chunk_files:

                with open(
                    file_path,
                    "r",
                    encoding="utf-8",
                ) as file:

                    chunks.append(json.load(file))

            return chunks

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

    # ------------------------------------------------------------------
    # Build FAISS + metadata
    # ------------------------------------------------------------------

    def build_and_save_index(
        self,
        chunk_files: list[str],
    ) -> tuple[str, str]:
        """
        Build FAISS incrementally while writing metadata
        incrementally.

        Returns:
            Tuple of index file path and metadata file path.
        """
        try:
            logger.info(
                f"Using embedding model: " f"{self.embedding_config.model_name}"
            )

            total_chunks = len(chunk_files)

            if total_chunks == 0:
                raise ValueError("No chunks available for embedding")

            os.makedirs(
                self.embedding_config.embedding_dir,
                exist_ok=True,
            )

            index = None
            metadata_file = None

            index_file_path = self.embedding_config.index_file_path

            metadata_file_path = self.embedding_config.metadata_file_path

            temp_metadata_path = metadata_file_path + ".tmp"

            batch_number = 0
            metadata_first = True

            try:
                # ----------------------------------------------------------
                # Start metadata JSON
                # ----------------------------------------------------------

                metadata_file = open(
                    temp_metadata_path,
                    "w",
                    encoding="utf-8",
                )

                metadata_file.write('{"chunks":[')

                # ----------------------------------------------------------
                # Process batches
                # ----------------------------------------------------------

                for start in range(
                    0,
                    total_chunks,
                    self.BATCH_SIZE,
                ):
                    end = min(
                        start + self.BATCH_SIZE,
                        total_chunks,
                    )

                    batch_number += 1

                    batch_files = chunk_files[start:end]

                    batch_chunks = self.load_chunk_batch(batch_files)

                    texts = [chunk["text"] for chunk in batch_chunks]

                    logger.info(
                        f"Embedding chunks "
                        f"{start + 1}-{end}/"
                        f"{total_chunks} "
                        f"(batch {batch_number})"
                    )

                    # ------------------------------------------------------
                    # HF embedding
                    # ------------------------------------------------------

                    embeddings = np.asarray(
                        embed_texts(
                            texts,
                            self.embedding_config.model_name,
                        ),
                        dtype="float32",
                    )

                    # ------------------------------------------------------
                    # Validate embeddings
                    # ------------------------------------------------------

                    if embeddings.ndim != 2:
                        raise ValueError("Embedding output must " "be a 2D array")

                    if embeddings.shape[0] != len(texts):
                        raise ValueError(
                            "Number of embeddings does "
                            "not match number of input texts"
                        )

                    if embeddings.shape[1] <= 0:
                        raise ValueError(
                            "Embedding dimension must " "be greater than zero"
                        )

                    # ------------------------------------------------------
                    # Create FAISS index once
                    # ------------------------------------------------------

                    if index is None:

                        embedding_dimension = embeddings.shape[1]

                        index = faiss.IndexFlatL2(embedding_dimension)

                        logger.info(
                            f"Created FAISS IndexFlatL2 "
                            f"with dimension "
                            f"{embedding_dimension}"
                        )

                    elif embeddings.shape[1] != index.d:

                        raise ValueError(
                            "Embedding dimension changed " "between batches"
                        )

                    # ------------------------------------------------------
                    # Add vectors
                    # ------------------------------------------------------

                    index.add(embeddings)

                    logger.info(
                        f"Added batch to FAISS index. "
                        f"Current vectors: "
                        f"{index.ntotal}"
                    )

                    # ------------------------------------------------------
                    # Write metadata immediately
                    # ------------------------------------------------------

                    for chunk in batch_chunks:

                        if not metadata_first:
                            metadata_file.write(",")

                        json.dump(
                            chunk,
                            metadata_file,
                            ensure_ascii=False,
                        )

                        metadata_first = False

                    metadata_file.flush()

                    # ------------------------------------------------------
                    # Release batch memory
                    # ------------------------------------------------------

                    del embeddings
                    del texts
                    del batch_chunks
                    del batch_files

                    gc.collect()

                # ----------------------------------------------------------
                # Validate index
                # ----------------------------------------------------------

                if index is None or index.ntotal == 0:
                    raise ValueError("FAISS index contains " "no vectors")

                logger.info(f"Built FAISS index with " f"{index.ntotal} vectors")

                # ----------------------------------------------------------
                # Finish metadata JSON
                # ----------------------------------------------------------

                metadata_file.write("]}")

                metadata_file.close()
                metadata_file = None

                # Atomic metadata replacement.
                os.replace(
                    temp_metadata_path,
                    metadata_file_path,
                )

                logger.info("Embedding metadata saved successfully")

                # ----------------------------------------------------------
                # Save FAISS
                # ----------------------------------------------------------

                faiss.write_index(
                    index,
                    index_file_path,
                )

                logger.info("FAISS index saved successfully")

                return (
                    index_file_path,
                    metadata_file_path,
                )

            finally:

                if metadata_file is not None:

                    try:
                        metadata_file.close()
                    except Exception:
                        pass

                # Remove incomplete metadata file
                # if something failed.
                if os.path.exists(temp_metadata_path):

                    try:
                        os.remove(temp_metadata_path)
                    except Exception:
                        pass

                if index is not None:

                    del index

                gc.collect()

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def initiate_embedding_indexing(
        self,
    ) -> EmbeddingArtifact:
        """
        Execute the complete embedding indexing pipeline.
        """
        try:
            logger.info("Starting embedding indexing pipeline")

            chunk_files = self.get_chunk_files()

            (
                index_file_path,
                metadata_file_path,
            ) = self.build_and_save_index(chunk_files)

            # Only filenames were kept in memory,
            # but release the list explicitly.
            del chunk_files

            gc.collect()

            logger.info("Embedding indexing pipeline " "completed successfully")

            return EmbeddingArtifact(
                index_file_path=(index_file_path),
                metadata_file_path=(metadata_file_path),
            )

        except Exception as e:
            raise MyException(
                e,
                sys,
            ) from e
