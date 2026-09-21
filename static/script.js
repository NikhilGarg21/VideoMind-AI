// ============================================================================
// VideoMind frontend — optimized vanilla JS.
// ============================================================================

const state = {
  jobId: null,
  sourceType: null, // "url" | "upload"
  selectedFile: null,
  validated: null, // result of /api/validate, or null
  pollTimer: null,
  lastStartedUrl: null,
  lastValidatedUrl: null, // Prevent duplicate validation requests
  stageDefs: [],
  ytPlayer: null,
  ytReady: false,
  mediaEl: null, // <video> element when playing an uploaded file
  results: null,
};

const el = {
  statusChip: document.getElementById("statusChip"),
  statusChipText: document.getElementById("statusChipText"),

  form: document.getElementById("inputForm"),
  urlInput: document.getElementById("urlInput"),
  checkBtn: document.getElementById("checkBtn"),
  dropzone: document.getElementById("dropzone"),
  dropzoneText: document.getElementById("dropzoneText"),
  fileInput: document.getElementById("fileInput"),
  previewCard: document.getElementById("previewCard"),
  previewThumb: document.getElementById("previewThumb"),
  previewTitle: document.getElementById("previewTitle"),
  previewMeta: document.getElementById("previewMeta"),
  analyzeBtn: document.getElementById("analyzeBtn"),
  formError: document.getElementById("formError"),

  signalChain: document.getElementById("signalChain"),
  chainTrack: document.getElementById("chainTrack"),
  chainSubtext: document.getElementById("chainSubtext"),

  resultsSection: document.getElementById("resultsSection"),
  videoEmbed: document.getElementById("videoEmbed"),
  resultTitle: document.getElementById("resultTitle"),
  resultChannel: document.getElementById("resultChannel"),

  tabs: document.getElementById("tabs"),
  tldrText: document.getElementById("tldrText"),
  keyPoints: document.getElementById("keyPoints"),
  chaptersList: document.getElementById("chaptersList"),
  transcriptList: document.getElementById("transcriptList"),
  transcriptSearch: document.getElementById("transcriptSearch"),

  chatLog: document.getElementById("chatLog"),
  chatEmpty: document.getElementById("chatEmpty"),
  chatForm: document.getElementById("chatForm"),
  chatInput: document.getElementById("chatInput"),
  chatSend: document.getElementById("chatSend"),

  errorBanner: document.getElementById("errorBanner"),
  errorBannerText: document.getElementById("errorBannerText"),
};

// ----------------------------------------------------------------------------
// Init
// ----------------------------------------------------------------------------

async function init() {
  buildWaveform();

  const config = await fetch("/api/config").then((r) => r.json());

  state.stageDefs = config.stages;

  buildChainModules();
  bindEvents();
}

function buildWaveform() {
  const svg = document.getElementById("waveformSvg");
  const bars = 28;
  let html = "";

  for (let i = 0; i < bars; i++) {
    const h = 30 + Math.random() * 130;
    const x = i * 14;
    const y = 110 - h / 2;
    const delay = (i * 0.08).toFixed(2);

    html += `<rect class="wf-bar" x="${x}" y="${y}" width="7" height="${h}" rx="3" style="animation-delay:${delay}s"></rect>`;
  }

  svg.innerHTML = html;
}

function buildChainModules() {
  el.chainTrack.innerHTML = state.stageDefs
    .map(
      (stage, i) => `
      <div class="chain-module" data-status="pending" data-key="${stage.key}">
        <div class="chain-module-head">
          <span class="chain-module-num">0${i + 1}</span>
          <span class="chain-status-icon" data-icon>○</span>
          <span class="chain-module-label">${stage.label}</span>
          <span class="chain-status-suffix" data-suffix hidden>(Processing…)</span>
        </div>
        <div class="chain-meter">
          <div class="chain-meter-fill"></div>
        </div>
        <div class="chain-module-desc">${stage.desc}</div>
      </div>
    `,
    )
    .join("");
}

// ----------------------------------------------------------------------------
// Events
// ----------------------------------------------------------------------------

function bindEvents() {
  el.checkBtn.addEventListener("click", handleCheck);

  el.urlInput.addEventListener("input", () => {
    if (
      state.lastValidatedUrl &&
      el.urlInput.value.trim() !== state.lastValidatedUrl
    ) {
      state.validated = null;
      state.lastValidatedUrl = null;
      el.previewCard.hidden = true;
    }

    if (state.sourceType !== "upload") {
      updateAnalyzeState();
    }
  });

  el.urlInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleCheck();
    }
  });

  el.dropzone.addEventListener("click", () => el.fileInput.click());

  el.dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      el.fileInput.click();
    }
  });

  el.fileInput.addEventListener("change", () => {
    if (el.fileInput.files[0]) {
      handleFileSelected(el.fileInput.files[0]);
    }
  });

  ["dragover", "dragenter"].forEach((evt) =>
    el.dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      el.dropzone.classList.add("dragover");
    }),
  );

  ["dragleave", "drop"].forEach((evt) =>
    el.dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      el.dropzone.classList.remove("dragover");
    }),
  );

  el.dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];

    if (file) {
      handleFileSelected(file);
    }
  });

  el.form.addEventListener("submit", (e) => {
    e.preventDefault();
    startJob();
  });

  el.tabs.addEventListener("click", (e) => {
    const btn = e.target.closest(".tab");

    if (btn) {
      switchTab(btn.dataset.tab);
    }
  });

  el.transcriptSearch.addEventListener("input", filterTranscript);

  el.chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendQuestion();
  });
}

// ----------------------------------------------------------------------------
// Memory Cleanup Helper
// ----------------------------------------------------------------------------

function clearPreviousResults() {
  if (state.ytPlayer && typeof state.ytPlayer.destroy === "function") {
    state.ytPlayer.destroy();
    state.ytPlayer = null;
  }

  if (state.mediaEl) {
    state.mediaEl.pause();
    state.mediaEl.removeAttribute("src");
    state.mediaEl.load();
    state.mediaEl = null;
  }

  el.videoEmbed.innerHTML = "";
  el.chaptersList.innerHTML = "";
  el.transcriptList.innerHTML = "";

  state.results = null;

  // Retain UI components hidden state until refreshed
  el.resultsSection.hidden = true;
}

// ----------------------------------------------------------------------------
// Validate (URL) / select (file)
// ----------------------------------------------------------------------------

async function handleCheck() {
  const url = el.urlInput.value.trim();

  if (!url) {
    return;
  }

  // Prevent hitting the backend again if URL hasn't changed & is already validated
  if (url === state.lastValidatedUrl && state.validated) {
    if (url !== state.lastStartedUrl) {
      startJob();
    }

    return;
  }

  clearError();

  state.sourceType = "url";
  state.selectedFile = null;

  el.fileInput.value = "";
  el.dropzoneText.textContent =
    "Drop a video or audio file, or click to browse";

  el.checkBtn.disabled = true;
  el.checkBtn.textContent = "Checking…";

  try {
    const res = await fetch("/api/validate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ url }),
    });

    const data = await res.json();

    if (!data.valid) {
      showFormError(data.error || "Couldn't read this link.");

      state.validated = null;
      state.lastValidatedUrl = null;

      el.previewCard.hidden = true;
    } else {
      state.validated = data;
      state.lastValidatedUrl = url;

      showPreview({
        title: data.title,
        meta: formatDuration(data.duration),
        thumb: data.thumbnail,
      });

      if (url !== state.lastStartedUrl) {
        startJob();
      }
    }
  } catch (err) {
    showFormError("Couldn't reach the server. Is it running?");
  } finally {
    el.checkBtn.disabled = false;
    el.checkBtn.textContent = "Check";
    updateAnalyzeState();
  }
}

function handleFileSelected(file) {
  clearError();
  clearPreviousResults();

  state.sourceType = "upload";
  state.selectedFile = file;
  state.validated = null;
  state.lastValidatedUrl = null;

  el.urlInput.value = "";
  el.dropzoneText.textContent = file.name;

  showPreview({
    title: file.name,
    meta: formatBytes(file.size),
    thumb: null,
  });

  updateAnalyzeState();
}

function showPreview({ title, meta, thumb }) {
  el.previewTitle.textContent = title || "Untitled";
  el.previewMeta.textContent = meta || "";

  if (thumb) {
    el.previewThumb.src = thumb;
    el.previewThumb.style.display = "block";

    el.previewThumb.onerror = () => {
      el.previewThumb.style.display = "none";
    };
  } else {
    el.previewThumb.style.display = "none";
  }

  el.previewCard.hidden = false;
}

function updateAnalyzeState() {
  const ready =
    (state.sourceType === "url" && state.validated) ||
    (state.sourceType === "upload" && state.selectedFile);

  el.analyzeBtn.disabled = !ready;
}

function setFormBusy(busy) {
  el.urlInput.disabled = busy;
  el.checkBtn.disabled = busy;
  el.fileInput.disabled = busy;
  el.dropzone.style.pointerEvents = busy ? "none" : "";
  el.dropzone.style.opacity = busy ? "0.5" : "";

  if (busy) {
    el.analyzeBtn.disabled = true;
  } else {
    el.analyzeBtn.textContent = "Analyze";
    updateAnalyzeState();
  }
}

function showFormError(msg) {
  el.formError.textContent = msg;
  el.formError.hidden = false;
}

function clearError() {
  el.formError.hidden = true;
}

// ----------------------------------------------------------------------------
// Start job
// ----------------------------------------------------------------------------

async function startJob() {
  el.errorBanner.hidden = true;
  el.analyzeBtn.disabled = true;
  el.analyzeBtn.textContent = "Starting…";

  const formData = new FormData();

  if (state.sourceType === "url") {
    formData.append("url", el.urlInput.value.trim());
  } else {
    formData.append("file", state.selectedFile);
  }

  try {
    const res = await fetch("/api/jobs", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json();

      if (res.status === 409) {
        throw new Error(
          "Still working on the last video — wait for it to finish first.",
        );
      }

      throw new Error(err.detail || "Couldn't start processing");
    }

    // Purge old DOM render elements on starting new job execution
    clearPreviousResults();

    const { job_id } = await res.json();

    state.jobId = job_id;

    if (state.sourceType === "url") {
      state.lastStartedUrl = el.urlInput.value.trim();
    }

    renderChain({
      stages: Object.fromEntries(
        state.stageDefs.map((s) => [s.key, "pending"]),
      ),
      current_stage: "ingestion",
      status: "running",
    });

    el.chatLog
      .querySelectorAll(".chat-bubble")
      .forEach((b) => b.remove());

    el.chatEmpty.hidden = false;

    el.signalChain.hidden = false;

    setStatusChip("processing", "Processing");
    setFormBusy(true);

    el.analyzeBtn.textContent = "Processing…";

    pollJob();
  } catch (err) {
    showFormError(err.message);
    el.analyzeBtn.disabled = false;
    el.analyzeBtn.textContent = "Analyze";
  }
}

function pollJob() {
  clearInterval(state.pollTimer);

  state.pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/jobs/${state.jobId}`);
      const job = await res.json();

      renderChain(job);

      if (job.status === "completed") {
        clearInterval(state.pollTimer);
        setStatusChip("completed", "Ready");
        setFormBusy(false);
        showResults(job);
      } else if (job.status === "failed") {
        clearInterval(state.pollTimer);
        setStatusChip("failed", "Failed");
        setFormBusy(false);
        showError(job.error || "Processing failed.");
      }
    } catch (err) {
      // transient network hiccup
    }
  }, 1100);
}

function renderChain(job) {
  state.stageDefs.forEach((stage) => {
    const moduleEl = el.chainTrack.querySelector(
      `[data-key="${stage.key}"]`,
    );

    const status = job.stages[stage.key] || "pending";

    moduleEl.dataset.status = status;

    const icon = moduleEl.querySelector("[data-icon]");
    const suffix = moduleEl.querySelector("[data-suffix]");

    icon.textContent =
      status === "done"
        ? "✓"
        : status === "running"
          ? "→"
          : status === "error"
            ? "✕"
            : "○";

    suffix.hidden = status !== "running";
  });

  const active = state.stageDefs.find(
    (s) => s.key === job.current_stage,
  );

  el.chainSubtext.textContent = active
    ? active.desc
    : job.status === "completed"
      ? "Every stage completed successfully."
      : "Six passes over the audio, each one built for a reason.";
}

function showError(message) {
  el.errorBannerText.textContent = message;
  el.errorBanner.hidden = false;
}

function setStatusChip(state_, text) {
  el.statusChip.dataset.state = state_;
  el.statusChipText.textContent = text;
}

// ----------------------------------------------------------------------------
// Results
// ----------------------------------------------------------------------------

function showResults(job) {
  state.results = job.results;
  el.resultsSection.hidden = false;

  const meta = job.results.metadata || {};

  el.resultTitle.textContent = meta.title || "Untitled";

  el.resultChannel.textContent = [meta.channel, formatDuration(meta.duration)]
    .filter(Boolean)
    .join(" · ");

  setupPlayer(job);
  renderOverview(job.results.summary);
  renderChapters(job.results.timestamps);
  renderTranscript(job.results.transcript);

  el.chatEmpty.hidden = false;
}

function setupPlayer(job) {
  if (job.video_id) {
    el.videoEmbed.innerHTML = `<div id="ytPlayer"></div>`;

    loadYouTubeAPI(() => {
      state.ytPlayer = new YT.Player("ytPlayer", {
        videoId: job.video_id,
        playerVars: {
          rel: 0,
        },
      });

      state.ytReady = true;
    });
  } else if (job.media_url) {
    if (job.is_video === false) {
      el.videoEmbed.innerHTML = `
        <div class="audio-only-player">
          <div class="audio-only-icon">♪</div>
          <audio id="localPlayer" src="${job.media_url}" controls></audio>
        </div>
      `;
    } else {
      el.videoEmbed.innerHTML = `
        <video id="localPlayer" src="${job.media_url}" controls></video>
      `;
    }

    state.mediaEl = document.getElementById("localPlayer");
  } else {
    el.videoEmbed.innerHTML = `
      <div
        style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-tertiary);font-size:13px;"
      >
        No preview available
      </div>
    `;
  }
}

function loadYouTubeAPI(callback) {
  if (window.YT && window.YT.Player) {
    return callback();
  }

  const tag = document.createElement("script");

  tag.src = "https://www.youtube.com/iframe_api";

  document.head.appendChild(tag);

  window.onYouTubeIframeAPIReady = callback;
}

function seekTo(timeLabel) {
  const seconds = parseTimecode(timeLabel);

  if (state.ytReady && state.ytPlayer) {
    state.ytPlayer.seekTo(seconds, true);
    state.ytPlayer.playVideo();
  } else if (state.mediaEl) {
    state.mediaEl.currentTime = seconds;
    state.mediaEl.play();
  }
}

function parseTimecode(label) {
  const parts = label.split(":").map(Number);

  return parts.length === 2
    ? parts[0] * 60 + parts[1]
    : parts[0] * 3600 + parts[1] * 60 + parts[2];
}

function renderOverview(summary) {
  el.tldrText.textContent = summary.tldr || "";

  el.keyPoints.innerHTML = (summary.key_points || [])
    .map((point) => `<li>${escapeHtml(point)}</li>`)
    .join("");
}

function renderChapters(topics) {
  if (!topics || topics.length === 0) {
    el.chaptersList.innerHTML = `
      <li class="chapters-empty">
        <div class="chapters-empty-icon">✦</div>
        <div class="chapters-empty-content">
          <div class="chapters-empty-title">Chapters unavailable</div>
          <div class="chapters-empty-text">
            We couldn't generate chapters for this video,
            but you can still use the transcript, summary, and Q&A.
          </div>
        </div>
      </li>
    `;

    return;
  }

  el.chaptersList.innerHTML = topics
    .map(
      (t) => `
      <li data-time="${t.start_time}">
        <span class="time-badge">${t.start_time}</span>
        <span class="chapter-topic">${escapeHtml(t.topic)}</span>
      </li>
    `,
    )
    .join("");

  el.chaptersList.querySelectorAll("li").forEach((li) => {
    li.addEventListener("click", () => seekTo(li.dataset.time));
  });
}

function renderTranscript(segments) {
  el.transcriptList.innerHTML = (segments || [])
    .map(
      (s) => `
      <li data-text="${escapeHtml(s.text).toLowerCase()}">
        <span
          class="time-badge"
          data-time="${s.start_time}"
          title="Jump to this moment"
        >
          ${s.start_time}
        </span>
        <span class="transcript-text">${escapeHtml(s.text)}</span>
      </li>
    `,
    )
    .join("");

  el.transcriptList
    .querySelectorAll(".time-badge")
    .forEach((badge) => {
      badge.addEventListener("click", (e) => {
        e.stopPropagation();
        seekTo(badge.dataset.time);
      });
    });
}

function filterTranscript() {
  const q = el.transcriptSearch.value.trim().toLowerCase();

  el.transcriptList.querySelectorAll("li").forEach((li) => {
    const matches = !q || li.dataset.text.includes(q);
    li.classList.toggle("hidden-match", !matches);
  });
}

// ----------------------------------------------------------------------------
// Tabs
// ----------------------------------------------------------------------------

function switchTab(name) {
  el.tabs
    .querySelectorAll(".tab")
    .forEach((t) =>
      t.classList.toggle("active", t.dataset.tab === name),
    );

  document
    .querySelectorAll(".tab-panel")
    .forEach((p) =>
      p.classList.toggle("active", p.id === `panel-${name}`),
    );
}

// ----------------------------------------------------------------------------
// Ask
// ----------------------------------------------------------------------------

async function sendQuestion() {
  const question = el.chatInput.value.trim();

  if (!question || !state.jobId) {
    return;
  }

  el.chatEmpty.hidden = true;

  appendBubble("user", question);

  el.chatInput.value = "";
  el.chatSend.disabled = true;

  const pending = appendBubble("assistant pending", "Thinking…");

  try {
    const res = await fetch(`/api/jobs/${state.jobId}/ask`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ question }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Couldn't get an answer.");
    }

    const data = await res.json();

    pending.classList.remove("pending");

    pending.innerHTML = `${escapeHtml(data.answer)}${renderSourceChips(data.sources)}`;

    bindSourceChips(pending);
  } catch (err) {
    pending.classList.remove("pending");
    pending.textContent = err.message;
  } finally {
    el.chatSend.disabled = false;
    el.chatLog.scrollTop = el.chatLog.scrollHeight;
  }
}

function appendBubble(className, text) {
  const div = document.createElement("div");

  div.className = `chat-bubble ${className}`;
  div.textContent = text;

  el.chatLog.appendChild(div);
  el.chatLog.scrollTop = el.chatLog.scrollHeight;

  return div;
}

function renderSourceChips(sources) {
  if (!sources || !sources.length) {
    return "";
  }

  const chips = sources
    .map(
      (s) =>
        `<span class="source-chip" data-time="${s.start_time}" title="Jump to this moment">${s.start_time}</span>`,
    )
    .join("");

  return `<div class="chat-sources">${chips}</div>`;
}

function bindSourceChips(container) {
  container.querySelectorAll(".source-chip").forEach((chip) => {
    chip.addEventListener("click", () => seekTo(chip.dataset.time));
  });
}

// ----------------------------------------------------------------------------
// Helpers
// ----------------------------------------------------------------------------

function formatDuration(seconds) {
  if (!seconds && seconds !== 0) {
    return "";
  }

  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);

  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatBytes(bytes) {
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(0)} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function escapeHtml(str) {
  const div = document.createElement("div");

  div.textContent = str ?? "";

  return div.innerHTML;
}

init();
