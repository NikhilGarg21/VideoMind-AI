// ============================================================================
// VideoMind frontend — optimized vanilla JS.
// ============================================================================

const state = {
  jobId: null,
  sourceType: null, // "url" | "upload"
  selectedFile: null,
  validated: null,
  pollTimer: null,
  lastStartedUrl: null,
  lastValidatedUrl: null,
  stageDefs: [],
  ytPlayer: null,
  ytReady: false,
  mediaEl: null,
  results: null,
  processing: false,
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

async function init() {
  buildWaveform();

  const config = await fetch("/api/config").then((r) => r.json());

  state.stageDefs = config.stages;

  buildChainModules();
  bindEvents();
}

function buildWaveform() {
  const svg = document.getElementById("waveformSvg");
  if (!svg) return;
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

function bindEvents() {
  el.checkBtn.addEventListener("click", handleCheck);

  el.urlInput.addEventListener("input", () => {
    const url = el.urlInput.value.trim();

    if (state.sourceType === "upload" || url !== state.lastValidatedUrl) {
      clearPreviousResults();

      state.sourceType = "url";
      state.selectedFile = null;
      state.validated = null;
      state.lastValidatedUrl = null;

      el.fileInput.value = "";
      el.dropzoneText.textContent =
        "Drop a video or audio file, or click to browse";

      el.previewCard.hidden = true;
    }

    updateAnalyzeState();
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
      e.preventDefault();
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

function clearPreviousResults() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }

  if (state.ytPlayer && typeof state.ytPlayer.destroy === "function") {
    try {
      state.ytPlayer.destroy();
    } catch (e) {
      // Ignore cleanup errors.
    }

    state.ytPlayer = null;
  }

  state.ytReady = false;

  if (state.mediaEl) {
    try {
      state.mediaEl.pause();
      state.mediaEl.removeAttribute("src");
      state.mediaEl.load();
    } catch (e) {
      // Ignore cleanup errors.
    }

    state.mediaEl = null;
  }

  el.videoEmbed.classList.remove("audio-mode");
  el.videoEmbed.innerHTML = "";

  el.chaptersList.innerHTML = "";
  el.transcriptList.innerHTML = "";

  state.results = null;

  el.resultsSection.hidden = true;
}

async function handleCheck() {
  const url = el.urlInput.value.trim();

  if (!url) return;

  if (state.processing) {
    return;
  }

  clearPreviousResults();

  state.sourceType = "url";
  state.selectedFile = null;
  state.validated = null;

  el.fileInput.value = "";
  el.dropzoneText.textContent =
    "Drop a video or audio file, or click to browse";

  el.analyzeBtn.disabled = true;

  clearError();

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

    if (!state.processing) {
      updateAnalyzeState();
    }
  }
}

function handleFileSelected(file) {
  clearError();

  clearPreviousResults();

  state.sourceType = "upload";
  state.selectedFile = file;
  state.validated = null;
  state.lastValidatedUrl = null;
  state.lastStartedUrl = null;

  el.urlInput.value = "";

  el.fileInput.value = "";
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

async function startJob() {
  if (state.processing) {
    return;
  }

  state.processing = true;

  el.errorBanner.hidden = true;
  clearPreviousResults();
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

    el.chatLog.querySelectorAll(".chat-bubble").forEach((b) => b.remove());

    el.chatEmpty.hidden = false;
    el.signalChain.hidden = false;

    setStatusChip("processing", "Processing");
    setFormBusy(true);

    el.analyzeBtn.textContent = "Processing…";

    pollJob();
  } catch (err) {
    state.processing = false;
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
        state.processing = false;
        setStatusChip("completed", "Ready");
        setFormBusy(false);
        showResults(job);
      } else if (job.status === "failed") {
        clearInterval(state.pollTimer);
        state.processing = false;
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
    const moduleEl = el.chainTrack.querySelector(`[data-key="${stage.key}"]`);

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

  const active = state.stageDefs.find((s) => s.key === job.current_stage);

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

/* ==========================================================================
   Player Setup & Audio Controls Logic
   ========================================================================== */

function setupPlayer(job) {
  state.ytReady = false;
  state.mediaEl = null;

  el.videoEmbed.classList.remove("audio-mode");

  // 1. YouTube Video
  if (job.video_id) {
    el.videoEmbed.innerHTML = `<div id="ytPlayer"></div>`;

    loadYouTubeAPI(() => {
      state.ytPlayer = new YT.Player("ytPlayer", {
        videoId: job.video_id,
        playerVars: { rel: 0 },
      });
      state.ytReady = true;
    });
    return;
  }

  // 2. Local / Uploaded Media
  if (job.media_url) {
    const urlOrFilename = (
      job.media_url ||
      job.results?.metadata?.title ||
      ""
    ).toLowerCase();

    // Check file extension for audio formats
    const isAudio =
      /\.(mp3|wav|m4a|aac|ogg|flac|wma|opus)($|\?)/i.test(urlOrFilename) ||
      (state.selectedFile && state.selectedFile.type.startsWith("audio/"));

    if (isAudio) {
      el.videoEmbed.classList.add("audio-mode");

      const title =
        job.results?.metadata?.title ||
        state.selectedFile?.name ||
        "Audio Track";

      el.videoEmbed.innerHTML = `
        <div class="audio-only-player">
          <audio id="localPlayer" src="${job.media_url}" preload="metadata"></audio>
          
          <button type="button" class="audio-play-btn" id="audioPlayBtn" aria-label="Play audio">
            <svg class="icon-play" viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
              <path d="M8 5v14l11-7z"/>
            </svg>
            <svg class="icon-pause" viewBox="0 0 24 24" width="18" height="18" fill="currentColor" style="display:none;">
              <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>
            </svg>
          </button>

          <div class="audio-main">
            <div class="audio-meta-row">
              <span class="audio-title">${escapeHtml(title)}</span>
              <span class="audio-time" id="audioTimeDisplay">0:00 / 0:00</span>
            </div>

            <div class="audio-waveform" id="audioWaveformContainer">
              ${Array.from({ length: 20 })
                .map(() => `<div class="waveform-bar"></div>`)
                .join("")}
              <input type="range" class="audio-seek-slider" id="audioSeekSlider" min="0" max="100" value="0" step="0.1" />
            </div>
          </div>

          <div class="audio-controls">
            <button type="button" class="audio-action-btn" id="audioSpeedBtn" title="Speed">1x</button>
            <button type="button" class="audio-action-btn" id="audioMuteBtn" title="Mute/Unmute">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/>
              </svg>
            </button>
          </div>
        </div>
      `;

      state.mediaEl = document.getElementById("localPlayer");
      bindCustomAudioEvents();
    } else {
      // Default to HTML5 video element for videos
      el.videoEmbed.innerHTML = `
        <video
          id="localPlayer"
          src="${job.media_url}"
          controls
          preload="metadata"
        ></video>
      `;
      state.mediaEl = document.getElementById("localPlayer");
    }

    return;
  }

  el.videoEmbed.innerHTML = `
    <div
      style="
        display:flex;
        align-items:center;
        justify-content:center;
        height:100%;
        color:var(--text-tertiary);
        font-size:13px;
      "
    >
      No preview available
    </div>
  `;
}

function bindCustomAudioEvents() {
  const audio = state.mediaEl;
  if (!audio) return;

  const playBtn = document.getElementById("audioPlayBtn");
  const playIcon = playBtn.querySelector(".icon-play");
  const pauseIcon = playBtn.querySelector(".icon-pause");

  const timeDisplay = document.getElementById("audioTimeDisplay");
  const seekSlider = document.getElementById("audioSeekSlider");
  const waveformBars = document.querySelectorAll(".waveform-bar");
  const speedBtn = document.getElementById("audioSpeedBtn");
  const muteBtn = document.getElementById("audioMuteBtn");

  const speeds = [1, 1.25, 1.5, 2];
  let speedIdx = 0;

  waveformBars.forEach((bar) => {
    const h = Math.floor(Math.random() * 65) + 25;
    bar.style.height = `${h}%`;
  });

  playBtn.addEventListener("click", () => {
    if (audio.paused) {
      audio.play();
    } else {
      audio.pause();
    }
  });

  audio.addEventListener("play", () => {
    playIcon.style.display = "none";
    pauseIcon.style.display = "block";
  });

  audio.addEventListener("pause", () => {
    playIcon.style.display = "block";
    pauseIcon.style.display = "none";
  });

  audio.addEventListener("timeupdate", () => {
    if (!audio.duration) return;

    const current = audio.currentTime;
    const total = audio.duration;
    const percent = (current / total) * 100;

    seekSlider.value = percent;
    timeDisplay.textContent = `${formatDuration(current)} / ${formatDuration(total)}`;

    const barCount = waveformBars.length;
    const activeThreshold = Math.floor((percent / 100) * barCount);

    waveformBars.forEach((bar, index) => {
      bar.classList.toggle("active", index <= activeThreshold);
    });
  });

  audio.addEventListener("loadedmetadata", () => {
    timeDisplay.textContent = `0:00 / ${formatDuration(audio.duration)}`;
  });

  seekSlider.addEventListener("input", () => {
    if (!audio.duration) return;
    const seekTime = (seekSlider.value / 100) * audio.duration;
    audio.currentTime = seekTime;
  });

  speedBtn.addEventListener("click", () => {
    speedIdx = (speedIdx + 1) % speeds.length;
    const newSpeed = speeds[speedIdx];
    audio.playbackRate = newSpeed;
    speedBtn.textContent = `${newSpeed}x`;
  });

  muteBtn.addEventListener("click", () => {
    audio.muted = !audio.muted;
    muteBtn.style.opacity = audio.muted ? "0.4" : "1";
  });
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

  if (!Number.isFinite(seconds)) {
    return;
  }

  el.videoEmbed.scrollIntoView({
    behavior: "smooth",
    block: "center",
  });

  if (state.ytPlayer && state.ytReady) {
    state.ytPlayer.seekTo(seconds, true);
    state.ytPlayer.playVideo();
    return;
  }

  const media = state.mediaEl;

  if (!media) {
    return;
  }

  const seek = () => {
    const duration = media.duration;

    const target = Number.isFinite(duration)
      ? Math.min(Math.max(seconds, 0), duration)
      : Math.max(seconds, 0);

    try {
      media.currentTime = target;
    } catch (err) {
      return;
    }

    const playPromise = media.play();

    if (playPromise) {
      playPromise.catch(() => {});
    }
  };

  if (media.readyState >= HTMLMediaElement.HAVE_METADATA) {
    seek();
  } else {
    media.addEventListener("loadedmetadata", seek, {
      once: true,
    });
  }
}

function parseTimecode(label) {
  if (!label || typeof label !== "string") {
    return NaN;
  }

  const parts = label.trim().split(":").map(Number);

  if (parts.some((part) => !Number.isFinite(part))) {
    return NaN;
  }

  if (parts.length === 2) {
    return parts[0] * 60 + parts[1];
  }

  if (parts.length === 3) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
  }

  return NaN;
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

  el.transcriptList.querySelectorAll("li").forEach((item) => {
    item.addEventListener("click", () => {
      const badge = item.querySelector(".time-badge");

      if (badge) {
        seekTo(badge.dataset.time);
      }
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

function switchTab(name) {
  el.tabs
    .querySelectorAll(".tab")
    .forEach((t) => t.classList.toggle("active", t.dataset.tab === name));

  document
    .querySelectorAll(".tab-panel")
    .forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
}

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
