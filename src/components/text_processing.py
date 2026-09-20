import os
import sys

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.entity.config_entity import TextProcessingConfig
from src.entity.artifact_entity import (
    AudioTranscriptionArtifact,
    TextProcessingArtifact,
)
from src.exception import MyException
from src.logger import logger
from src.utils.main_utils import (
    load_json,
    save_json,
)


class TextProcessing:
    """Processes timestamped transcript and creates text chunks."""

    def __init__(
        self,
        audio_transcription_artifact: AudioTranscriptionArtifact,
        text_processing_config: TextProcessingConfig,
    ):
        """
        Initialize TextProcessing with the transcription artifact and config.

        Args:
            audio_transcription_artifact: Output of the transcription stage,
                pointing to the timestamped transcript JSON.
            text_processing_config: Configuration for chunk size, overlap,
                and the output directory for text chunks.
        """
        try:
            self.audio_transcription_artifact = audio_transcription_artifact
            self.text_processing_config = text_processing_config

        except Exception as e:
            raise MyException(e, sys) from e

    def load_transcript_data(self) -> dict:
        """
        Load and validate the timestamped transcript produced by transcription.

        Returns:
            The parsed transcript dict, guaranteed to contain a non-empty
            `segments` list.

        Raises:
            MyException: If the file is missing, empty, or malformed.
        """
        try:
            logger.info("Loading transcription data")

            transcript_file_path = (
                self.audio_transcription_artifact.transcript_file_path
            )

            transcript_data = load_json(transcript_file_path)

            if not transcript_data:
                raise ValueError("Transcription data is empty")

            if "segments" not in transcript_data:
                raise ValueError("Transcription data does not contain segments")

            if not transcript_data["segments"]:
                raise ValueError("Transcription segments are empty")

            logger.info("Transcription data loaded successfully")

            return transcript_data

        except Exception as e:
            raise MyException(e, sys) from e

    def create_text_chunks(self, segments: list) -> list:
        """
        Merge transcript segments into larger text chunks while preserving
        the start/end timestamps that bound each chunk.

        Uses a RecursiveCharacterTextSplitter to split accumulated text
        once it reaches the configured chunk size, carrying over any
        leftover text into the next chunk.

        Args:
            segments: List of transcript segment dicts (each with `start`,
                `end`, and `text`).

        Returns:
            A list of chunk dicts, each with `chunk_id`, `start_time`,
            `end_time`, `text`, `text_length`, and `word_count`.

        Raises:
            MyException: If no chunks are produced.
        """
        try:
            logger.info("Creating timestamp-preserved text chunks")

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.text_processing_config.chunk_size,
                chunk_overlap=self.text_processing_config.chunk_overlap,
                separators=[
                    "\n\n",
                    "\n",
                    ". ",
                    "! ",
                    "? ",
                    " ",
                    "",
                ],
            )

            chunks = []

            current_text = ""
            current_start_time = None
            current_end_time = None
            chunk_id = 1

            for segment in segments:
                segment_text = segment.get(
                    "text",
                    "",
                ).strip()

                if not segment_text:
                    continue

                segment_start = segment.get("start")
                segment_end = segment.get("end")

                if current_start_time is None:
                    current_start_time = segment_start

                current_end_time = segment_end

                if current_text:
                    current_text += " "

                current_text += segment_text

                if len(current_text) >= (self.text_processing_config.chunk_size):
                    split_chunks = text_splitter.split_text(current_text)

                    for split_chunk in split_chunks[:-1]:
                        chunks.append(
                            {
                                "chunk_id": chunk_id,
                                "start_time": current_start_time,
                                "end_time": current_end_time,
                                "text": split_chunk,
                                "text_length": len(split_chunk),
                                "word_count": len(split_chunk.split()),
                            }
                        )

                        chunk_id += 1

                    if split_chunks:
                        current_text = split_chunks[-1]

                    current_start_time = segment_start
                    current_end_time = segment_end

            if current_text.strip():
                final_text = current_text.strip()

                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "start_time": current_start_time,
                        "end_time": current_end_time,
                        "text": final_text,
                        "text_length": len(final_text),
                        "word_count": len(final_text.split()),
                    }
                )

            if not chunks:
                raise ValueError("No text chunks were created")

            logger.info(f"Created {len(chunks)} text chunks")

            return chunks

        except Exception as e:
            raise MyException(e, sys) from e

    def save_text_chunks(self, chunks: list) -> str:
        """
        Persist each text chunk to its own JSON file on disk.

        Args:
            chunks: List of chunk dicts produced by `create_text_chunks`.

        Returns:
            Path to the directory containing the saved chunk files.

        Raises:
            MyException: If saving any chunk fails.
        """
        try:
            logger.info("Saving text chunks")

            text_chunks_dir = self.text_processing_config.text_chunks_dir

            os.makedirs(
                text_chunks_dir,
                exist_ok=True,
            )

            for chunk in chunks:
                chunk_id = chunk["chunk_id"]

                chunk_file_path = os.path.join(
                    text_chunks_dir,
                    f"chunk_{chunk_id:03d}.json",
                )

                save_json(
                    chunk,
                    chunk_file_path,
                )

            logger.info("Text chunks saved successfully")

            return text_chunks_dir

        except Exception as e:
            raise MyException(e, sys) from e

    def initiate_text_processing(
        self,
    ) -> TextProcessingArtifact:
        """
        Execute the complete text processing stage: load the transcript,
        chunk it, and save the chunks to disk.

        Returns:
            A TextProcessingArtifact pointing to the directory of saved
            text chunk files.

        Raises:
            MyException: If any stage of processing fails.
        """
        try:
            logger.info("Starting text processing")

            transcript_data = self.load_transcript_data()

            segments = transcript_data["segments"]

            text_chunks = self.create_text_chunks(segments=segments)

            text_chunks_dir = self.save_text_chunks(chunks=text_chunks)

            text_processing_artifact = TextProcessingArtifact(
                text_chunks_dir=text_chunks_dir
            )

            logger.info("Text processing artifact created successfully")

            return text_processing_artifact

        except Exception as e:
            raise MyException(e, sys) from e
