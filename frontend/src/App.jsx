import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import "./App.css";

const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const MODE_OPTIONS = {
  video: {
    label: "Scene Search",
    helper: "Find visual scenes using CLIP embeddings",
    placeholder: "Describe the scene you want to find...",
    searchEndpoint: "/youtube/search-visual",
  },
  audio: {
    label: "Dialogue Search",
    helper: "Find spoken dialogue from transcript",
    placeholder: "Type the dialogue or phrase you remember...",
    searchEndpoint: "/youtube/search-dialogue",
  },
};

const SEARCH_MODES = [
  {
    id: "video",
    label: "Scene Search",
    description: "Search scenes visually",
  },
  {
    id: "audio",
    label: "Dialogue Search",
    description: "Search spoken dialogue",
  },
];

function cx(...classes) {
  return classes.filter(Boolean).join(" ");
}

function clampProgress(value) {
  const n = Number(value || 0);
  return Math.max(0, Math.min(100, Math.round(n)));
}

function getYouTubeId(url) {
  try {
    const parsed = new URL(url.trim());

    if (parsed.hostname.includes("youtu.be")) {
      return parsed.pathname.replace("/", "").split("?")[0];
    }

    if (parsed.searchParams.get("v")) {
      return parsed.searchParams.get("v");
    }

    const shortsMatch = parsed.pathname.match(/\/shorts\/([^/?]+)/);
    if (shortsMatch) return shortsMatch[1];

    return "";
  } catch {
    return "";
  }
}

function buildWatchUrl(youtubeId) {
  return youtubeId ? `https://www.youtube.com/watch?v=${youtubeId}` : "";
}

function cleanApiLabel() {
  return API.replace("https://", "").replace("http://", "").replace(/\/$/, "");
}

function formatScore(score) {
  if (score === null || score === undefined || Number.isNaN(Number(score))) return "";
  return `${Math.round(Number(score) * 100)}% match`;
}

function getThinkingTitle(job, selectedMode, isCreatingJob) {
  if (isCreatingJob) return "Creating Momentum job";
  if (!job) return "Waiting for a YouTube URL";
  if (job.status === "ready") {
    return selectedMode === "video" ? "Video scene index ready" : "Audio transcript ready";
  }
  if (job.status === "failed") return "Processing failed";
  return job.message || "Momentum is processing";
}

function createResultLabel(mode, item, index) {
  if (mode === "audio") return item.text || "Detected dialogue";

  const scene = item.scene_index !== undefined && item.scene_index !== null
    ? `Scene ${item.scene_index}`
    : `Visual match ${index + 1}`;

  const score = formatScore(item.score);
  return score ? `${scene} · ${score}` : scene;
}

export default function App() {
  const [mode, setMode] = useState("video");
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [submittedUrl, setSubmittedUrl] = useState("");
  const [jobId, setJobId] = useState("");
  const [job, setJob] = useState(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [isCreatingJob, setIsCreatingJob] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState("");
  const [thinkingFeed, setThinkingFeed] = useState([]);
  const [modeMenuOpen, setModeMenuOpen] = useState(false);

  const pollRef = useRef(null);

  const activeUrl = submittedUrl || youtubeUrl;
  const youtubeId = useMemo(() => getYouTubeId(activeUrl), [activeUrl]);
  const previewYoutubeId = useMemo(() => getYouTubeId(youtubeUrl), [youtubeUrl]);
  const progress = clampProgress(job?.progress);
  const isReady = job?.status === "ready";
  const isFailed = job?.status === "failed";
  const hasStarted = Boolean(jobId || job || isCreatingJob);
  const selectedMode = MODE_OPTIONS[mode];
  

  useEffect(() => {
    return () => stopPolling();
  }, []);

  useEffect(() => {
    if (!job?.message && !job?.status) return;

    const message = job?.message || `Status changed to ${job.status}`;

    setThinkingFeed((prev) => {
      if (prev[0]?.message === message && prev[0]?.progress === progress) return prev;

      return [
        {
          id: `${Date.now()}-${Math.random()}`,
          message,
          status: job.status,
          progress,
        },
        ...prev,
      ].slice(0, 5);
    });
  }, [job?.message, job?.status, progress]);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const pollJob = (id) => {
    stopPolling();

    const fetchJob = async () => {
      try {
        const response = await axios.get(`${API}/youtube/jobs/${id}`);
        const latestJob = response.data;

        setJob(latestJob);

        if (latestJob.status === "ready" || latestJob.status === "failed") {
          stopPolling();
        }
      } catch (err) {
        stopPolling();
        setError(
          err?.response?.data?.detail ||
            "Could not read the job status. Check whether the backend is running."
        );
      }
    };

    fetchJob();
    pollRef.current = setInterval(fetchJob, 2400);
  };

  const startProcessing = async () => {
    const cleanUrl = youtubeUrl.trim();
    const cleanYoutubeId = getYouTubeId(cleanUrl);

    if (!cleanUrl) {
      setError("Paste a YouTube URL first.");
      return;
    }

    if (!cleanYoutubeId) {
      setError("This does not look like a valid YouTube URL.");
      return;
    }

    try {
      setError("");
      setResults([]);
      setQuery("");
      setJob(null);
      setJobId("");
      setThinkingFeed([]);
      setSubmittedUrl(cleanUrl);
      setIsCreatingJob(true);

      const response = await axios.post(`${API}/youtube/jobs`, {
        youtube_url: cleanUrl,
        mode,
      });

      setJobId(response.data.job_id);
      setJob({
        id: response.data.job_id,
        youtube_id: response.data.youtube_id,
        mode: response.data.mode || mode,
        status: response.data.status || "queued",
        progress: response.data.progress || 0,
        message: response.data.message || `${MODE_OPTIONS[mode].label} job created.`,
      });

      pollJob(response.data.job_id);
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          "Could not start processing. Check your backend URL, Modal endpoint, and environment variables."
      );
    } finally {
      setIsCreatingJob(false);
    }
  };

  const searchMomentum = async () => {
    const cleanQuery = query.trim();

    if (!cleanQuery) {
      setError(mode === "video" ? "Describe the visual scene you want to find." : "Type the dialogue you want to find.");
      return;
    }

    if (!jobId) {
      setError("Process a YouTube video first.");
      return;
    }

    try {
      setError("");
      setIsSearching(true);
      setResults([]);

      const response = await axios.post(`${API}${selectedMode.searchEndpoint}`, {
        job_id: jobId,
        query: cleanQuery,
      });

      setResults(response.data.results || []);
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          `Could not search ${mode === "video" ? "visual scenes" : "audio dialogue"}.`
      );
    } finally {
      setIsSearching(false);
    }
  };

  const resetWorkspace = () => {
    stopPolling();
    setMode("video");
    setYoutubeUrl("");
    setSubmittedUrl("");
    setJobId("");
    setJob(null);
    setQuery("");
    setResults([]);
    setIsCreatingJob(false);
    setIsSearching(false);
    setError("");
    setThinkingFeed([]);
  };

  return (
    <div className={cx("momentum-app", hasStarted && "conversation-mode")}>
      <main className="momentum-shell">
        <section className="intro-panel">
          <div className="brand-center">
            <h1>Momentum</h1>
            <p>Search any YouTube video by what you see or what you hear.</p>
          </div>

          <div className="gemini-composer source-composer">
            <div className="composer-input-row">
              <input
                value={youtubeUrl}
                onChange={(e) => setYoutubeUrl(e.target.value)}
                placeholder="Paste a YouTube URL"
                disabled={isCreatingJob || (!!jobId && !isFailed)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") startProcessing();
                }}
              />
              <label className={cx("mode-dropdown", mode)}>
                <div className="mode-picker">
                  <button
                    type="button"
                    className="mode-trigger"
                    onClick={() => setModeMenuOpen((prev) => !prev)}
                  >
                    <span className="mode-icon-slot">
                      {mode === "video" ? (
                        <img src="/icons/video.svg" alt="" />
                      ) : (
                        <img src="/icons/audio.svg" alt="" />
                      )}
                    </span>

                    <span className="mode-trigger-label">
                      {mode === "video" ? "Scene Search" : "Dialogue Search"}
                    </span>

                    
                  </button>

                  {modeMenuOpen && (
                    <div className="mode-menu">
                      {SEARCH_MODES.map((item) => {
                        const selected = mode === item.id;

                        return (
                          <button
                            key={item.id}
                            type="button"
                            className={selected ? "mode-menu-item selected" : "mode-menu-item"}
                            onClick={() => {
                              setMode(item.id);
                              setModeMenuOpen(false);
                            }}
                          >
                            <span className="mode-icon-slot menu-icon">
                              {item.id === "video" ? (
                                <img src="/icons/video.svg" alt="" />
                              ) : (
                                <img src="/icons/audio.svg" alt="" />
                              )}
                            </span>

                            <span className="mode-copy">
                              <strong>{item.label}</strong>
                              <small>{item.description}</small>
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

              </label>

              <button
                className="send-button"
                onClick={startProcessing}
                disabled={isCreatingJob || (!!jobId && !isFailed)}
                aria-label="Start processing"
              >
                {isCreatingJob ? <span className="button-spinner" /> : "➜"}
              </button>
            </div>


            {previewYoutubeId && !hasStarted && (
              <div className="instant-preview">
                <img
                  src={`https://img.youtube.com/vi/${previewYoutubeId}/mqdefault.jpg`}
                  alt="YouTube thumbnail preview"
                />
                <div>
                  <strong>YouTube video detected</strong>
                  <span>{buildWatchUrl(previewYoutubeId)}</span>
                </div>
              </div>
            )}
          </div>

          {error && (
            <div className="error-message">
              <strong>Attention</strong>
              <span>{error}</span>
            </div>
          )}
        </section>

        {hasStarted && (
          <section className="conversation-panel">
            <article className="source-message">
              <img
                src={`https://img.youtube.com/vi/${youtubeId}/hqdefault.jpg`}
                alt="Processed YouTube video thumbnail"
              />

              <div className="source-message-content">
                <div className="source-topline">
                  <span className={cx("mode-pill", mode)}>
                    
                    {selectedMode.label}
                  </span>

                  <button className="text-reset" onClick={resetWorkspace}>
                    New video
                  </button>
                </div>

                <h2>{job?.video_title || "YouTube video"}</h2>
                <a href={buildWatchUrl(youtubeId)} target="_blank" rel="noreferrer">
                  {submittedUrl || buildWatchUrl(youtubeId)}
                </a>
              </div>
            </article>

            <section className="thinking-stage">
              <div
                className={cx("liquid-orb", isReady && "complete", isFailed && "failed")}
                style={{ "--progress": `${progress}%` }}
                aria-label={`Processing progress ${progress}%`}
              >
                <div className="liquid" />
                <div className="orb-glass" />
                <div className="orb-content">
                  {isReady ? <span className="tick-mark">✓</span> : isFailed ? <span>!</span> : <span>{progress}</span>}
                </div>
              </div>

              <div className="thinking-copy">
                <div className="thinking-line-main">
                  <span>{getThinkingTitle(job, mode, isCreatingJob)}</span>
                  {!isReady && !isFailed && (
                    <span className="typing-dots" aria-hidden="true">
                      <i />
                      <i />
                      <i />
                    </span>
                  )}
                </div>

                <div className="verbose-stack">
                  {thinkingFeed.length === 0 ? (
                    <p className="verbose-item active">Connecting to Modal worker...</p>
                  ) : (
                    thinkingFeed.map((item, index) => (
                      <p
                        key={item.id}
                        className={cx("verbose-item", index === 0 && "active")}
                      >
                        {item.message}
                      </p>
                    ))
                  )}
                </div>
              </div>
            </section>

            {isReady && (
              <section className="query-section">
                <div className="query-heading">
                  <h3>{mode === "video" ? "Describe a scene" : "Search the dialogue"}</h3>
                  <p>
                    {mode === "video"
                      ? "Example: a person speaking on stage, a laptop screen, a whiteboard explanation."
                      : "Example: type a phrase you remember from the spoken transcript."}
                  </p>
                </div>

                <div className="gemini-composer query-composer">
                  <div className="composer-input-row">
                    <div className={cx("mode-chip", mode)}>
                      <span className="custom-icon-slot" aria-hidden="true">
                        {mode === "video" ? "▣" : "◖"}
                      </span>
                      <span>{selectedMode.label}</span>
                    </div>

                    <input
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder={selectedMode.placeholder}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") searchMomentum();
                      }}
                      disabled={isSearching}
                    />

                    <button
                      className="send-button"
                      onClick={searchMomentum}
                      disabled={isSearching}
                      aria-label="Search"
                    >
                      {isSearching ? <span className="button-spinner" /> : "➜"}
                    </button>
                  </div>
                </div>
              </section>
            )}

            {(isSearching || results.length > 0) && (
              <section className="results-panel">
                {isSearching && (
                  <div className="search-thinking">
                    <span>Searching the {mode === "video" ? "visual index" : "transcript"}</span>
                    <span className="typing-dots" aria-hidden="true">
                      <i />
                      <i />
                      <i />
                    </span>
                  </div>
                )}

                {!isSearching && results.length > 0 && (
                  <div className="results-list compact-results">
                    {results.map((result, index) => {
                      const timestamp =
                        result.timestamp_label ||
                        result.time_label ||
                        formatTimestamp(result.timestamp || result.start_time || result.start || 0);

                      const score =
                        result.score_percent ||
                        result.match_percent ||
                        result.similarity_percent ||
                        Math.round((result.score || result.similarity || 0) * 100);

                      const youtubeUrl =
                        result.youtube_url ||
                        result.url ||
                        result.timestamp_url ||
                        buildYouTubeTimestampUrl(
                          job?.youtube_url || youtubeUrl,
                          result.timestamp || result.start_time || result.start || 0
                        );

                      return (
                        <a
                          key={`${timestamp}-${index}`}
                          className="result-pill"
                          href={youtubeUrl}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <span className="result-time">{timestamp}</span>
                          <span className="result-score">{score}% match</span>
                        </a>
                      );
                    })}
                  </div>
                )}
              </section>
            )}
          </section>
        )}
      </main>

      <footer className="demo-note">
        Momentum can make mistakes. Demo mode currently processes on CPU, so longer videos may take more time than production GPU processing.
      </footer>
    </div>
  );
}
