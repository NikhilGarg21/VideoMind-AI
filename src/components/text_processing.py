import os
import sys
import json

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.entity.config_entity import TextProcessingConfig
from src.entity.artifact_entity import (
    AudioTranscriptionArtifact,
    TextProcessingArtifact,
)
from src.exception import MyException
from src.logger import logger


class TextProcessing:
    """Processes timestamped transcript and creates text chunks."""

    def __init__(
        self,
        audio_transcription_artifact: AudioTranscriptionArtifact,
        text_processing_config: TextProcessingConfig,
    ):
        self.audio_transcription_artifact = audio_transcription_artifact

        self.text_processing_config = text_processing_config

    def load_transcript_data(self) -> dict:
        """Load timestamped transcription data."""

        try:
            logger.info("Loading transcription data")

            transcript_file_path = (
                self.audio_transcription_artifact.transcript_file_path
            )

            with open(
                transcript_file_path,
                "r",
                encoding="utf-8",
            ) as file:

                transcript_data = json.load(file)

            if not transcript_data:
                raise ValueError("Transcription data is empty")

            if "segments" not in transcript_data:
                raise ValueError("Transcription data does not contain segments")

            if not transcript_data["segments"]:
                raise ValueError("Transcription segments are empty")

            logger.info("Transcription data loaded successfully")

            return transcript_data

        except Exception as e:
            raise MyException(e, sys)

    def create_text_chunks(
        self,
        segments: list,
    ) -> list:
        """
        Create text chunks while preserving timestamps.

        Each chunk contains text along with the
        start and end timestamps.
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

                segment_text = segment.get("text", "").strip()

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

                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "start_time": current_start_time,
                        "end_time": current_end_time,
                        "text": current_text.strip(),
                        "text_length": len(current_text.strip()),
                        "word_count": len(current_text.split()),
                    }
                )

            if not chunks:
                raise ValueError("No text chunks were created")

            logger.info(f"Created {len(chunks)} text chunks")

            return chunks

        except Exception as e:
            raise MyException(e, sys)

    def save_text_chunks(
        self,
        chunks: list,
    ) -> str:
        """Save timestamped text chunks."""

        try:
            logger.info("Saving text chunks")

            os.makedirs(
                self.text_processing_config.text_chunks_dir,
                exist_ok=True,
            )

            for chunk in chunks:

                chunk_id = chunk["chunk_id"]

                chunk_file_path = os.path.join(
                    self.text_processing_config.text_chunks_dir,
                    f"chunk_{chunk_id:03d}.json",
                )

                with open(
                    chunk_file_path,
                    "w",
                    encoding="utf-8",
                ) as file:

                    json.dump(
                        chunk,
                        file,
                        ensure_ascii=False,
                        indent=4,
                    )

            logger.info("Text chunks saved successfully")

            return self.text_processing_config.text_chunks_dir

        except Exception as e:
            raise MyException(e, sys)

    def initiate_text_processing(
        self,
    ) -> TextProcessingArtifact:
        """Execute complete text processing."""

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
            raise MyException(e, sys)
