import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import "./App.css";

const API_BASE = "http://localhost:8000";

function hhmmss(sec) {
  const s = Math.max(0, Math.floor(Number(sec) || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

export default function App() {
  const [mode, setMode] = useState("audio");
  const [language, setLanguage] = useState("en");
  const [modelSize, setModelSize] = useState("small");
  const [file, setFile] = useState(null);
  const [uploadPct, setUploadPct] = useState(0);
  const [jobId, setJobId] = useState("");
  const [stage, setStage] = useState("");
  const [progress, setProgress] = useState(0);
  const [ready, setReady] = useState(false);
  const [queryText, setQueryText] = useState("");
  const [searching, setSearching] = useState(false);
  const [best, setBest] = useState(null);
  const [alternates, setAlternates] = useState([]);
  const [clipUrl, setClipUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [error, setError] = useState("");

  const pollTimer = useRef(null);

  const canSearch = useMemo(
    () => !!jobId && ready && queryText.trim().length >= 2 && !searching,
    [jobId, ready, queryText, searching]
  );

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, []);

  const resetRun = () => {
    setFile(null);
    setUploadPct(0);
    setJobId("");
    setStage("");
    setProgress(0);
    setReady(false);
    setQueryText("");
    setBest(null);
    setAlternates([]);
    setClipUrl("");
    setStatusMsg("");
    setError("");
    if (pollTimer.current) clearInterval(pollTimer.current);
    pollTimer.current = null;
  };

  const apiPaths = useMemo(() => {
    if (mode === "audio") {
      return {
        upload: `${API_BASE}/audio/videos`,
        status: (id) => `${API_BASE}/audio/videos/${id}/status`,
        search: (id) => `${API_BASE}/audio/videos/${id}/search`,
      };
    }
    return {
      upload: `${API_BASE}/scene/videos`,
      status: (id) => `${API_BASE}/scene/videos/${id}/status`,
      search: (id) => `${API_BASE}/scene/videos/${id}/search`,
    };
  }, [mode]);

  const startPolling = (id) => {
    if (pollTimer.current) clearInterval(pollTimer.current);

    pollTimer.current = setInterval(async () => {
      try {
        const res = await axios.get(apiPaths.status(id));
        setStage(res.data.stage || "");
        setProgress(res.data.progress ?? 0);
        setReady(!!res.data.ready);

        if (res.data.error) {
          setError(res.data.error);
          setStatusMsg("Processing failed.");
          clearInterval(pollTimer.current);
          pollTimer.current = null;
          return;
        }

        if (res.data.ready) {
          setStatusMsg(mode === "audio" ? "Audio transcription ready!" : "Scene index ready!");
          clearInterval(pollTimer.current);
          pollTimer.current = null;
        } else {
          setStatusMsg(`Processing ${mode}...`);
        }
      } catch (e) {
        // ignore short blips
      }
    }, 2000);
  };

  const autoUpload = async (selectedFile) => {
    setError("");
    setStatusMsg("");
    setBest(null);
    setAlternates([]);
    setClipUrl("");
    setUploadPct(0);
    if (!selectedFile) return;

    setBusy(true);
    setStatusMsg("Uploading…");

    const form = new FormData();
    form.append("file", selectedFile);
    if (mode === "audio") {
      form.append("language", language);
      form.append("model_size", modelSize);
    }

    try {
      const res = await axios.post(apiPaths.upload, form, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (evt) => {
          if (!evt.total) return;
          const pct = Math.round((evt.loaded * 100) / evt.total);
          setUploadPct(pct);
        },
      });

      const id = res.data.job_id;
      setJobId(id);
      setStage("UPLOADED");
      setProgress(0);
      setReady(false);
      setStatusMsg("Upload complete. Processing started…");
      startPolling(id);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  const runSearch = async () => {
    if (!canSearch) return;
    setError("");
    setSearching(true);
    setStatusMsg(mode === "audio" ? "Searching transcript…" : "Searching scenes…");
    setBest(null);
    setAlternates([]);
    setClipUrl("");

    try {
      const body = {
        query: queryText,
        top_k: 3,
        clip_duration: 10.0,
      };

      const res = await axios.post(apiPaths.search(jobId), body, {
        headers: { "Content-Type": "application/json" },
      });

      const bestRes = res.data.best;
      const altRes = res.data.alternates || [];

      setBest(bestRes || null);
      setAlternates(altRes);

      if (!bestRes) {
        setStatusMsg("No matches found. Try a clearer query.");
        return;
      }

      const absoluteClipUrl = `${API_BASE}${bestRes.clip_url}${bestRes.clip_url.includes("?") ? "&" : "?"}t=${Date.now()}`;
      setClipUrl(absoluteClipUrl);
      setStatusMsg(`Jumped to ${bestRes.timestamp || hhmmss(bestRes.start)}.`);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "Search failed");
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="container">
      <header className="header">
        <div className="logo">
          <div className="logoIcon"></div>
          <h2>Video Finder</h2>
        </div>
        <button className="resetBtn" onClick={resetRun} disabled={busy}>Reset All</button>
      </header>

      <div className="mainGrid">
        {/* Left Column: Controls */}
        <div className="sidebar">
          <div className="card">
            <div className="sectionTitle">1. Configure Mode</div>
            <div className="field">
              <label>Search Type</label>
              <select
                value={mode}
                onChange={(e) => {
                  resetRun();
                  setMode(e.target.value);
                }}
                disabled={busy || !!jobId}
              >
                <option value="audio">Audio / Dialogue</option>
                <option value="scene">Scene / Visual</option>
              </select>
            </div>

            {mode === "audio" && (
              <div className="audioParams animate-fade">
                <div className="field">
                  <label>Language</label>
                  <select value={language} onChange={(e) => setLanguage(e.target.value)} disabled={busy || !!jobId}>
                    <option value="en">English (en)</option>
                    <option value="ta">Tamil (ta)</option>
                  </select>
                </div>
                <div className="field">
                  <label>Whisper Model</label>
                  <select value={modelSize} onChange={(e) => setModelSize(e.target.value)} disabled={busy || !!jobId}>
                    <option value="tiny">tiny (Fast)</option>
                    <option value="small">small (Balanced)</option>
                    <option value="large-v3">large-v3 (Precise)</option>
                  </select>
                </div>
              </div>
            )}
          </div>

          <div className="card">
            <div className="sectionTitle">2. Upload Video</div>
            <div className="uploadArea">
              <input
                className="fileInput"
                type="file"
                accept="video/*"
                disabled={busy || !!jobId}
                onChange={(e) => {
                  const f = e.target.files?.[0] || null;
                  if (f) {
                    resetRun();
                    setFile(f);
                    autoUpload(f);
                  }
                }}
              />
              <div className="uploadLabel">
                {file ? file.name : "Select or drag video here"}
              </div>
            </div>

            {uploadPct > 0 && uploadPct < 100 && (
              <div className="progressContainer">
                <div className="progressLabel">Uploading... {uploadPct}%</div>
                <div className="progressBar"><div className="fill" style={{ width: `${uploadPct}%` }}></div></div>
              </div>
            )}

            {jobId && (
              <div className="statusCard">
                <div className="statusHeader">
                  <span className="jobId">ID: {jobId.slice(0, 8)}...</span>
                  <span className={`badge ${ready ? 'ready' : 'busy'}`}>{ready ? "Ready" : stage}</span>
                </div>
                
                {/* Visual Animations for Processing */}
                {!ready && (
                  <div className="processingVisual">
                    {mode === "audio" ? (
                       <div className="mic-animation">
                         <div className="pulse"></div>
                         <div className="pulse"></div>
                         <div className="pulse"></div>
                         <span>Transcribing Audio...</span>
                       </div>
                    ) : (
                      <div className="frame-animation">
                        <div className="scanner"></div>
                        <div className="frames">
                          <span></span><span></span><span></span>
                        </div>
                        <span>Extracting Frames...</span>
                      </div>
                    )}
                    <div className="progressBar sm"><div className="fill" style={{ width: `${progress}%` }}></div></div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Search & Results */}
        <div className="content">
          <div className="card searchCard">
            <div className="sectionTitle">3. Search & Explore</div>
            <textarea
              className="textarea"
              placeholder={mode === "audio" ? "Enter dialogue you remember..." : "Describe what happens in the scene..."}
              value={queryText}
              onChange={(e) => setQueryText(e.target.value)}
              disabled={!jobId}
            />
            <button className="primaryBtn" onClick={runSearch} disabled={!canSearch}>
              {searching ? "Searching..." : "Search Video"}
            </button>
            {statusMsg && <div className="infoMsg">{statusMsg}</div>}
            {error && <div className="errMsg">{error}</div>}
          </div>

          {best && (
            <div className="resultContainer animate-up">
              <div className="videoWrapper">
                 <video className="mainVideo" controls src={clipUrl} autoPlay />
                 <div className="timestampOverlay">{best.timestamp || hhmmss(best.start)}</div>
              </div>
              
              <div className="resultDetails">
                <h3>Top Match</h3>
                <p>{best.text || `Visual match found with ${Math.round(best.score * 100)}% confidence`}</p>
              </div>

              {alternates.length > 0 && (
                <div className="alternates">
                  <label>Other matches:</label>
                  <div className="altGrid">
                    {alternates.map((a, i) => (
                      <div key={i} className="altCard">
                        <span className="altTime">{a.timestamp || hhmmss(a.start)}</span>
                        <span className="altScore">{Math.round(a.score * 100)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}