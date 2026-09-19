# 🎥 VideoMind

> **Understand any video without watching it.**

VideoMind is an AI-powered video understanding and question-answering system that transforms long videos into searchable, grounded knowledge.

It can process a YouTube video or uploaded audio/video file, transcribe its content using Whisper, identify meaningful timestamps, generate summaries, create semantic embeddings, and answer questions using Retrieval-Augmented Generation (RAG).

---

## ✨ Features

- 🎬 **YouTube Video Support** — Analyze videos directly from a YouTube URL.
- 📁 **Video & Audio Upload** — Upload supported video/audio files for analysis.
- 🎙️ **Automatic Transcription** — Converts spoken content into text using OpenAI Whisper.
- ⏱️ **Timestamp Generation** — Preserves where important information appears in the video.
- 📝 **Grounded Summarization** — Generates summaries based on the processed video content.
- 🧩 **Text Chunking** — Splits transcripts into meaningful searchable chunks.
- 🔎 **Semantic Search** — Uses sentence embeddings to retrieve relevant video sections.
- ⚡ **FAISS Vector Search** — Provides fast similarity-based retrieval.
- 🤖 **RAG-based Q&A** — Answers questions using retrieved video context.
- 📍 **Source Timestamps** — Answers include timestamps pointing back to relevant parts of the video.
- 🌐 **FastAPI Backend** — REST API for video processing and question answering.
- 🎨 **Custom Web UI** — HTML, CSS and JavaScript frontend.
- 📊 **DVC Pipeline** — Data processing and embedding/indexing stages are versioned with DVC.
- 🔐 **Environment-based API Keys** — Secrets are loaded through environment variables.

---

## 🧠 How VideoMind Works

```text
                    ┌─────────────────────┐
                    │   YouTube URL /     │
                    │   Video / Audio     │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Audio Ingestion   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │      Whisper        │
                    │    Transcription    │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Text Processing   │
                    │   & Chunking        │
                    └──────────┬──────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
          ┌─────────────────┐   ┌─────────────────┐
          │    Timestamp    │   │    Summary      │
          │    Generation   │   │    Generation   │
          └─────────────────┘   └─────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ SentenceTransformer│
                    │     Embeddings      │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │       FAISS         │
                    │    Vector Index     │
                    └──────────┬──────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │         User Question          │
              └────────────────┬───────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Semantic Retrieval│
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │      Groq LLM       │
                    │    Answer Generation│
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Answer + Timestamps │
                    └─────────────────────┘
````

---

## 🏗️ Architecture

VideoMind is organized into separate components for ingestion, transcription, processing, retrieval, and question answering.

```text
VideoMind/
│
├── app.py
│
├── src/
│   ├── components/
│   │   ├── audio_ingestion.py
│   │   ├── audio_transcription.py
│   │   ├── text_processing.py
│   │   ├── timestamps.py
│   │   ├── summary.py
│   │   ├── embedding_indexer.py
│   │   └── qa_engine.py
│   │
│   ├── pipeline/
│   │   ├── video_pipeline.py
│   │   └── qa_pipeline.py
│   │
│   ├── llm/
│   │   └── llm_client.py
│   │
│   ├── entity/
│   │   ├── config_entity.py
│   │   └── artifact_entity.py
│   │
│   ├── utils/
│   │   └── ...
│   │
│   ├── exception.py
│   └── logger.py
│
├── artifact/
│   └── embedding/
│       ├── index.faiss
│       └── metadata.json
│
├── static/
│   ├── index.html
│   ├── style.css
│   └── script.js
│
├── scripts/
│   └── ...
│
├── dvc.yaml
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── ...
```

---

# 🔄 Processing Pipeline

## 1. Video / Audio Ingestion

VideoMind accepts:

* YouTube URLs
* Uploaded video files
* Uploaded audio files

For YouTube URLs, the application uses `yt-dlp` to retrieve the media required for processing.

---

## 2. Audio Transcription

The extracted audio is processed using **OpenAI Whisper**.

```text
Audio
  ↓
Whisper
  ↓
Transcript + segments
```

The transcription retains segment-level timing information, allowing VideoMind to connect answers back to the original video.

---

## 3. Text Processing

The transcript is cleaned and divided into manageable text chunks.

Each chunk contains information such as:

```text
{
    "text": "...",
    "start_time": "...",
    "end_time": "..."
}
```

This allows the retrieval system to return both relevant text and its location in the video.

---

## 4. Timestamp Generation

VideoMind preserves timestamps associated with transcript segments.

This allows answers to reference the relevant portion of the source video.

Example:

```text
Relevant source:
00:07:39 - 00:10:57
```

---

## 5. Summarization

The processed video content can be summarized using the configured LLM.

The summary is grounded in the processed video content rather than requiring the user to manually watch the entire video.

---

# 🔎 Embedding & Retrieval

VideoMind converts text chunks into vector embeddings using **Sentence Transformers**.

```text
Text chunks
     ↓
Sentence Transformer
     ↓
Embeddings
     ↓
FAISS Index
```

FAISS is used for efficient similarity search over the generated embeddings.

The resulting artifacts are stored as:

```text
artifact/
└── embedding/
    ├── index.faiss
    └── metadata.json
```

The metadata file preserves the relationship between retrieved vectors and their original video chunks/timestamps.

---

# 🤖 Question Answering

VideoMind uses a Retrieval-Augmented Generation architecture.

When a user asks:

```text
"What value is provided to students?"
```

the system performs:

```text
Question
   ↓
Question Embedding
   ↓
FAISS Similarity Search
   ↓
Relevant Video Chunks
   ↓
Context
   ↓
Groq LLM
   ↓
Answer
```

The response contains the generated answer along with relevant timestamps.

This keeps the answer grounded in the retrieved video content.

---

# 🧠 LLM

VideoMind uses **Groq** through LangChain's Groq integration.

The LLM client reads the API key from:

```text
GROQ_API_KEY
```

The key is never hardcoded into the application.

Example:

```python
api_key = os.getenv("GROQ_API_KEY")
```

---

# 🌐 Web Application

VideoMind provides a custom frontend built with:

* HTML
* CSS
* JavaScript

The interface allows users to:

1. Paste a YouTube URL
2. Validate the URL
3. Upload media files
4. Start video analysis
5. Monitor processing
6. Ask questions
7. View answers with timestamps

The backend is implemented using **FastAPI**.

---

# 🚀 API

The FastAPI application exposes endpoints for configuration, validation, video processing, job status, and question answering.

### Main endpoints

```text
GET /
```

Serves the VideoMind frontend.

```text
GET /api/config
```

Returns frontend/application configuration.

```text
POST /api/validate
```

Validates the provided video source.

```text
POST /api/jobs
```

Creates a video-processing job.

```text
GET /api/jobs/{job_id}
```

Returns the status of a processing job.

```text
POST /api/jobs/{job_id}/ask
```

Asks a question about the processed video.

```text
GET /media/{job_id}/{filename}
```

Provides access to generated media associated with a job.

Interactive API documentation is available through:

```text
/docs
```

---

# 🛠️ Tech Stack

| Category                       | Technology            |
| ------------------------------ | --------------------- |
| Language                       | Python                |
| Backend                        | FastAPI               |
| Frontend                       | HTML, CSS, JavaScript |
| Video Download                 | yt-dlp                |
| Speech-to-Text                 | OpenAI Whisper        |
| Embeddings                     | Sentence Transformers |
| Vector Database                | FAISS                 |
| LLM                            | Groq                  |
| LLM Framework                  | LangChain             |
| Experiment/Pipeline Versioning | DVC                   |
| API Server                     | Uvicorn               |
| Configuration                  | Environment Variables |
| Logging                        | Python Logging        |

---

# 📦 Installation

## 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd VideoMind
```

---

## 2. Create a virtual environment

### Windows

```bash
python -m venv venv
```

Activate it:

```bash
venv\Scripts\activate
```

---

## 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

# 🔐 Environment Variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key
```

Do **not** commit `.env` to GitHub.

Your `.gitignore` should contain:

```gitignore
.env
venv/
__pycache__/
```

For production deployment, configure `GROQ_API_KEY` through the hosting platform's environment/secrets settings.

---

# ▶️ Running Locally

Start the FastAPI application with:

```bash
uvicorn app:app --reload
```

The application will be available at:

```text
http://127.0.0.1:8000
```

Open:

```text
http://127.0.0.1:8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

---

# 🧪 Q&A Testing

After the embedding pipeline has generated the FAISS index and metadata, the Q&A pipeline can be initialized using the generated artifacts.

Example:

```python
from src.entity.artifact_entity import EmbeddingArtifact
from src.pipeline.qa_pipeline import QAPipeline

embedding_artifact = EmbeddingArtifact(
    index_file_path="artifact/embedding/index.faiss",
    metadata_file_path="artifact/embedding/metadata.json",
)

qa_pipeline = QAPipeline(embedding_artifact)

result = qa_pipeline.ask(
    "What is the main topic discussed in the video?"
)

print(result["answer"])
```

Retrieved sources can also be inspected:

```python
for source in result.get("sources", []):
    print(
        source["start_time"],
        "-",
        source["end_time"]
    )
```

---

# 📊 DVC Pipeline

VideoMind uses DVC to version and reproduce the data-processing pipeline.

The processing stages cover the workflow up to embedding/index generation.

```text
Audio Ingestion
       ↓
Audio Transcription
       ↓
Text Processing
       ↓
Timestamp Generation
       ↓
Summary Generation
       ↓
Embedding / FAISS Indexing
```

The interactive question-answering stage is intentionally kept outside the DVC pipeline because Q&A is an inference loop driven by user questions.

Run the pipeline with:

```bash
dvc repro
```

---

# 💾 Generated Artifacts

The embedding stage produces:

```text
artifact/
└── embedding/
    ├── index.faiss
    └── metadata.json
```

### `index.faiss`

Stores the vector index used for similarity search.

### `metadata.json`

Stores the processed chunks and their associated metadata, including timestamp information used to identify relevant sections of the video.

---

# 🧩 Project Components

## `AudioIngestion`

Handles the input media and prepares audio chunks for transcription.

## `AudioTranscription`

Uses Whisper to convert audio into timestamped text segments.

## `TextProcessing`

Cleans and structures the transcript into searchable chunks.

## `TimestampGenerator`

Maintains timestamp information associated with processed content.

## `SummaryGenerator`

Generates a grounded summary from the processed video content.

## `EmbeddingIndexer`

Creates sentence embeddings and builds the FAISS vector index.

## `QAEngine`

Retrieves relevant chunks and generates answers using the configured LLM.

## `VideoPipeline`

Coordinates the complete video-processing workflow.

## `QAPipeline`

Provides the interface for interactive question answering.

---

# 🔐 Security

API credentials should never be committed to the repository.

Use environment variables:

```env
GROQ_API_KEY=...
```

Never commit:

```text
.env
```

For deployment platforms, store secrets using their environment-variable/secret-management system.

---

# ⚡ Performance Considerations

Video processing is computationally heavier than normal API requests because it involves speech recognition and embedding generation.

The major resource-intensive components are:

* Whisper
* Sentence Transformers
* PyTorch-based dependencies
* Video/audio processing

For production deployment, these components may require more memory than a minimal web-service instance.

The application therefore separates the processing pipeline from the interactive Q&A workflow conceptually, while the Q&A stage can operate on already-generated FAISS artifacts.

---

# 🧪 Example Workflow

### Input

```text
YouTube URL
```

### Processing

```text
YouTube Video
      ↓
Audio Extraction
      ↓
Whisper Transcription
      ↓
Text Processing
      ↓
Timestamped Chunks
      ↓
Embeddings
      ↓
FAISS Index
```

### Question

```text
"What value is provided to students?"
```

### Output

```text
VideoMind retrieves the most relevant sections of the video
and generates an answer using the retrieved context.

Sources:
00:00 - 03:57
07:39 - 10:57
```

---

# 🎯 Why VideoMind?

Long-form videos often contain useful information buried across many minutes of content.

VideoMind turns that content into a searchable knowledge source so users can:

* Skip manually searching through long videos
* Ask questions in natural language
* Find relevant sections quickly
* Get answers grounded in the source content
* Jump directly to relevant timestamps

Instead of watching the entire video:

```text
Watch 60 minutes
       ↓
Find information manually
       ↓
Remember timestamp
```

VideoMind provides:

```text
Ask a question
       ↓
Retrieve relevant context
       ↓
Get an answer
       ↓
Get the timestamp
```

---

# 🔮 Future Improvements

* [ ] Persistent job storage
* [ ] Background task queue for long-running video processing
* [ ] Improved model/resource management
* [ ] Multiple video support
* [ ] Conversation history
* [ ] Streaming LLM responses
* [ ] More advanced transcript search
* [ ] Authentication and user accounts
* [ ] Cloud-based artifact storage
* [ ] Production deployment with dedicated processing workers
* [ ] GPU-based transcription for faster processing

---

