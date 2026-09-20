import json
import sys
import time

from src.entity.artifact_entity import (
    AudioTranscriptionArtifact,
    SummaryArtifact,
)
from src.entity.config_entity import SummaryConfig
from src.exception import MyException
from src.logger import logger
from src.prompts import Prompt
from src.utils.main_utils import save_json


class SummaryGenerator:
    """
    Generates a structured TL;DR + key points summary from a transcript,
    using map-reduce over batches to stay within LLM context limits.
    """

    def __init__(
        self,
        audio_transcription_artifact: AudioTranscriptionArtifact,
        summary_config: SummaryConfig,
        llm,
    ):
        """
        Initialize SummaryGenerator with the transcript artifact, config,
        and an LLM instance to use for summarization.

        Args:
            audio_transcription_artifact: Output of the transcription stage,
                pointing to the timestamped transcript JSON.
            summary_config: Configuration for batch sizing, retry behavior,
                and the output summary file path.
            llm: A LangChain-compatible chat model exposing `.invoke()`
                and returning a response with a `.content` string.
        """
        try:
            logger.info("Initializing SummaryGenerator")

            self.audio_transcription_artifact = audio_transcription_artifact

            self.summary_config = summary_config
            self.llm = llm

            logger.info("SummaryGenerator initialized successfully")

        except Exception as e:
            raise MyException(e, sys) from e

    def load_transcript(self) -> list:
        """
        Load the timestamped transcript JSON and return its segments.

        Returns:
            A list of transcript segment dicts.

        Raises:
            MyException: If the file can't be read or contains no segments.
        """
        try:
            logger.info("Loading transcript for summary")

            with open(
                self.audio_transcription_artifact.transcript_file_path,
                "r",
                encoding="utf-8",
            ) as file:
                transcript_data = json.load(file)

            segments = transcript_data.get(
                "segments",
                [],
            )

            if not segments:
                raise ValueError("Transcript contains no segments")

            logger.info(f"Loaded {len(segments)} transcript segments")

            return segments

        except Exception as e:
            raise MyException(e, sys) from e

    def create_batches(
        self,
        segments: list,
    ) -> list:
        """
        Group transcript segments into text batches, each capped at the
        configured character limit.

        Args:
            segments: List of transcript segment dicts.

        Returns:
            A list of batches, where each batch is a list of segment dicts.

        Raises:
            MyException: If no batches could be created.
        """
        try:
            logger.info("Splitting transcript into batches for summarization")

            max_chars = self.summary_config.max_chars_per_batch

            batches = []
            current_batch = []
            current_chars = 0

            for segment in segments:
                text = segment.get(
                    "text",
                    "",
                ).strip()

                if not text:
                    continue

                segment_chars = len(text) + 1

                if current_batch and current_chars + segment_chars > max_chars:
                    batches.append(current_batch)

                    current_batch = []
                    current_chars = 0

                current_batch.append(segment)

                current_chars += segment_chars

            if current_batch:
                batches.append(current_batch)

            if not batches:
                raise ValueError("No batches could be created from transcript")

            logger.info(f"Split transcript into " f"{len(batches)} batch(es)")

            return batches

        except Exception as e:
            raise MyException(e, sys) from e

    def prepare_batch_text(
        self,
        segments: list,
    ) -> str:
        """
        Join a batch's segment texts into a single space-separated string.
        """
        try:
            return " ".join(
                segment.get(
                    "text",
                    "",
                ).strip()
                for segment in segments
                if segment.get(
                    "text",
                    "",
                ).strip()
            )

        except Exception as e:
            raise MyException(e, sys) from e

    def _strip_markdown_fence(
        self,
        text: str,
    ) -> str:
        """
        Remove a wrapping ```json ... ``` or ``` ... ``` code fence
        from an LLM response.
        """
        stripped = text.strip()

        if stripped.startswith("```"):
            stripped = stripped.split(
                "\n",
                1,
            )[-1]

            if stripped.endswith("```"):
                stripped = stripped[: -len("```")]

        return stripped.strip()

    def invoke_llm_json(
        self,
        prompt: str,
    ) -> dict:
        """
        Shared retry-and-parse helper for both map and reduce LLM calls.
        """
        try:
            max_attempts = self.summary_config.max_retries

            retry_delay = self.summary_config.retry_delay

            last_error = None

            for attempt in range(
                1,
                max_attempts + 1,
            ):
                try:
                    response = self.llm.invoke(prompt)

                    response_text = self._strip_markdown_fence(response.content)

                    if not response_text:
                        raise ValueError("LLM returned an empty response")

                    return json.loads(response_text)

                except Exception as attempt_error:
                    last_error = attempt_error

                    logger.warning(
                        f"LLM call attempt "
                        f"{attempt}/{max_attempts} failed: "
                        f"{attempt_error}"
                    )

                    if attempt < max_attempts:
                        time.sleep(retry_delay * attempt)

            raise last_error

        except Exception as e:
            raise MyException(e, sys) from e

    def generate_partial_summary(
        self,
        transcript: str,
    ) -> str:
        """
        Generate a short summary for a single transcript batch.
        """
        try:
            logger.info("Generating partial summary for batch")

            prompt = Prompt.batch_summary_prompt.format(transcript=transcript)

            response_data = self.invoke_llm_json(prompt)

            partial_summary = response_data.get(
                "partial_summary",
                "",
            ).strip()

            if not partial_summary:
                raise ValueError("LLM returned an empty partial_summary")

            return partial_summary

        except Exception as e:
            raise MyException(e, sys) from e

    def generate_final_summary(
        self,
        partial_summaries: list,
    ) -> dict:
        """
        Combine all partial summaries into a single final summary.
        """
        try:
            logger.info("Generating final combined summary")

            numbered = "\n".join(
                f"{index}. {summary}"
                for index, summary in enumerate(
                    partial_summaries,
                    start=1,
                )
            )

            prompt = Prompt.final_summary_prompt.format(numbered=numbered)

            response_data = self.invoke_llm_json(prompt)

            tldr = response_data.get(
                "tldr",
                "",
            ).strip()

            key_points = response_data.get(
                "key_points",
                [],
            )

            if not tldr:
                raise ValueError("LLM returned an empty tldr")

            if not isinstance(key_points, list) or not key_points:
                raise ValueError("LLM returned an empty or " "invalid key_points list")

            cleaned_key_points = [
                str(point).strip() for point in key_points if str(point).strip()
            ]

            return {
                "tldr": tldr,
                "key_points": cleaned_key_points,
            }

        except Exception as e:
            raise MyException(e, sys) from e

    def initiate_summary_generation(
        self,
    ) -> SummaryArtifact:
        try:
            logger.info("Starting summary generation")

            segments = self.load_transcript()

            batches = self.create_batches(segments)

            partial_summaries = []

            for (
                batch_index,
                batch_segments,
            ) in enumerate(
                batches,
                start=1,
            ):
                logger.info(f"Summarizing batch " f"{batch_index}/{len(batches)}")

                batch_text = self.prepare_batch_text(batch_segments)

                partial_summary = self.generate_partial_summary(batch_text)

                partial_summaries.append(partial_summary)

            final_summary = self.generate_final_summary(partial_summaries)

            logger.info("Saving summary")

            summary_file_path = save_json(
                final_summary,
                self.summary_config.summary_file_path,
            )

            logger.info("Summary saved successfully")

            artifact = SummaryArtifact(summary_file_path=summary_file_path)

            logger.info("Summary generation completed successfully")

            return artifact

        except Exception as e:
            raise MyException(e, sys) from e
