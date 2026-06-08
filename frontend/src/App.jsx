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

async function fetchYouTubeMetadata(url) {
  const response = await axios.get("https://www.youtube.com/oembed", {
    params: {
      url,
      format: "json",
    },
  });

  return response.data;
}

function cleanApiLabel() {
  return API.replace("https://", "").replace("http://", "").replace(/\/$/, "");
}

function formatScore(score) {
  if (score === null || score === undefined || Number.isNaN(Number(score))) return "";
  return `${Math.round(Number(score) * 100)}% match`;
}

function getThinkingTitle(job, selectedMode, isCreatingJob, sourceType = "youtube") {
  if (isCreatingJob) {
    return sourceType === "upload" ? "Uploading local file" : "Creating Momentum job";
  }

  if (!job) {
    return sourceType === "upload" ? "Waiting for a local file" : "Waiting for a YouTube URL";
  }

  if (job.status === "ready") {
    return selectedMode === "video" ? "Video scene index ready" : "Audio transcript ready";
  }

  if (job.status === "failed") return "Processing failed";

  if (job.status === "queued") {
    return sourceType === "upload" ? "File submitted for processing" : "Video submitted for processing";
  }

  return job.message || "Momentum is processing";
}

function getProgressColor(progress) {
  if (progress < 25) {
    return "linear-gradient(180deg, #dbeafe 0%, #93c5fd 100%)";
  }

  if (progress < 50) {
    return "linear-gradient(180deg, #bfdbfe 0%, #60a5fa 100%)";
  }

  if (progress < 75) {
    return "linear-gradient(180deg, #c4b5fd 0%, #818cf8 100%)";
  }

  if (progress < 100) {
    return "linear-gradient(180deg, #ddd6fe 0%, #a78bfa 100%)";
  }

  return "linear-gradient(180deg, #bbf7d0 0%, #22c55e 100%)";
}

function createResultLabel(mode, item, index) {
  if (mode === "audio") return item.text || "Detected dialogue";

  const scene = item.scene_index !== undefined && item.scene_index !== null
    ? `Scene ${item.scene_index}`
    : `Visual match ${index + 1}`;

  const score = formatScore(item.score);
  return score ? `${scene} · ${score}` : scene;
}

function formatDuration(ms) {
  if (!ms) return "";

  const totalSeconds = Math.round(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes > 0) {
    return `${minutes} min ${seconds} sec`;
  }

  return `${seconds} sec`;
}

function formatTimestamp(seconds) {
  const totalSeconds = Math.floor(Number(seconds || 0));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;

  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }

  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function buildYouTubeTimestampUrl(urlOrId, seconds) {
  const cleanValue = String(urlOrId || "").trim();
  const timestamp = Math.floor(Number(seconds || 0));

  const youtubeId = cleanValue.includes("youtube") || cleanValue.includes("youtu.be")
    ? getYouTubeId(cleanValue)
    : cleanValue;

  return youtubeId
    ? `https://www.youtube.com/watch?v=${youtubeId}&t=${timestamp}s`
    : "";
}

function formatFileSize(bytes) {
  if (!bytes) return "";

  const mb = bytes / (1024 * 1024);

  if (mb >= 1) {
    return `${mb.toFixed(1)} MB`;
  }

  return `${Math.round(bytes / 1024)} KB`;
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
  const [currentVerbose, setCurrentVerbose] = useState("Waiting to start...");
  const [displayProgress, setDisplayProgress] = useState(0);
  const [videoMeta, setVideoMeta] = useState(null);
  const [isFetchingMeta, setIsFetchingMeta] = useState(false);
  const [modeMenuOpen, setModeMenuOpen] = useState(false);
  const [processingStartTime, setProcessingStartTime] = useState(null);
  const [processingDuration, setProcessingDuration] = useState(null);
  const [sourceType, setSourceType] = useState("youtube"); // "youtube" | "upload"
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploadingFile, setIsUploadingFile] = useState(false); 
  const [isDraggingFile, setIsDraggingFile] = useState(false); 
  const [showSplash, setShowSplash] = useState(true);

  const [splashExiting, setSplashExiting] = useState(false);
  const [appReady, setAppReady] = useState(false);

  const pollRef = useRef(null);
  const modePickerRef = useRef(null);
  const uploadModeRowRef = useRef(null);

  const activeUrl = submittedUrl || youtubeUrl;
  const youtubeId = useMemo(() => getYouTubeId(activeUrl), [activeUrl]);
  const previewYoutubeId = useMemo(() => getYouTubeId(youtubeUrl), [youtubeUrl]);
  const videoTitle =
    videoMeta?.title ||
    job?.video_title ||
    job?.title ||
    job?.youtube_title ||
    job?.metadata?.title ||
    "YouTube video";

  const progress = clampProgress(job?.progress);
  const isReady = job?.status === "ready";
  const isFailed = job?.status === "failed";
  const hasStarted = Boolean(jobId || job);
  const selectedMode = MODE_OPTIONS[mode];

  useEffect(() => {
    return () => stopPolling();
  }, []);

  useEffect(() => {
    const cleanUrl = youtubeUrl.trim();
    const cleanYoutubeId = getYouTubeId(cleanUrl);

    if (!cleanUrl || !cleanYoutubeId) {
      setVideoMeta(null);
      setIsFetchingMeta(false);
      return;
    }

    const timeout = setTimeout(async () => {
      try {
        setIsFetchingMeta(true);

        const data = await fetchYouTubeMetadata(cleanUrl);

        setVideoMeta({
          title: data.title,
          author: data.author_name,
          thumbnail: data.thumbnail_url,
        });
      } catch {
        setVideoMeta({
          title: "YouTube video",
          author: "",
          thumbnail: `https://img.youtube.com/vi/${cleanYoutubeId}/hqdefault.jpg`,
        });
      } finally {
        setIsFetchingMeta(false);
      }
    }, 350);

    return () => clearTimeout(timeout);
  }, [youtubeUrl]);

  useEffect(() => {
    const exitTimer = setTimeout(() => {
      setSplashExiting(true);
      setAppReady(true);
    }, 2600);

    const removeTimer = setTimeout(() => {
      setShowSplash(false);
    }, 3300);

    return () => {
      clearTimeout(exitTimer);
      clearTimeout(removeTimer);
    };
  }, []);

  useEffect(() => {
    if (!job?.message && !job?.status) return;

    if (job?.status === "ready" && processingDuration) return;
    if (job?.status === "failed" && processingDuration) return;

    const message = job?.message || `Status changed to ${job.status}`;
    setCurrentVerbose(message);
  }, [job?.message, job?.status, processingDuration]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        modePickerRef.current &&
        !modePickerRef.current.contains(event.target)
      ) {
        setModeMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  useEffect(() => {
      const target = progress;

      const interval = setInterval(() => {
        setDisplayProgress((current) => {
          if (current === target) {
            clearInterval(interval);
            return current;
          }

          if (current < target) {
            return Math.min(current + 1, target);
          }

          return Math.max(current - 1, target);
        });
      }, 18);

      return () => clearInterval(interval);
    }, [progress]);

    useEffect(() => {
    if (sourceType !== "upload") return;
    if (!modeMenuOpen) return;

    setTimeout(() => {
      uploadModeRowRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }, 80);
  }, [modeMenuOpen, sourceType]);


  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const pollJob = (id, source = sourceType) => {
  stopPolling();

  const fetchJob = async () => {
    try {
      const endpoint =
        source === "upload"
          ? `${API}/upload/jobs/${id}`
          : `${API}/youtube/jobs/${id}`;

      const response = await axios.get(endpoint);
      const latestJob = response.data;

      setJob(latestJob);

      if (latestJob.status === "ready" || latestJob.status === "failed") {
        stopPolling();

        setProcessingStartTime((startedAt) => {
          if (startedAt) {
            const duration = Date.now() - startedAt;
            setProcessingDuration(duration);

            if (latestJob.status === "ready") {
              setCurrentVerbose(
                `Task completed in ${formatDuration(duration)}. You can now search this ${source === "upload" ? "file" : "video"}.`
              );
            } else {
              setCurrentVerbose(
                `Task stopped after ${formatDuration(duration)} because processing failed.`
              );
            }
          }

          return startedAt;
        });
      }
    } catch (err) {
      stopPolling();
      setError(
        err?.response?.data?.detail ||
          "Could not read the job status. Check whether the backend is running."
      );

      setSelectedFile(null);
      setUploadProgress(0);
      setIsUploadingFile(false);
      setIsCreatingJob(false);
      setJob(null);
      setJobId("");
      setModeMenuOpen(false);
      setCurrentVerbose("Waiting to start...");
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
      const startedAt = Date.now();

      setError("");
      setResults([]);
      setQuery("");
      setJob(null);
      setJobId("");
      setSourceType("youtube");
      setUploadProgress(0);
      setSelectedFile(null);

      setProcessingStartTime(startedAt);
      setProcessingDuration(null);

      setCurrentVerbose("Creating Momentum job...");
      setDisplayProgress(0);
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

      pollJob(response.data.job_id, "youtube");
    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          "Could not start processing. Check your backend URL, Modal endpoint, and environment variables."
      );
    } finally {
      setIsCreatingJob(false);
    }
  };

  const startUploadProcessing = async (file) => {
  if (!file) return;

  try {
    const startedAt = Date.now();

    setError("");
    setResults([]);
    setQuery("");
    setJob(null);
    setJobId("");
    setSubmittedUrl("");
    setYoutubeUrl("");
    setVideoMeta(null);

    setSelectedFile(file);
    setProcessingStartTime(startedAt);
    setProcessingDuration(null);

    setCurrentVerbose("Uploading file...");
    setDisplayProgress(0);
    setUploadProgress(0);
    setIsUploadingFile(true);
    setIsCreatingJob(true);

    const presignResponse = await axios.post(`${API}/upload/presign`, {
      filename: file.name,
      content_type: file.type || "application/octet-stream",
      file_size: file.size,
      mode,
    });

    const {
      sas_upload_url,
      blob_name,
      blob_url,
      content_type,
    } = presignResponse.data;

    await axios.put(sas_upload_url, file, {
      headers: {
        "x-ms-blob-type": "BlockBlob",
        "Content-Type": file.type || "application/octet-stream",
      },
      onUploadProgress: (progressEvent) => {
        if (!progressEvent.total) return;

        const percent = Math.round(
          (progressEvent.loaded * 100) / progressEvent.total
        );

        setUploadProgress(percent);

        if (percent < 100) {
          setCurrentVerbose("Uploading file directly to cloud storage...");
        } else {
          setCurrentVerbose("File uploaded. Starting processing...");
          setJob({
            id: "upload-pending",
            source_type: "upload",
            mode,
            status: "processing",
            progress: 10,
            message: "Creating processing job...",
            original_file_name: file.name,
            media_content_type: file.type,
          });
          setDisplayProgress(10);
        }
      },
    });

    const completeResponse = await axios.post(`${API}/upload/complete`, {
      filename: file.name,
      mode,
      blob_name,
      blob_url,
      content_type: content_type || file.type || "application/octet-stream",
      file_size: file.size,
    });

    setJobId(completeResponse.data.job_id);

    setJob({
      id: completeResponse.data.job_id,
      source_type: "upload",
      mode: completeResponse.data.mode || mode,
      status: completeResponse.data.status || "queued",
      progress: completeResponse.data.progress || 15,
      message: completeResponse.data.message || "File uploaded. Processing started.",
      original_file_name: completeResponse.data.file_name,
      media_blob_url: completeResponse.data.media_blob_url,
    });

    setCurrentVerbose(completeResponse.data.message || "File uploaded. Processing started.");
    pollJob(completeResponse.data.job_id, "upload");
  } catch (err) {
      setError(
        err?.response?.data?.detail ||
          "Could not upload file. Check backend, Azure settings, and file size."
      );

      setSelectedFile(null);
      setUploadProgress(0);
      setIsUploadingFile(false);
      setIsCreatingJob(false);
      setJob(null);
      setJobId("");
      setModeMenuOpen(false);
      setCurrentVerbose("Waiting to start...");

  } finally {
    setIsUploadingFile(false);
    setIsCreatingJob(false);
  }
};

  const handleDroppedFile = (event) => {
    event.preventDefault();
    event.stopPropagation();

    setIsDraggingFile(false);

    const file = event.dataTransfer.files?.[0];

    if (file) {
      startUploadProcessing(file);
    }
  };

  const searchMomentum = async () => {
    const cleanQuery = query.trim();

    if (!cleanQuery) {
      setError(mode === "video" ? "Describe the visual scene you want to find." : "Type the dialogue you want to find.");
      return;
    }

    if (!jobId) {
      setError(sourceType === "upload" ? "Upload and process a file first." : "Process a YouTube video first.");
      return;
    }

    try {
      setError("");
      setIsSearching(true);
      setResults([]);

      const searchEndpoint =
      sourceType === "upload"
        ? mode === "video"
          ? "/upload/search-visual"
          : "/upload/search-dialogue"
        : selectedMode.searchEndpoint;

    const response = await axios.post(`${API}${searchEndpoint}`, {
      job_id: jobId,
      query: cleanQuery,
    });

    const sortedResults = [...(response.data.results || [])].sort(
      (a, b) => Number(b.score || b.similarity || 0) - Number(a.score || a.similarity || 0)
    );

    setResults(sortedResults);

    } catch (err) {
      setError(
        err?.response?.data?.detail ||
          `Could not search ${mode === "video" ? "visual scenes" : "audio dialogue"}.`
      );
    } finally {
      setIsSearching(false);
    }
  };

  const cleanupUploadedFile = async () => {
    if (sourceType !== "upload") return;
    if (!jobId) return;

    try {
      await axios.delete(`${API}/upload/jobs/${jobId}/file`);
    } catch (err) {
      console.warn("Could not delete uploaded Azure file:", err);
    }
  };

  const resetWorkspace = async () => {
    await cleanupUploadedFile();

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
    setCurrentVerbose("Waiting to start...");
    setDisplayProgress(0);
    setVideoMeta(null);
    setIsFetchingMeta(false);
    setProcessingStartTime(null);
    setProcessingDuration(null);
    setSourceType("youtube");
    setSelectedFile(null);
    setUploadProgress(0);
    setIsUploadingFile(false);
  };

  return (
    <>
    {showSplash && (
      <div className={cx("splash-screen", splashExiting && "exiting")}>
        <video
          className="splash-video"
          src="/MomentumSplashh.mp4"
          autoPlay
          muted
          playsInline
          preload="auto"
          onEnded={() => {
            setSplashExiting(true);
            setAppReady(true);

            setTimeout(() => {
              setShowSplash(false);
            }, 700);
          }}
        />

        <div className="splash-glow" />
      </div>
    )}

    
    <div
      className={cx(
        "momentum-app",
        appReady && "app-ready",
        hasStarted && "conversation-mode",
        modeMenuOpen && !hasStarted && "mode-menu-open"
      )}
    >
      <main className="momentum-shell">
        <section className="intro-panel">
          <div className="brand-center">
            <img src="/Momentum Full logo.png-2.png" alt="" />
            <p>
              {sourceType === "youtube"
                ? "Search any YouTube video by what you see or what you hear."
                : "Upload a local file and search by scenes or dialogue."}
            </p>
          </div>

          {!hasStarted && (
            <div className="source-switcher">
              <button
                type="button"
                className={sourceType === "youtube" ? "active" : ""}
                onClick={() => setSourceType("youtube")}
              >
                YouTube Video
              </button>

              <button
                type="button"
                className={sourceType === "upload" ? "active" : ""}
                onClick={() => setSourceType("upload")}
              >
                Local Files
              </button>

              <span className={cx("source-switcher-thumb", sourceType)} />
            </div>
          )}


          <div className="gemini-composer source-composer">

            {sourceType === "youtube" ? (
            <>
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
                  <div className="mode-picker" ref={modePickerRef}>
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
                                <strong>
                                  {item.label}
                                  {item.id === "audio" && <span className="language-badge">EN</span>}
                                </strong>
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
                    src={videoMeta?.thumbnail || `https://img.youtube.com/vi/${previewYoutubeId}/mqdefault.jpg`}
                    alt="YouTube thumbnail preview"
                  />
                  <div>
                    <strong>
                      {isFetchingMeta ? "Fetching video title..." : videoMeta?.title || "YouTube video detected"}
                    </strong>

                    <span>
                      {videoMeta?.author ? `${videoMeta.author} · ` : ""}
                      {buildWatchUrl(previewYoutubeId)}
                    </span>
                  </div>
                </div>
              )}
            </>
          ) : (

            <div className={cx("upload-composer", modeMenuOpen && "mode-open")}>
              <p className="local-upload-note">
              Local file processing can be slower due to upload speed limit. For a quicker demo, try YouTube search.
            </p>
              <label
                className={cx(
                  "upload-dropzone",
                  isDraggingFile && "dragging",
                  (isCreatingJob || isUploadingFile) && "uploading"
                )}
                onDragEnter={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setIsDraggingFile(true);
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setIsDraggingFile(true);
                }}
                onDragLeave={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setIsDraggingFile(false);
                }}
                onDrop={handleDroppedFile}
              >
                

                <input
                  type="file"
                  accept="video/*,audio/*"
                  hidden
                  disabled={isCreatingJob || (!!jobId && !isFailed)}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) startUploadProcessing(file);
                  }}
                />

                <div className="upload-icon-card">
                  <img src="/icons/Files.png" alt="" />
                </div>

                <strong>
                  {selectedFile ? selectedFile.name : "Drop your file here, or browse"}
                </strong>

                <small>
                  Supports MP4, MOV, WEBM, MP3, WAV
                </small>
              </label>

              <div className="upload-mode-row" ref={uploadModeRowRef}>

                <div className="mode-picker" ref={modePickerRef}>
                  <button
                    type="button"
                    className="mode-trigger"
                    onClick={() => setModeMenuOpen((prev) => !prev)}
                    disabled={isCreatingJob || (!!jobId && !isFailed)}
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
                              <strong>
                                {item.label}
                                {item.id === "audio" && <span className="language-badge">EN</span>}
                              </strong>
                              <small>{item.description}</small>
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              {(isUploadingFile || uploadProgress > 0) && !hasStarted && (
                <div className="upload-progress-wrap">
                  <div className="upload-progress-top">
                    <span>{selectedFile?.name || "Uploading file"}</span>
                    <strong>
                      {uploadProgress < 100 ? `${uploadProgress}%` : "Uploaded"}
                    </strong>
                  </div>

                  <div className="upload-progress-track">
                    <div
                      className="upload-progress-fill"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                </div>
              )}
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
              {sourceType === "youtube" ? (
                <img
                  src={`https://img.youtube.com/vi/${youtubeId}/hqdefault.jpg`}
                  alt="Processed YouTube video thumbnail"
                />
              ) : (
                <div className="uploaded-file-visual">
                  <span>{mode === "video" ? "VIDEO" : "AUDIO"}</span>
                </div>
              )}

              <div className="source-message-content">
                <div className="source-topline">
                  <span className={cx("mode-pill", mode)}>
                    
                    {selectedMode.label}
                  </span>
                </div>

                <h2>
                {sourceType === "upload"
                  ? job?.original_file_name || selectedFile?.name || "Uploaded file"
                  : videoTitle}
              </h2>

              {sourceType === "youtube" ? (
                <a href={buildWatchUrl(youtubeId)} target="_blank" rel="noreferrer">
                  {submittedUrl || buildWatchUrl(youtubeId)}
                </a>
              ) : (
                <span className="local-file-caption">
                  {selectedFile?.type || job?.media_content_type || "Local file"}{" "}
                  {selectedFile?.size ? `· ${formatFileSize(selectedFile.size)}` : ""}
                </span>
              )}
              </div>
            </article>

            <section className="thinking-stage">
              <div
                className={cx("liquid-orb", isReady && "complete", isFailed && "failed")}
                style={{
                  "--progress": `${displayProgress}%`,
                  "--fill-color": getProgressColor(displayProgress),
                }}
                aria-label={`Processing progress ${displayProgress}%`}
              >
                <div className="liquid" />
                <div className="orb-glass" />
                <div className="orb-content">
                  {isReady ? (
                      <span className="tick-mark">✓</span>
                    ) : isFailed ? (
                      <span>!</span>
                    ) : (
                      <span>{displayProgress}</span>
                    )}
                </div>
              </div>

              <div className="thinking-copy">
                <div className="thinking-line-main">
                  <span>{getThinkingTitle(job, mode, isCreatingJob, sourceType)}</span>
                  {!isReady && !isFailed && (
                    <span className="typing-dots" aria-hidden="true">
                      <i />
                      <i />
                      <i />
                    </span>
                  )}
                </div>

                <div className="verbose-single" key={currentVerbose}>
                  <p className="verbose-item active">{currentVerbose}</p>
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
                  <>
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

                      const resultUrl =
                        result.youtube_url ||
                        result.url ||
                        result.timestamp_url ||
                        buildYouTubeTimestampUrl(
                          job?.youtube_url || submittedUrl,
                          result.timestamp || result.start_time || result.start || 0
                        );

                      if (sourceType === "upload") {
                        return (
                          <div
                            key={`${timestamp}-${index}`}
                            className="result-pill local-result-pill"
                          >
                            <span className="result-time">{timestamp}</span>
                            <span className="result-score">{score}% match</span>
                          </div>
                        );
                      }

                      return (
                        <a
                          key={`${timestamp}-${index}`}
                          className="result-pill"
                          href={resultUrl}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <span className="result-time">{timestamp}</span>
                          <span className="result-score">{score}% match</span>
                        </a>
                      );
                    })}
                  </div>
                  <div className="new-video-action">
                    <button
                      type="button"
                      className="search-new-video-button"
                      onClick={resetWorkspace}
                    >
                      Search new video
                    </button>
                  </div>
                  </>
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
    </>
  );
}
