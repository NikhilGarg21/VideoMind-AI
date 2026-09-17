class Prompt:
    timestamp_prompt = """
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