import json
import os
import sys
import time
from src.entity.config_entity import TimestampConfig
from src.entity.artifact_entity import (
    AudioTranscriptionArtifact,
    TimestampArtifact,
)
from src.exception import MyException
from src.logger import logger


class TimestampGenerator:
    """Generates semantic topic timestamps from transcript using an LLM."""

    def __init__(
        self,
        audio_transcription_artifact: AudioTranscriptionArtifact,
        timestamp_config: TimestampConfig,
        llm,
    ):
        self.audio_transcription_artifact = audio_transcription_artifact
        self.timestamp_config = timestamp_config
        self.llm = llm

    def load_transcript(self) -> list:
        try:
            logger.info("Loading transcript")

            with open(
                self.audio_transcription_artifact.transcript_file_path,
                "r",
                encoding="utf-8",
            ) as file:
                transcript_data = json.load(file)

            segments = transcript_data.get("segments", [])

            if not segments:
                raise ValueError("Transcript contains no segments")

            logger.info(f"Loaded {len(segments)} transcript segments")

            return segments

        except Exception as e:
            raise MyException(e, sys) from e

    def prepare_transcript(self, segments: list) -> str:
        try:
            logger.info("Preparing transcript for LLM")

            transcript_lines = []

            for segment in segments:
                text = segment.get("text", "").strip()

                if not text:
                    continue

                start = float(segment.get("start", 0.0))
                end = float(segment.get("end", 0.0))

                transcript_lines.append(f"[{start:.2f} - {end:.2f}] {text}")

            if not transcript_lines:
                raise ValueError("No valid transcript segments found")

            transcript = "\n".join(transcript_lines)

            logger.info(f"Prepared transcript with {len(transcript_lines)} segments")

            return transcript

        except Exception as e:
            raise MyException(e, sys) from e

    def create_batches(self, segments: list) -> list:
        """Split segments into batches that fit the LLM's context budget."""
        try:
            logger.info("Splitting transcript into batches")

            max_chars = self.timestamp_config.max_chars_per_batch
            batches = []
            current_batch = []
            current_chars = 0

            for segment in segments:
                text = segment.get("text", "").strip()
                if not text:
                    continue

                segment_chars = len(text) + 20

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

            logger.info(f"Split transcript into {len(batches)} batch(es)")
            return batches

        except Exception as e:
            raise MyException(e, sys) from e

    def merge_batches(self, batch_topics: list) -> list:
        """Merge per-batch topic lists, stitching adjacent same-name topics
        that got split across a batch boundary."""
        try:
            logger.info("Merging topics from all batches")

            merged = []

            for batch in batch_topics:
                for topic in batch:
                    if (
                        merged
                        and topic["topic"].strip().lower()
                        == merged[-1]["topic"].strip().lower()
                    ):
                        merged[-1]["end_time"] = topic["end_time"]
                    else:
                        merged.append(topic)

            merged.sort(key=lambda x: x["start_time"])

            for index, topic in enumerate(merged, start=1):
                topic["topic_id"] = index

            logger.info(f"Merged into {len(merged)} total topics")
            return merged

        except Exception as e:
            raise MyException(e, sys) from e

    def create_prompt(self, transcript: str) -> str:
        return f"""
Analyze the following complete video transcript.

Identify the major semantic topics discussed in the video.

You MUST return a JSON object.

JSON format:

{{
  "topics": [
    {{
      "topic_id": 1,
      "topic": "Short topic name",
      "start_time": 0.0,
      "end_time": 10.0
    }}
  ]
}}

Rules:

- Read the entire transcript before deciding topic boundaries.
- Group consecutive segments that discuss the same subject.
- Create meaningful sections, not sentence-level topics.
- Do not split topics using fixed time or text length.
- Topics must be chronological.
- Cover the complete transcript.
- Do not overlap topics.
- Use timestamps ONLY from the transcript.
- start_time must exactly equal a segment start timestamp.
- end_time must exactly equal a segment end timestamp.
- Do not invent timestamps.
- Do not reproduce transcript text.
- Topic names must be short.
- Return ONLY valid JSON.
- Do not use Markdown.
- Do not include explanations.

Transcript:

{transcript}
"""

    def generate_timestamps(self, transcript: str) -> list:
        try:
            logger.info("Generating semantic timestamps using LLM")

            prompt = self.create_prompt(transcript)

            max_attempts = 3
            last_error = None

            for attempt in range(1, max_attempts + 1):
                try:
                    response = self.llm.invoke(prompt)
                    response_text = response.content.strip()

                    if not response_text:
                        raise ValueError("LLM returned an empty response")

                    response_data = json.loads(response_text)
                    timestamps = response_data.get("topics", [])

                    if not isinstance(timestamps, list) or not timestamps:
                        raise ValueError(
                            "LLM response does not contain a valid topics list"
                        )

                    logger.info(
                        f"Generated {len(timestamps)} topics (attempt {attempt})"
                    )
                    return timestamps

                except Exception as attempt_error:
                    last_error = attempt_error
                    logger.info(
                        f"generate_timestamps attempt {attempt}/{max_attempts} "
                        f"failed: {attempt_error}"
                    )
                    if attempt < max_attempts:
                        time.sleep(2 * attempt)

            raise last_error

        except Exception as e:
            raise MyException(e, sys) from e

    def validate_timestamps(
        self,
        segments: list,
        topics: list,
    ) -> list:
        try:
            logger.info("Validating generated timestamps")

            segment_starts = [
                round(float(segment.get("start", 0.0)), 2) for segment in segments
            ]

            segment_ends = [
                round(float(segment.get("end", 0.0)), 2) for segment in segments
            ]

            valid_starts = set(segment_starts)
            valid_ends = set(segment_ends)

            validated_topics = []

            for index, topic in enumerate(
                topics,
                start=1,
            ):
                if not isinstance(topic, dict):
                    raise ValueError(f"Topic {index} is not a valid object")

                if "topic" not in topic:
                    raise ValueError(f"Topic {index} is missing 'topic'")

                if "start_time" not in topic:
                    raise ValueError(f"Topic {index} is missing 'start_time'")

                if "end_time" not in topic:
                    raise ValueError(f"Topic {index} is missing 'end_time'")

                topic_name = str(topic["topic"]).strip()

                if not topic_name:
                    raise ValueError(f"Topic {index} has an empty topic name")

                start_time = round(
                    float(topic["start_time"]),
                    2,
                )

                end_time = round(
                    float(topic["end_time"]),
                    2,
                )

                if start_time not in valid_starts:
                    raise ValueError(
                        f"Invalid start_time for topic " f"{index}: {start_time}"
                    )

                if end_time not in valid_ends:
                    raise ValueError(
                        f"Invalid end_time for topic " f"{index}: {end_time}"
                    )

                if start_time >= end_time:
                    raise ValueError(
                        f"Invalid timestamp range for topic "
                        f"{index}: {start_time} - {end_time}"
                    )

                validated_topics.append(
                    {
                        "topic_id": index,
                        "topic": topic_name,
                        "start_time": start_time,
                        "end_time": end_time,
                    }
                )

            if not validated_topics:
                raise ValueError("No valid topics generated")

            validated_topics.sort(key=lambda x: x["start_time"])

            for index in range(
                1,
                len(validated_topics),
            ):
                previous_topic = validated_topics[index - 1]
                current_topic = validated_topics[index]

                if current_topic["start_time"] < previous_topic["end_time"]:
                    raise ValueError(
                        "Generated topics contain overlapping " "timestamp ranges"
                    )

            for index, topic in enumerate(
                validated_topics,
                start=1,
            ):
                topic["topic_id"] = index

            logger.info("Timestamp validation completed successfully")

            return validated_topics

        except Exception as e:
            raise MyException(e, sys) from e

    def save_timestamps(self, topics: list) -> str:
        try:
            logger.info("Saving timestamp data")

            os.makedirs(
                self.timestamp_config.timestamp_dir,
                exist_ok=True,
            )

            timestamp_data = {
                "total_topics": len(topics),
                "topics": topics,
            }

            with open(
                self.timestamp_config.timestamp_file_path,
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    timestamp_data,
                    file,
                    ensure_ascii=False,
                    indent=4,
                )

            logger.info("Timestamp data saved successfully")

            return self.timestamp_config.timestamp_file_path

        except Exception as e:
            raise MyException(e, sys) from e

    def get_topic_text(self, segments: list, start_time: float, end_time: float) -> str:
        """Reconstruct the transcript text spanning a topic's time range."""
        try:
            texts = [
                segment.get("text", "").strip()
                for segment in segments
                if segment.get("start", 0.0) >= start_time
                and segment.get("end", 0.0) <= end_time
            ]
            return " ".join(text for text in texts if text)

        except Exception as e:
            raise MyException(e, sys) from e

    def create_boundary_prompt(
        self, topic_a_name: str, text_a: str, topic_b_name: str, text_b: str
    ) -> str:
        return f"""
Two consecutive topic segments were extracted from a video transcript,
split at a processing boundary. Determine whether they are actually
ONE continuous topic that got incorrectly split, or two genuinely
DIFFERENT topics.

Topic A: "{topic_a_name}"
Text A: {text_a}

Topic B: "{topic_b_name}"
Text B: {text_b}

Return ONLY valid JSON, no markdown:
{{
  "same_topic": true or false,
  "merged_name": "short combined name if same_topic is true, else empty string"
}}
"""

    def reconcile_boundaries(self, topics: list, segments: list) -> list:
        """Use the LLM to merge topics that were split only because they
        landed on opposite sides of a batch boundary."""
        try:
            if len(topics) < 2:
                return topics

            logger.info("Reconciling topic boundaries across batches")

            reconciled = [topics[0]]

            for topic in topics[1:]:
                previous_topic = reconciled[-1]

                same_name = (
                    previous_topic["topic"].strip().lower()
                    == topic["topic"].strip().lower()
                )
                same_batch = previous_topic.get("_batch_index") == topic.get(
                    "_batch_index"
                )
                adjacent = abs(topic["start_time"] - previous_topic["end_time"]) < 1.0

                if same_name or same_batch or not adjacent:
                    reconciled.append(topic)
                    continue

                text_a = self.get_topic_text(
                    segments, previous_topic["start_time"], previous_topic["end_time"]
                )
                text_b = self.get_topic_text(
                    segments, topic["start_time"], topic["end_time"]
                )

                try:
                    prompt = self.create_boundary_prompt(
                        previous_topic["topic"], text_a, topic["topic"], text_b
                    )
                    response = self.llm.invoke(prompt)
                    response_data = json.loads(response.content.strip())

                    if response_data.get("same_topic"):
                        previous_topic["topic"] = (
                            response_data.get("merged_name") or previous_topic["topic"]
                        )
                        previous_topic["end_time"] = topic["end_time"]
                        continue

                except Exception as reconcile_error:
                    logger.info(
                        f"Boundary reconciliation failed, keeping topics "
                        f"separate: {reconcile_error}"
                    )

                reconciled.append(topic)

            for index, topic in enumerate(reconciled, start=1):
                topic["topic_id"] = index

            logger.info(f"Reconciled down to {len(reconciled)} topics")
            return reconciled

        except Exception as e:
            raise MyException(e, sys) from e

    def close_gaps(self, topics: list) -> list:
        """Eliminate small gaps between consecutive topics by extending
        each topic's end_time forward to the next topic's start_time."""
        try:
            if len(topics) < 2:
                return topics

            logger.info("Closing gaps between consecutive topics")

            for index in range(len(topics) - 1):
                topics[index]["end_time"] = topics[index + 1]["start_time"]

            logger.info("Gaps closed")
            return topics

        except Exception as e:
            raise MyException(e, sys) from e

    def initiate_timestamp_generation(self) -> TimestampArtifact:
        try:
            logger.info("Starting timestamp generation")

            segments = self.load_transcript()
            batches = self.create_batches(segments)

            all_batch_topics = []

            for batch_index, batch_segments in enumerate(batches, start=1):
                logger.info(f"Processing batch {batch_index}/{len(batches)}")

                transcript = self.prepare_transcript(batch_segments)
                topics = self.generate_timestamps(transcript)
                validated_topics = self.validate_timestamps(batch_segments, topics)

                for topic in validated_topics:
                    topic["_batch_index"] = batch_index

                all_batch_topics.append(validated_topics)

            merged_topics = self.merge_batches(all_batch_topics)
            final_topics = self.reconcile_boundaries(merged_topics, segments)

            for topic in final_topics:
                topic.pop("_batch_index", None)

            final_topics = self.close_gaps(final_topics)

            for topic in final_topics:
                topic["start_time"] = int(round(topic["start_time"]))
                topic["end_time"] = int(round(topic["end_time"]))

            timestamp_file_path = self.save_timestamps(final_topics)

            artifact = TimestampArtifact(timestamp_file_path=timestamp_file_path)

            logger.info("Timestamp generation completed successfully")
            return artifact

        except Exception as e:
            raise MyException(e, sys) from e
