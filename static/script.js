const state = {
  jobId: null,
  pollTimer: null,
  startingJob: false,
  transcript: null,
};

const POLL_INTERVAL_MS = 1500;
const POLL_ERROR_RETRY_MS = 4000;


// ============================================================
// DOM HELPERS
// ============================================================

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  if (value === null || value === undefined) {
    return "";
  }

  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value);
}


// ============================================================
// STATUS
// ============================================================

function setStatus(message) {
  const status = $("status");

  if (status) {
    status.textContent = message;
  }
}


// ============================================================
// PROGRESS
// ============================================================

function updateProgress(progress) {
  const progressBar = $("progressBar");
  const progressText = $("progressText");

  const safeProgress = Math.max(
    0,
    Math.min(
      100,
      Number(progress) || 0
    )
  );

  if (progressBar) {
    progressBar.style.width = `${safeProgress}%`;
  }

  if (progressText) {
    progressText.textContent = `${safeProgress}%`;
  }
}


// ============================================================
// CHAIN RENDER
// ============================================================

function renderChain(job) {
  if (!job) {
    return;
  }

  const currentStage = job.current_stage || "";
  const status = job.status || "";

  updateProgress(
    job.progress || 0
  );

  const stageElement = $("currentStage");

  if (stageElement) {
    stageElement.textContent = currentStage || status;
  }

  const chainItems = document.querySelectorAll(
    "[data-stage]"
  );

  chainItems.forEach((item) => {
    const stage = item.dataset.stage;

    item.classList.remove(
      "active",
      "completed",
      "failed"
    );

    if (status === "failed") {
      if (stage === currentStage) {
        item.classList.add("failed");
      }
      return;
    }

    if (stage === currentStage) {
      item.classList.add("active");
      return;
    }

    const stageOrder = [
      "queued",
      "starting",
      "video_processing",
      "generating_results",
      "completed",
    ];

    const currentIndex = stageOrder.indexOf(currentStage);
    const itemIndex = stageOrder.indexOf(stage);

    if (
      currentIndex !== -1 &&
      itemIndex !== -1 &&
      itemIndex < currentIndex
    ) {
      item.classList.add("completed");
    }
  });
}


// ============================================================
// JOB MESSAGE
// ============================================================

function renderJobMessage(job) {
  if (!job) {
    return;
  }

  const statusText = $("jobStatus");

  if (!statusText) {
    return;
  }

  if (job.status === "queued") {
    statusText.textContent = "Job queued";
  } else if (job.status === "starting") {
    statusText.textContent = "Starting pipeline...";
  } else if (job.status === "processing") {
    statusText.textContent = "Processing video...";
  } else if (job.status === "completed") {
    statusText.textContent = "Processing completed";
  } else if (job.status === "failed") {
    statusText.textContent = "Processing failed";
  } else {
    statusText.textContent = job.status || "";
  }
}


// ============================================================
// SHOW RESULTS
// ============================================================

function showResults(job) {
  if (!job) {
    return;
  }

  const results = job.results || {};
  const summaryElement = $("summary");

  if (
    summaryElement &&
    results.summary !== null &&
    results.summary !== undefined
  ) {
    if (typeof results.summary === "string") {
      summaryElement.textContent = results.summary;
    } else {
      summaryElement.textContent = JSON.stringify(
        results.summary,
        null,
        2
      );
    }
  }

  renderTimestamps(results.timestamps);

  const resultsContainer = $("results");

  if (resultsContainer) {
    resultsContainer.classList.remove("hidden");
  }
}


// ============================================================
// TIMESTAMPS
// ============================================================

function renderTimestamps(timestamps) {
  const container = $("timestamps");

  if (!container) {
    return;
  }

  if (!timestamps) {
    container.innerHTML = "";
    return;
  }

  if (!Array.isArray(timestamps)) {
    container.textContent =
      typeof timestamps === "string"
        ? timestamps
        : JSON.stringify(
            timestamps,
            null,
            2
          );
    return;
  }

  container.innerHTML = timestamps
    .map((item) => {
      if (item === null || item === undefined) {
        return "";
      }

      if (typeof item === "string") {
        return `
          <div class="timestamp-item">
            ${escapeHtml(item)}
          </div>
        `;
      }

      const start = item.start ?? item.timestamp ?? "";
      const text = item.text ?? item.title ?? item.description ?? "";

      return `
        <div class="timestamp-item">
          <span class="timestamp-time">
            ${escapeHtml(start)}
          </span>
          <span class="timestamp-text">
            ${escapeHtml(text)}
          </span>
        </div>
      `;
    })
    .join("");
}


// ============================================================
// TRANSCRIPT
// ============================================================

async function fetchTranscript(jobId) {
  try {
    const response = await fetch(
      `/api/jobs/${encodeURIComponent(jobId)}/transcript`
    );

    if (!response.ok) {
      return null;
    }

    const transcript = await response.json();
    state.transcript = transcript;

    return transcript;
  } catch (error) {
    console.error("Transcript fetch failed:", error);
    return null;
  }
}


// ============================================================
// VIDEO
// ============================================================

function setupVideo(job) {
  if (!job) {
    return;
  }

  const video = $("videoPlayer");

  if (!video) {
    return;
  }

  if (job.media_url) {
    video.src = job.media_url;
    video.load();
  }
}


// ============================================================
// POLLING
// ============================================================

function stopPolling() {
  if (state.pollTimer) {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}


function schedulePoll(delay = POLL_INTERVAL_MS) {
  stopPolling();

  state.pollTimer = setTimeout(
    pollOnce,
    delay
  );
}


async function pollOnce() {
  if (!state.jobId) {
    return;
  }

  const currentJobId = state.jobId;

  try {
    const response = await fetch(
      `/api/jobs/${encodeURIComponent(currentJobId)}`
    );

    if (response.status === 404) {
      stopPolling();
      setStatus("Job no longer exists.");
      return;
    }

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const job = await response.json();

    // Ignore an old response if the
    // user already started a fresh job.
    if (currentJobId !== state.jobId) {
      return;
    }

    renderChain(job);
    renderJobMessage(job);
    setupVideo(job);

    if (job.status === "completed") {
      stopPolling();
      setStatus("Video processing completed.");

      await fetchTranscript(currentJobId);
      showResults(job);

      const askSection = $("askSection");

      if (askSection) {
        askSection.classList.remove("hidden");
      }

      return;
    }

    if (job.status === "failed") {
      stopPolling();
      setStatus(
        job.error || "Video processing failed."
      );
      return;
    }

    schedulePoll(POLL_INTERVAL_MS);

  } catch (error) {
    console.error("Polling error:", error);

    if (currentJobId !== state.jobId) {
      return;
    }

    schedulePoll(POLL_ERROR_RETRY_MS);
  }
}


function pollJob() {
  stopPolling();

  if (!state.jobId) {
    return;
  }

  pollOnce();
}


// ============================================================
// CREATE URL JOB
// ============================================================

async function submitUrl(url) {
  if (state.startingJob) {
    return;
  }

  const cleanUrl = String(url || "").trim();

  if (!cleanUrl) {
    setStatus("Please enter a URL.");
    return;
  }

  state.startingJob = true;

  try {
    setStatus("Validating new URL...");

    /*
     * IMPORTANT:
     * We DO NOT clear the old state here.
     *
     * Old video/result stays visible until
     * the backend successfully creates the
     * new job.
     */

    const response = await fetch("/api/jobs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        url: cleanUrl,
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(
        data.detail || "Could not create new job."
      );
    }

    /*
     * NEW JOB EXISTS NOW.
     *
     * Backend has already:
     * 1. created the new job
     * 2. switched ACTIVE_JOB_ID
     * 3. deleted old artifacts
     *
     * Now frontend switches to the new
     * job state.
     */

    state.jobId = data.job_id;
    state.transcript = null;

    updateProgress(0);
    setStatus("New job started...");

    renderChain(data);
    renderJobMessage(data);

    if (data.validation) {
      updateVideoMetadata(data.validation);
    }

    /*
     * Hide old result only AFTER new job
     * creation succeeded.
     */

    clearResultUI();

    /*
     * Start the actual pipeline.
     */

    await startJob(data.job_id);

  } catch (error) {
    console.error("Could not start new job:", error);

    /*
     * Old result/state remains intact
     * because we never cleared it before
     * successful job creation.
     */

    setStatus(
      error.message || "Could not start new job."
    );

  } finally {
    state.startingJob = false;
  }
}


// ============================================================
// START JOB PIPELINE
// ============================================================

async function startJob(jobId) {
  const response = await fetch(
    `/api/jobs/${encodeURIComponent(jobId)}/start`,
    {
      method: "POST",
    }
  );

  const data = await response.json();

  if (!response.ok) {
    throw new Error(
      data.detail || "Could not start pipeline."
    );
  }

  if (jobId !== state.jobId) {
    return;
  }

  renderChain(data);
  renderJobMessage(data);

  pollJob();
}


// ============================================================
// CLEAR RESULT UI
// ============================================================

function clearResultUI() {
  const results = $("results");

  if (results) {
    results.classList.add("hidden");
  }

  const askSection = $("askSection");

  if (askSection) {
    askSection.classList.add("hidden");
  }

  const summary = $("summary");

  if (summary) {
    summary.textContent = "";
  }

  const timestamps = $("timestamps");

  if (timestamps) {
    timestamps.innerHTML = "";
  }
}


// ============================================================
// VIDEO METADATA
// ============================================================

function updateVideoMetadata(validation) {
  if (!validation) {
    return;
  }

  const titleElement = $("videoTitle");

  if (titleElement && validation.title) {
    titleElement.textContent = validation.title;
  }

  const thumbnail = $("videoThumbnail");

  if (thumbnail && validation.thumbnail) {
    thumbnail.src = validation.thumbnail;
  }

  const duration = $("videoDuration");

  if (duration && validation.duration !== undefined) {
    duration.textContent = formatDuration(validation.duration);
  }
}


function formatDuration(seconds) {
  const value = Number(seconds);

  if (!Number.isFinite(value)) {
    return "";
  }

  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const secs = Math.floor(value % 60);

  if (hours > 0) {
    return [
      String(hours).padStart(2, "0"),
      String(minutes).padStart(2, "0"),
      String(secs).padStart(2, "0"),
    ].join(":");
  }

  return [
    String(minutes).padStart(2, "0"),
    String(secs).padStart(2, "0"),
  ].join(":");
}


// ============================================================
// ASK QUESTION
// ============================================================

async function askQuestion(question) {
  if (!state.jobId) {
    setStatus("No completed video available.");
    return;
  }

  const cleanQuestion = String(question || "").trim();

  if (!cleanQuestion) {
    return;
  }

  const answerElement = $("answer");

  if (answerElement) {
    answerElement.textContent = "Thinking...";
  }

  try {
    const response = await fetch(
      `/api/jobs/${encodeURIComponent(state.jobId)}/ask`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question: cleanQuestion,
        }),
      }
    );

    const data = await response.json();

    if (!response.ok) {
      throw new Error(
        data.detail || "Question answering failed."
      );
    }

    if (answerElement) {
      if (typeof data === "string") {
        answerElement.textContent = data;
      } else {
        const answer =
          data.answer ??
          data.response ??
          data.result ??
          data;

        answerElement.textContent =
          typeof answer === "string"
            ? answer
            : JSON.stringify(answer, null, 2);
      }
    }

  } catch (error) {
    console.error("Ask failed:", error);

    if (answerElement) {
      answerElement.textContent =
        error.message || "Question answering failed.";
    }
  }
}


// ============================================================
// URL FORM
// ============================================================

function setupUrlForm() {
  const form = $("urlForm");
  const input = $("urlInput");

  if (!form || !input) {
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitUrl(input.value);
  });
}


// ============================================================
// UPLOAD FORM
// ============================================================

function setupUploadForm() {
  const form = $("uploadForm");
  const fileInput = $("fileInput");

  if (!form || !fileInput) {
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (!fileInput.files || !fileInput.files.length) {
      setStatus("Please select a video file.");
      return;
    }

    if (state.startingJob) {
      return;
    }

    state.startingJob = true;

    try {
      setStatus("Uploading video...");

      const formData = new FormData();
      formData.append("file", fileInput.files[0]);

      const response = await fetch("/api/jobs/upload", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Upload failed."
        );
      }

      state.jobId = data.job_id;
      state.transcript = null;

      clearResultUI();
      updateProgress(0);

      renderChain(data);
      renderJobMessage(data);

      await startJob(data.job_id);

    } catch (error) {
      console.error("Upload failed:", error);

      setStatus(
        error.message || "Upload failed."
      );

    } finally {
      state.startingJob = false;
    }
  });
}


// ============================================================
// ASK FORM
// ============================================================

function setupAskForm() {
  const form = $("askForm");
  const input = $("questionInput");

  if (!form || !input) {
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await askQuestion(input.value);
  });
}


// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
  setupUrlForm();
  setupUploadForm();
  setupAskForm();

  setStatus("Ready.");
});