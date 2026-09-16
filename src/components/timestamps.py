import json
import os
import sys

from src.exception import MyException
from src.logger import logger
from src.entity.config_entity import TimestampConfig
from src.entity.artifact_entity import (
    AudioTranscriptionArtifact,
    TimestampArtifact,
)


class TimestampGenerator:

    def __init__(
        self,
        audio_transcription_artifact: AudioTranscriptionArtifact,
        timestamp_config: TimestampConfig,
        llm,
    ):
        try:
            logger.info("Initializing TimestampGenerator")

            self.audio_transcription_artifact = audio_transcription_artifact
            self.timestamp_config = timestamp_config
            self.llm = llm

            logger.info("TimestampGenerator initialized successfully")

        except Exception as e:
            raise MyException(e, sys) from e

    def load_transcript(self):
        try:
            logger.info("Loading transcript")

            with open(
                self.audio_transcription_artifact.transcript_file_path,
                "r",
                encoding="utf-8",
            ) as file:
                transcript = json.load(file)

            logger.info("Transcript loaded successfully")
            return transcript

        except Exception as e:
            raise MyException(e, sys) from e

    def prepare_transcript(self, segments):
        try:
            logger.info("Preparing transcript for LLM")

            transcript = "\n".join(
                f"{segment['id']}|{segment['text']}" for segment in segments
            )

            logger.info("Transcript prepared successfully")
            return transcript

        except Exception as e:
            raise MyException(e, sys) from e

    def create_prompt(self, transcript):
        return f"""
Analyze the complete video transcript and identify meaningful semantic chapters.

First analyze the transcript as a whole, then identify major sections where
the main subject, concept, process, question, task, or learning objective changes.

Rules:
- Prefer fewer strong chapters over many small ones.
- Do not target a fixed chapter count or equal durations.
- Group definitions, explanations, examples, applications, comparisons,
  clarifications, pros/cons, and recaps that belong to the same concept.
- Combine closely related subtopics, even when moving from concepts to examples,
  applications, or project discussion.
- Do not split chapters for minor examples, explanations, or presentation structure.
- Do not use arbitrary time thresholds or context-chunk boundaries.
- Combine short closing remarks, career reflections, calls to action, and goodbyes
  with the preceding substantive section unless they introduce a substantial topic.
- Chapters must be chronological and non-overlapping.
- Use only segment IDs provided in the transcript.
- Never invent segment IDs.
- start_segment and end_segment must exactly match existing segment IDs.
- Topic names must be concise, specific, and descriptive.

Identify the semantic chapters and return them using the required structure.

Transcript:
{transcript}
"""

    def generate_timestamps(self, transcript):
        try:
            logger.info("Generating semantic timestamps using LLM")

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
                                    "topic": {
                                        "type": "string"
                                    },
                                    "start_segment": {
                                        "type": "integer"
                                    },
                                    "end_segment": {
                                        "type": "integer"
                                    },
                                },
                                "required": [
                                    "topic",
                                    "start_segment",
                                    "end_segment",
                                ],
                            },
                        }
                    },
                    "required": ["topics"],
                }
            )

            response = structured_llm.invoke(
                self.create_prompt(transcript)
            )

            topics = response["topics"]

            for i, topic in enumerate(topics, start=1):
                topic["topic_id"] = i

            logger.info("Semantic timestamps generated successfully")

            return topics

        except Exception as e:
            raise MyException(e, sys) from e

    def validate_topics(self, topics, segments):
        try:
            logger.info("Validating generated topics")

            valid_segment_ids = {segment["id"] for segment in segments}

            previous_end = -1

            for topic in topics:
                start_segment = topic["start_segment"]
                end_segment = topic["end_segment"]

                if start_segment not in valid_segment_ids:
                    raise ValueError(
                        f"Invalid start segment ID: {start_segment}"
                    )

                if end_segment not in valid_segment_ids:
                    raise ValueError(
                        f"Invalid end segment ID: {end_segment}"
                    )

                if start_segment > end_segment:
                    raise ValueError(
                        f"Invalid segment range: "
                        f"{start_segment}-{end_segment}"
                    )

                if start_segment <= previous_end:
                    raise ValueError(
                        "Overlapping or unordered topic ranges detected"
                    )

                previous_end = end_segment

            logger.info("Generated topics validated successfully")

        except Exception as e:
            raise MyException(e, sys) from e

    def convert_segments_to_timestamps(self, topics, segments):
        try:
            logger.info("Converting segment IDs to timestamps")

            segment_map = {
                segment["id"]: segment
                for segment in segments
            }

            timestamp_topics = []

            for topic in topics:
                start_segment = segment_map[
                    topic["start_segment"]
                ]

                end_segment = segment_map[
                    topic["end_segment"]
                ]

                timestamp_topics.append(
                    {
                        "topic_id": topic["topic_id"],
                        "topic": topic["topic"],
                        "start_time": self.format_timestamp(
                            start_segment["start"]
                        ),
                        "end_time": self.format_timestamp(
                            end_segment["end"]
                        ),
                    }
                )

            logger.info("Segment IDs converted to timestamps")

            return timestamp_topics

        except Exception as e:
            raise MyException(e, sys) from e

    def close_gaps(self, topics):
        try:
            for i in range(len(topics) - 1):
                topics[i]["end_time"] = topics[i + 1]["start_time"]

            return topics

        except Exception as e:
            raise MyException(e, sys) from e

    def format_timestamp(self, seconds):
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)

        return f"{minutes:02d}:{seconds:02d}"

    def save_timestamps(self, topics):
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

            with open(
                self.timestamp_config.timestamp_file_path,
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    output,
                    file,
                    indent=4,
                    ensure_ascii=False,
                )

            logger.info(
                f"Timestamp file saved at "
                f"{self.timestamp_config.timestamp_file_path}"
            )

        except Exception as e:
            raise MyException(e, sys) from e

    def initiate_timestamp_generation(self) -> TimestampArtifact:
        try:
            logger.info("Starting timestamp generation pipeline")

            transcript = self.load_transcript()

            segments = transcript["segments"]
            prepared_transcript = self.prepare_transcript(
                segments
            )

            topics = self.generate_timestamps(
                prepared_transcript
            )

            self.validate_topics(
                topics,
                segments,
            )

            timestamp_topics = self.convert_segments_to_timestamps(
                topics,
                segments,
            )

            timestamp_topics = self.close_gaps(
                timestamp_topics
            )

            self.save_timestamps(
                timestamp_topics
            )

            logger.info(
                "Timestamp generation pipeline completed successfully"
            )

            return TimestampArtifact(
                timestamp_file_path=self.timestamp_config.timestamp_file_path
            )

        except Exception as e:
            raise MyException(e, sys) from e