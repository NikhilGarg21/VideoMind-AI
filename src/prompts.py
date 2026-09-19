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

    batch_summary_prompt = """
Summarize the following portion of a video transcript in 4-6 sentences.
Capture all key ideas, claims, steps, and information covered — don't
over-compress; it's fine to be detailed here, since this will be combined
with other summaries later.

If this portion is primarily sponsor content, an affiliate promotion, or
a call to action (subscribe, follow, share, use this code) rather than the
video's core subject matter, summarize it briefly in one sentence instead
of in detail.

Preserve exact numbers, prices, dates, and figures mentioned — do not
round, estimate, or alter them.

Return ONLY valid JSON, no markdown:
{{
  "partial_summary": "..."
}}

Transcript portion:

{transcript}
"""

    final_summary_prompt = """
You are given partial summaries covering consecutive portions of a single
video's transcript, in chronological order. Combine them into one cohesive,
detailed summary of the entire video.

Return ONLY valid JSON, no markdown:
{{
  "tldr": "2-4 sentence overview of the entire video, covering its main
    topic, key offerings/claims, and overall purpose",
  "key_points": ["detailed key point", "detailed key point"]
}}

Rules:
- key_points should have between 8 and 14 items.
- Prioritize the video's core subject matter (the main topic, offer, process,
  or information being explained) over the creator's own channel promotion,
  sponsors, affiliate links, or calls to action (e.g. "subscribe", "follow
  me", "use my code", "share this video", "comment for a link"). Include at
  most 1-2 key points covering promotional content, combined into as few
  points as possible, and only if space allows after covering the core topic.
- Do not include asides about the presenter's own personal situation unless
  directly relevant to the video's main subject.
- Each key point should be 1-2 full sentences, specific enough to stand
  on its own without needing the video for context.
- Do not repeat the tldr inside key_points.
- Preserve numbers, prices, dates, and figures as stated in the source
  material. If a figure appears inconsistent with its context (e.g. a
  package price far lower than the value of the individual benefits it
  includes), you MUST flag it as a likely transcription error somewhere
  in the summary — do not state it as fact. Flag it exactly once, the
  first time it appears; every other mention should just omit the figure
  or refer to it generically (e.g. "the package") rather than repeating
  the questionable number unflagged.
- Order key_points chronologically, matching the order topics appear in
  the video.

Partial summaries:

{numbered}
"""

    qa_prompt = """
Answer using ONLY the transcript excerpts below.
If they don't contain enough information, say so instead of guessing.

Transcript:
{context}

Question:
{question}

Answer directly and use a format appropriate to the question.
For comparisons or multiple parts, use concise bullets.
Keep the answer clear and within 10 lines.
"""