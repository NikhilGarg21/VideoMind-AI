import os
import sys
import json
import time
import re
from src.exception import MyException
from src.logger import logger

from src.entity.config_entity import TimestampConfig
from src.entity.artifact_entity import (
    AudioTranscriptionArtifact,
    TimestampArtifact,
)

from src.prompts import Prompt
from src.utils.main_utils import (
    load_json,
    save_json,
    format_timestamp,
)


class TimestampGenerator:
    """Generates semantic topic timestamps from a transcript using an LLM."""

    def __init__(
        self,
        audio_transcription_artifact: AudioTranscriptionArtifact,
        timestamp_config: TimestampConfig,
        llm,
    ):
        """
        Initialize TimestampGenerator with the transcript artifact, config,
        and an LLM instance to use for topic segmentation.

        Args:
            audio_transcription_artifact: Output of the transcription stage,
                pointing to the timestamped transcript JSON.
            timestamp_config: Configuration for the output timestamp file
                path and directory.
            llm: A LangChain-compatible chat model supporting
                `with_structured_output`.
        """
        try:
            logger.info("Initializing TimestampGenerator")

            self.audio_transcription_artifact = audio_transcription_artifact
            self.timestamp_config = timestamp_config
            self.llm = llm

            logger.info("TimestampGenerator initialized successfully")

        except Exception as e:
            raise MyException(e, sys) from e

    def extract_topics_from_error(self, error) -> list | None:
        """
        Attempt to salvage a valid topics list from a failed tool-call
        error whose underlying model output was valid JSON but wasn't
        wrapped in a proper tool call (a known intermittent Groq
        behavior with structured output on longer prompts).

        Args:
            error: The exception raised by the LLM call.

        Returns:
            A parsed list of topic dicts if recoverable, otherwise None.
        """
        try:
            error_str = str(error)
            match = re.search(
                r"'failed_generation':\s*'(\[.*\])'", error_str, re.DOTALL
            )
            if not match:
                return None
            raw_json = match.group(1).encode().decode("unicode_escape")
            return json.loads(raw_json)
        except Exception:
            return None

    def load_transcript(self):
        """
        Load the timestamped transcript JSON from disk.

        Returns:
            The parsed transcript dict.

        Raises:
            MyException: If loading fails.
        """
        try:
            logger.info("Loading transcript")

            transcript = load_json(
                self.audio_transcription_artifact.transcript_file_path
            )

            logger.info("Transcript loaded successfully")

            return transcript

        except Exception as e:
            raise MyException(e, sys) from e

    def prepare_transcript(self, segments):
        """
        Format transcript segments into a compact `id|text` string suitable
        for inclusion in the LLM prompt.

        Args:
            segments: List of transcript segment dicts.

        Returns:
            A newline-separated string of `"{id}|{text}"` lines.

        Raises:
            MyException: If formatting fails.
        """
        try:
            logger.info("Preparing transcript for LLM")

            transcript = "\n".join(
                f"{segment['id']}|{segment['text']}" for segment in segments
            )

            logger.info("Transcript prepared successfully")

            return transcript

        except Exception as e:
            raise MyException(e, sys) from e

    def generate_timestamps(self, transcript):
        """
        Call the LLM with a structured-output schema to identify semantic
        topics and their bounding segment IDs within the transcript.

        Retries on transient tool-calling failures. If a failure includes
        a valid JSON payload that just wasn't wrapped in a proper tool
        call (a known intermittent Groq behavior), that payload is
        salvaged directly instead of retrying unnecessarily.

        Args:
            transcript: The formatted `id|text` transcript string.
            max_retries: Number of attempts before giving up.
            retry_delay: Seconds to wait between retries.

        Returns:
            A list of topic dicts, each with `topic`, `start_segment`,
            `end_segment`, and an assigned `topic_id`.

        Raises:
            MyException: If all retries are exhausted and no salvage succeeds.
        """
        try:
            logger.info("Generating semantic timestamps using LLM")
            max_retries = self.timestamp_config.max_retries
            retry_delay = self.timestamp_config.retry_delay
            structured_llm = self.llm.with_structured_output(
                {
                    "title": "timestamp_topics",
                    "description": "Semantic topics identified from a video transcript",
                    "type": "object",
                    "properties": {
                        "topics": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "topic": {"type": "string"},
                                    "start_segment": {"type": "integer"},
                                    "end_segment": {"type": "integer"},
                                },
                                "required": ["topic", "start_segment", "end_segment"],
                            },
                        }
                    },
                    "required": ["topics"],
                }
            )
            prompt = Prompt.timestamp_prompt.format(transcript=transcript)

            last_error = None

            for attempt in range(1, max_retries + 1):
                try:
                    response = structured_llm.invoke(prompt)
                    topics = response["topics"]
                    for i, topic in enumerate(topics, start=1):
                        topic["topic_id"] = i
                    logger.info("Semantic timestamps generated successfully")
                    return topics

                except Exception as e:
                    logger.warning(
                        f"LLM tool-call attempt {attempt}/{max_retries} failed: {e}"
                    )

                    salvaged = self.extract_topics_from_error(e)
                    if salvaged:
                        logger.warning(
                            "Recovered topics from failed tool call response"
                        )
                        for i, topic in enumerate(salvaged, start=1):
                            topic["topic_id"] = i
                        return salvaged

                    last_error = e
                    if attempt < max_retries:
                        time.sleep(retry_delay)

            raise last_error

        except Exception as e:
            raise MyException(e, sys) from e

    def validate_topics(self, topics, segments):
        """
        Validate that LLM-generated topics reference real, ordered,
        non-overlapping segment ranges.

        Args:
            topics: List of topic dicts from `generate_timestamps`.
            segments: The original transcript segments, used to check
                that referenced segment IDs actually exist.

        Raises:
            MyException: If any topic references an invalid segment ID,
                has a reversed range, or overlaps the previous topic.
        """
        try:
            logger.info("Validating generated topics")

            valid_segment_ids = {segment["id"] for segment in segments}

            previous_end = -1

            for topic in topics:
                start_segment = topic["start_segment"]
                end_segment = topic["end_segment"]

                if start_segment not in valid_segment_ids:
                    raise ValueError(f"Invalid start segment ID: {start_segment}")

                if end_segment not in valid_segment_ids:
                    raise ValueError(f"Invalid end segment ID: {end_segment}")

                if start_segment > end_segment:
                    raise ValueError(
                        f"Invalid segment range: " f"{start_segment}-{end_segment}"
                    )

                if start_segment <= previous_end:
                    raise ValueError("Overlapping or unordered topic ranges detected")

                previous_end = end_segment

            logger.info("Generated topics validated successfully")

        except Exception as e:
            raise MyException(e, sys) from e

    def convert_segments_to_timestamps(self, topics, segments):
        """
        Convert each topic's segment ID range into human-readable
        start/end timestamps.

        Args:
            topics: Validated list of topic dicts.
            segments: The original transcript segments, used to look up
                the actual `start`/`end` seconds for each segment ID.

        Returns:
            A list of topic dicts with `topic_id`, `topic`, `start_time`,
            and `end_time` (formatted as MM:SS or similar).

        Raises:
            MyException: If conversion fails.
        """
        try:
            logger.info("Converting segment IDs to timestamps")

            segment_map = {segment["id"]: segment for segment in segments}

            timestamp_topics = []

            for topic in topics:
                start_segment = segment_map[topic["start_segment"]]

                end_segment = segment_map[topic["end_segment"]]

                timestamp_topics.append(
                    {
                        "topic_id": topic["topic_id"],
                        "topic": topic["topic"],
                        "start_time": format_timestamp(start_segment["start"]),
                        "end_time": format_timestamp(end_segment["end"]),
                    }
                )

            logger.info("Segment IDs converted to timestamps")

            return timestamp_topics

        except Exception as e:
            raise MyException(e, sys) from e

    def _to_seconds(self, timestamp: str) -> float:
        """
        Convert a `"MM:SS"`-formatted timestamp string into total seconds.

        Args:
            timestamp: A timestamp string in `MM:SS` format.

        Returns:
            The equivalent number of seconds as a float.
        """
        minutes, seconds = timestamp.split(":")
        return int(minutes) * 60 + int(seconds)

    def close_gaps(self, topics, max_gap_seconds=2.0):
        """
        Close small timing gaps between consecutive topics so their
        boundaries line up, while leaving larger gaps untouched and
        logging them for manual review.

        Args:
            topics: List of topic dicts with `start_time`/`end_time`.
            max_gap_seconds: The largest gap (in seconds) that will be
                auto-closed. Gaps larger than this are left as-is and
                logged as a warning instead.

        Returns:
            The topics list, with small gaps closed in place.

        Raises:
            MyException: If gap calculation fails.
        """
        try:
            for i in range(len(topics) - 1):
                gap = self._to_seconds(topics[i + 1]["start_time"]) - self._to_seconds(
                    topics[i]["end_time"]
                )
                if 0 < gap <= max_gap_seconds:
                    topics[i]["end_time"] = topics[i + 1]["start_time"]
                elif gap > max_gap_seconds:
                    logger.warning(
                        f"Large gap ({gap:.1f}s) between topic {i + 1} "
                        f"and {i + 2} — not auto-closed"
                    )

            return topics

        except Exception as e:
            raise MyException(e, sys)

    def save_timestamps(self, topics):
        """
        Save the final list of topic timestamps to the configured output file.

        Args:
            topics: The finalized list of topic dicts.

        Raises:
            MyException: If saving fails.
        """
        try:
            logger.info("Saving timestamp artifact")

            os.makedirs(
                self.timestamp_config.timestamp_dir,
                exist_ok=True,
            )

            output = {
                "total_topics": len(topics),
                "topics": topics,
            }

            save_json(
                output,
                self.timestamp_config.timestamp_file_path,
            )

            logger.info(
                f"Timestamp file saved at "
                f"{self.timestamp_config.timestamp_file_path}"
            )

        except Exception as e:
            raise MyException(e, sys)

    def initiate_timestamp_generation(self) -> TimestampArtifact:
        """
        Execute the complete timestamp generation pipeline: load the
        transcript, generate topics via LLM, validate them, convert to
        timestamps, close small gaps, and save the result.

        Returns:
            A TimestampArtifact pointing to the saved timestamp JSON file.

        Raises:
            MyException: If any stage of the pipeline fails.
        """
        try:
            logger.info("Starting timestamp generation pipeline")

            transcript = self.load_transcript()

            segments = transcript["segments"]

            prepared_transcript = self.prepare_transcript(segments)

            topics = self.generate_timestamps(prepared_transcript)

            self.validate_topics(
                topics,
                segments,
            )

            timestamp_topics = self.convert_segments_to_timestamps(
                topics,
                segments,
            )

            timestamp_topics = self.close_gaps(timestamp_topics)

            self.save_timestamps(timestamp_topics)

            logger.info("Timestamp generation pipeline completed successfully")

            return TimestampArtifact(
                timestamp_file_path=self.timestamp_config.timestamp_file_path
            )

        except Exception as e:
            raise MyException(e, sys) from e
