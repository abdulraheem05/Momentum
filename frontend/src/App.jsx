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
  // Mode: "audio" or "scene"
  const [mode, setMode] = useState("audio");

  // Audio settings (only relevant in audio mode)
  const [language, setLanguage] = useState("en");
  const [modelSize, setModelSize] = useState("small");

  // Upload state
  const [file, setFile] = useState(null);
  const [uploadPct, setUploadPct] = useState(0);
  const [jobId, setJobId] = useState("");

  // Pipeline status
  const [stage, setStage] = useState("");
  const [progress, setProgress] = useState(0);
  const [ready, setReady] = useState(false);

  // Search input
  const [queryText, setQueryText] = useState("");

  // Search result
  const [searching, setSearching] = useState(false);
  const [best, setBest] = useState(null);
  const [alternates, setAlternates] = useState([]);

  // Clip
  const [clipUrl, setClipUrl] = useState("");

  // UX
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [error, setError] = useState("");

  const pollTimer = useRef(null);

  const canSearch = useMemo(
    () => !!jobId && ready && queryText.trim().length >= 2 && !searching,
    [jobId, ready, queryText, searching]
  );

  // Cleanup poller on unmount
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
          setStatusMsg(mode === "audio" ? "Audio transcription ready. You can search now." : "Scene index ready. You can search now.");
          clearInterval(pollTimer.current);
          pollTimer.current = null;
        } else {
          setStatusMsg(`Processing (${mode}): ${res.data.stage} (${res.data.progress}%)`);
        }
      } catch (e) {
        // ignore short blips (server restart etc.)
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

    // Only audio upload needs language/model
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
        top_k: mode === "audio" ? 3 : 3,
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
        setStatusMsg("No matches found. Try a clearer/shorter query.");
        return;
      }

      // clip_url already includes /audio/... or /scene/... from backend
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
      <h2 className="title">Video Finder</h2>

      <div className="card">
        {/* MODE */}
        <div className="section">
          <div className="sectionTitle">Choose Search Type</div>

          <div className="row">
            <div className="field">
              <label>Mode</label>
              <select
                value={mode}
                onChange={(e) => {
                  // switching mode resets everything (separate uploads/status)
                  resetRun();
                  setMode(e.target.value);
                }}
                disabled={busy || !!jobId}
              >
                <option value="audio">Audio search (dialogue)</option>
                <option value="scene">Scene search (description)</option>
              </select>
            </div>

            <button className="secondaryBtn" onClick={resetRun} disabled={busy}>
              Reset
            </button>
          </div>

          <p className="hint">
            Audio mode runs transcription (slower). Scene mode builds frame index only (faster).
          </p>
        </div>

        {/* AUDIO SETTINGS (only show for audio mode) */}
        {mode === "audio" && (
          <div className="section">
            <div className="sectionTitle">Audio Settings (before upload)</div>

            <div className="row">
              <div className="field">
                <label>Language</label>
                <select value={language} onChange={(e) => setLanguage(e.target.value)} disabled={busy || !!jobId}>
                  <option value="en">English (en)</option>
                  <option value="ta">Tamil (ta)</option>
                </select>
              </div>

              <div className="field">
                <label>Model</label>
                <select value={modelSize} onChange={(e) => setModelSize(e.target.value)} disabled={busy || !!jobId}>
                  <option value="tiny">tiny (fastest)</option>
                  <option value="base">base</option>
                  <option value="small">small</option>
                  <option value="medium">medium</option>
                  <option value="large-v3">large-v3 (slowest)</option>
                </select>
              </div>
            </div>

            <p className="hint">
              Tip: Use <b>tiny</b> while testing. Switch to <b>small</b> for better accuracy.
            </p>
          </div>
        )}

        {/* UPLOAD */}
        <div className="section">
          <div className="sectionTitle">Upload (auto-start)</div>

          <input
            className="fileInput"
            type="file"
            accept="video/*"
            disabled={busy || !!jobId}
            onChange={(e) => {
              const f = e.target.files?.[0] || null;
              setFile(f);
              if (f) {
                // new run per upload
                resetRun();
                setFile(f);
                autoUpload(f);
              }
            }}
          />

          <div className="progressWrap">
            <div className="progressText">Upload: {uploadPct}%</div>
            <div className="progressBarBg">
              <div className="progressBarFill" style={{ width: `${uploadPct}%` }} />
            </div>
          </div>

          {jobId && (
            <div className="metaBox">
              <div><b>Job ID:</b> {jobId}</div>
              <div><b>Mode:</b> {mode}</div>
              <div><b>Stage:</b> {stage || "-"}</div>
              <div><b>Progress:</b> {progress}%</div>
            </div>
          )}
        </div>

        {/* QUERY INPUT */}
        <div className="section">
          <div className="sectionTitle">{mode === "audio" ? "Dialogue you remember" : "Scene description"}</div>

          <textarea
            className="textarea"
            placeholder={mode === "audio" ? "Type the dialogue you remember…" : "Describe the scene… (e.g., 'a man speaking on stage')"}
            value={queryText}
            onChange={(e) => setQueryText(e.target.value)}
            disabled={!jobId}
          />

          <button className="primaryBtn" onClick={runSearch} disabled={!canSearch}>
            {searching ? "Searching…" : ready ? "Search" : "Search (wait until ready)"}
          </button>

          {!ready && jobId && (
            <div className="smallNote">
              Search will unlock after processing finishes.
            </div>
          )}
        </div>

        {/* RESULT */}
        <div className="section">
          <div className="sectionTitle">Result</div>

          {best ? (
            <>
              <div className="resultCard">
                <div className="pill">{best.timestamp || hhmmss(best.start)}</div>

                {/* Audio returns text; Scene may not return text */}
                {best.text ? (
                  <div className="resultText">{best.text}</div>
                ) : (
                  <div className="resultText mutedText">
                    Scene match found (score: {best.score})
                  </div>
                )}
              </div>

              {clipUrl && (
                <div className="videoBox">
                  <video className="video" controls src={clipUrl} />
                </div>
              )}

              {alternates.length > 0 && (
                <div className="alts">
                  <div className="altsTitle">Alternates</div>
                  {alternates.map((a, idx) => (
                    <div key={idx} className="altItem">
                      <span className="pill muted">{a.timestamp || hhmmss(a.start)}</span>
                      <span className="altText">
                        {a.text ? a.text : `Scene match (score: ${a.score})`}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="empty">No result yet. Upload → wait → search.</div>
          )}
        </div>

        {/* STATUS + ERROR */}
        {statusMsg && <div className="status">{statusMsg}</div>}
        {error && <div className="error">Error: {error}</div>}
      </div>
    </div>
  );
}
