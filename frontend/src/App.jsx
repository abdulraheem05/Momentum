import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import "./App.css";

const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const PROCESS_STEPS = [
  { key: "queued", label: "Job queued", hint: "Preparing the worker" },
  { key: "processing", label: "Audio extraction", hint: "Downloading and extracting audio" },
  { key: "transcribing", label: "Transcription", hint: "Detecting spoken dialogue" },
  { key: "uploading", label: "Saving transcript", hint: "Uploading timestamped transcript" },
  { key: "ready", label: "Ready", hint: "Search is available" },
];

function cx(...classes) {
  return classes.filter(Boolean).join(" ");
}

function formatProgress(value) {
  const n = Number(value || 0);
  return Math.max(0, Math.min(100, Math.round(n)));
}

function getYouTubeId(url) {
  try {
    const parsed = new URL(url);

    if (parsed.hostname.includes("youtu.be")) {
      return parsed.pathname.replace("/", "");
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

function getStatusTone(status) {
  if (status === "ready") return "success";
  if (status === "failed") return "danger";
  if (status === "transcribing") return "accent";
  return "default";
}

export default function App() {
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [jobId, setJobId] = useState("");
  const [job, setJob] = useState(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [isCreatingJob, setIsCreatingJob] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState("");
  const [activityLog, setActivityLog] = useState([]);

  const pollRef = useRef(null);

  const progress = formatProgress(job?.progress);
  const status = job?.status || "";
  const isReady = status === "ready";
  const isFailed = status === "failed";
  const youtubeId = useMemo(() => getYouTubeId(youtubeUrl), [youtubeUrl]);

  const currentStepIndex = useMemo(() => {
    if (!status) return -1;

    const exactIndex = PROCESS_STEPS.findIndex((step) => step.key === status);
    if (exactIndex !== -1) return exactIndex;

    if (progress >= 100) return PROCESS_STEPS.length - 1;
    if (progress >= 85) return 3;
    if (progress >= 55) return 2;
    if (progress >= 10) return 1;
    return 0;
  }, [status, progress]);

  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!job?.message && !status) return;

    const text = job?.message || `Status updated to ${status}`;

    setActivityLog((prev) => {
      const last = prev[0];
      if (last?.text === text && last?.status === status) return prev;

      return [
        {
          id: `${Date.now()}-${Math.random()}`,
          text,
          status: status || "info",
          progress,
          time: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          }),
        },
        ...prev,
      ].slice(0, 8);
    });
  }, [job?.message, status, progress]);

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
            "Could not check the job status. Please make sure the backend is running."
        );
      }
    };

    fetchJob();
    pollRef.current = setInterval(fetchJob, 2500);
  };

  const startProcessing = async () => {
    const cleanUrl = youtubeUrl.trim();

    if (!cleanUrl) {
      setError("Paste a YouTube URL first.");
      return;
    }

    if (!getYouTubeId(cleanUrl)) {
      setError("This does not look like a valid YouTube URL.");
      return;
    }

    try {
      setError("");
      setResults([]);
      setJob(null);
      setJobId("");
      setActivityLog([]);
      setIsCreatingJob(true);

      const response = await axios.post(`${API}/youtube/jobs`, {
        youtube_url: cleanUrl,
      });

      setJobId(response.data.job_id);
      setJob({
        id: response.data.job_id,
        status: response.data.status || "queued",
        progress: response.data.progress || 0,
        message: response.data.message || "Job created.",
        youtube_id: response.data.youtube_id,
      });

      pollJob(response.data.job_id);
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          "Could not start processing. Check your backend, Modal URL, cookies, and API keys."
      );
    } finally {
      setIsCreatingJob(false);
    }
  };

  const searchDialogue = async () => {
    const cleanQuery = query.trim();

    if (!cleanQuery) {
      setError("Type the dialogue or phrase you want to find.");
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

      const response = await axios.post(`${API}/youtube/search-dialogue`, {
        job_id: jobId,
        query: cleanQuery,
      });

      setResults(response.data.results || []);
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          "Search failed. The transcript may not be ready yet."
      );
    } finally {
      setIsSearching(false);
    }
  };

  const resetWorkspace = () => {
    stopPolling();
    setYoutubeUrl("");
    setJobId("");
    setJob(null);
    setQuery("");
    setResults([]);
    setError("");
    setActivityLog([]);
  };

  return (
    <div className="momentum-app">

      <header className="topbar">
        <div className="brand">
          <div className="brandMark">M</div>
          <div>
            <h1>Momentum</h1>
            <p>YouTube dialogue intelligence</p>
          </div>
        </div>

        <div className="apiPill">
          <span className="pulseDot" />
          {API.replace("https://", "").replace("http://", "")}
        </div>
      </header>

      <main className="shell">
        <section className="hero">
          <div className="heroCopy">
            <div className="eyebrow">AI transcript search</div>
            <h2>Find the exact moment a dialogue appears in a YouTube video.</h2>
            <p>
              Paste a YouTube link, let Momentum process the audio, then search
              for remembered phrases with clickable timestamp results.
            </p>
          </div>

          <div className="heroCard">
            <div className="inputHeader">
              <div>
                <label>YouTube URL</label>
                <p>Paste a public YouTube video link</p>
              </div>

              {youtubeId && (
                <a
                  href={`https://www.youtube.com/watch?v=${youtubeId}`}
                  target="_blank"
                  rel="noreferrer"
                  className="tinyLink"
                >
                  Open source
                </a>
              )}
            </div>

            <div className="urlInputWrap">
              <input
                value={youtubeUrl}
                onChange={(e) => setYoutubeUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=..."
                disabled={isCreatingJob || (!!jobId && !isFailed && !isReady)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") startProcessing();
                }}
              />
            </div>

            <div className="actions">
              <button
                className="primaryBtn"
                onClick={startProcessing}
                disabled={isCreatingJob || (!!jobId && !isFailed && !isReady)}
              >
                {isCreatingJob ? (
                  <>
                    <span className="miniSpinner" />
                    Creating job
                  </>
                ) : (
                  "Start processing"
                )}
              </button>

              <button className="ghostBtn" onClick={resetWorkspace}>
                Reset
              </button>
            </div>

            {youtubeId && (
              <div className="previewStrip">
                <img
                  src={`https://img.youtube.com/vi/${youtubeId}/mqdefault.jpg`}
                  alt="YouTube thumbnail"
                />
                <div>
                  <span>Detected video</span>
                  <strong>{youtubeId}</strong>
                </div>
              </div>
            )}
          </div>
        </section>

        {error && (
          <div className="errorBox">
            <strong>Something needs attention</strong>
            <span>{error}</span>
          </div>
        )}

        {(job || isCreatingJob) && (
          <section className="processingGrid">
            <div className="progressCard">
              <div className="progressTop">
                <div>
                  <span className="sectionLabel">Processing status</span>
                  <h3>{job?.video_title || "Preparing video transcript"}</h3>
                </div>

                <div
                  className="progressRing"
                  style={{
                    "--progress": `${progress}%`,
                  }}
                >
                  <div>
                    <strong>{progress}</strong>
                    <span>%</span>
                  </div>
                </div>
              </div>

              <div className={cx("statusBadge", getStatusTone(status))}>
                {status || "creating"}
              </div>

              <p className="jobMessage">
                {job?.message ||
                  "Creating the job and connecting to the worker..."}
              </p>

              <div className="stepList">
                {PROCESS_STEPS.map((step, index) => {
                  const done = index < currentStepIndex;
                  const active = index === currentStepIndex;

                  return (
                    <div
                      key={step.key}
                      className={cx("stepItem", done && "done", active && "active")}
                    >
                      <div className="stepDot">
                        {done ? "✓" : active ? <span /> : ""}
                      </div>

                      <div>
                        <strong>{step.label}</strong>
                        <small>{step.hint}</small>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="thinkingCard">
              <div className="thinkingHeader">
                <span className="sectionLabel">Live worker messages</span>
                <div className="thinkingDots">
                  <span />
                  <span />
                  <span />
                </div>
              </div>

              <div className="logList">
                {activityLog.length === 0 ? (
                  <div className="emptyLog">
                    Waiting for the first worker update...
                  </div>
                ) : (
                  activityLog.map((item) => (
                    <div key={item.id} className="logItem">
                      <div className="logIcon" />
                      <div>
                        <strong>{item.text}</strong>
                        <span>
                          {item.time} · {item.progress}%
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </section>
        )}

        <section className={cx("searchCard", !isReady && "locked")}>
          <div className="searchIntro">
            <div>
              <span className="sectionLabel">Dialogue search</span>
              <h3>What dialogue do you remember?</h3>
              <p>
                Search exact phrases from the transcript. Results return the
                matching dialogue with a YouTube timestamp link.
              </p>
            </div>

            {!isReady && (
              <div className="lockPill">
                {isFailed ? "Processing failed" : "Available after processing"}
              </div>
            )}
          </div>

          <div className="searchBox">
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder='Example: "I am going to explain the architecture"'
              disabled={!isReady || isSearching}
              onKeyDown={(e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
                  searchDialogue();
                }
              }}
            />

            <button
              className="primaryBtn searchBtn"
              onClick={searchDialogue}
              disabled={!isReady || isSearching}
            >
              {isSearching ? (
                <>
                  <span className="miniSpinner" />
                  Searching
                </>
              ) : (
                "Search dialogue"
              )}
            </button>
          </div>
        </section>

        <section className="resultsSection">
          <div className="resultsHeader">
            <div>
              <span className="sectionLabel">Results</span>
              <h3>
                {results.length > 0
                  ? `${results.length} timestamp match${results.length > 1 ? "es" : ""}`
                  : "No results yet"}
              </h3>
            </div>
          </div>

          {isSearching && (
            <div className="skeletonList">
              <div />
              <div />
              <div />
            </div>
          )}

          {!isSearching && results.length === 0 && (
            <div className="emptyState">
              <div className="emptyOrb" />
              <h4>Search results will appear here</h4>
              <p>
                Once processing is ready, type a phrase and Momentum will return
                the exact timestamp and detected dialogue.
              </p>
            </div>
          )}

          {!isSearching && results.length > 0 && (
            <div className="resultGrid">
              {results.map((item, index) => (
                <article key={`${item.timestamp}-${index}`} className="resultCard">
                  <div className="resultNumber">
                    {(index + 1).toString().padStart(2, "0")}
                  </div>

                  <div className="resultMain">
                    <div className="timestampRow">
                      <a
                        href={item.youtube_url}
                        target="_blank"
                        rel="noreferrer"
                        className="timestampBtn"
                      >
                        ▶ {item.timestamp_label || `${item.timestamp}s`}
                      </a>

                      <span className="rawTime">{item.timestamp}s</span>
                    </div>

                    <p className="dialogueText">“{item.text}”</p>

                    <a
                      href={item.youtube_url}
                      target="_blank"
                      rel="noreferrer"
                      className="watchLink"
                    >
                      Watch from this moment →
                    </a>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}