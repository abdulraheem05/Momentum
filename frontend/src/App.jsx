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
  // Pre-upload settings
  const [language, setLanguage] = useState("en");
  const [modelSize, setModelSize] = useState("small");

  // Upload state
  const [file, setFile] = useState(null);
  const [uploadPct, setUploadPct] = useState(0);
  const [videoId, setVideoId] = useState("");

  // Pipeline status
  const [stage, setStage] = useState("");
  const [progress, setProgress] = useState(0);
  const [readyToSearch, setReadyToSearch] = useState(false);

  // Search
  const [dialogue, setDialogue] = useState("");
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

  const canUpload = useMemo(() => !!file && !busy, [file, busy]);
  const canSearch = useMemo(
    () => !!videoId && readyToSearch && dialogue.trim().length >= 2 && !searching,
    [videoId, readyToSearch, dialogue, searching]
  );

  // Cleanup poller on unmount
  useEffect(() => {
    return () => {
      if (pollTimer.current) clearInterval(pollTimer.current);
    };
  }, []);

  const resetRun = () => {
    setUploadPct(0);
    setVideoId("");
    setStage("");
    setProgress(0);
    setReadyToSearch(false);
    setBest(null);
    setAlternates([]);
    setClipUrl("");
    setStatusMsg("");
    setError("");
    if (pollTimer.current) clearInterval(pollTimer.current);
    pollTimer.current = null;
  };

  const startPolling = (id) => {
    if (pollTimer.current) clearInterval(pollTimer.current);

    pollTimer.current = setInterval(async () => {
      try {
        const res = await axios.get(`${API_BASE}/videos/${id}/status`);
        setStage(res.data.stage || "");
        setProgress(res.data.progress ?? 0);
        setReadyToSearch(!!res.data.ready_to_search || !!res.data.ready_to_search === true ? true : !!res.data.ready_to_search);

        // Your backend uses "ready_to_search" key (per your code).
        // If you change backend to "ready_for_search", update here.

        if (res.data.error) {
          setError(res.data.error);
          setStatusMsg("Processing failed.");
          clearInterval(pollTimer.current);
          pollTimer.current = null;
          return;
        }

        if (res.data.stage === "READY") {
          setStatusMsg("Transcription ready. You can search now.");
          clearInterval(pollTimer.current);
          pollTimer.current = null;
        } else {
          setStatusMsg(`Processing: ${res.data.stage} (${res.data.progress}%)`);
        }
      } catch (e) {
        // If the server is restarting, this can fail briefly
        // Don’t spam errors; show minimal message.
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
    form.append("language", language);
    form.append("model_size", modelSize);

    try {
      const res = await axios.post(`${API_BASE}/videos`, form, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (evt) => {
          if (!evt.total) return;
          const pct = Math.round((evt.loaded * 100) / evt.total);
          setUploadPct(pct);
        },
      });

      const id = res.data.video_id;
      setVideoId(id);
      setStage("UPLOADED");
      setProgress(0);
      setReadyToSearch(false);
      setStatusMsg("Upload complete. Processing started…");

      // Start polling immediately
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
    setStatusMsg("Searching transcript…");
    setBest(null);
    setAlternates([]);
    setClipUrl("");

    try {
      const body = {
        query: dialogue,
        top_k: 3,
        clip_duration: 10.0,
      };

      const res = await axios.post(`${API_BASE}/videos/${videoId}/search`, body, {
        headers: { "Content-Type": "application/json" },
      });

      const bestRes = res.data.best;
      const altRes = res.data.alternates || [];

      setBest(bestRes || null);
      setAlternates(altRes);

      if (!bestRes) {
        setStatusMsg("No matches found. Try a shorter/clearer phrase.");
        return;
      }

      // Build absolute URL for video tag
      const absoluteClipUrl = `${API_BASE}${bestRes.clip_url}&t=${Date.now()}`;
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
      <h2 className="title">Video Scene Finder</h2>

      <div className="card">
        {/* SETTINGS */}
        <div className="section">
          <div className="sectionTitle">Language (choose before upload)</div>

          <div className="row">
            <div className="field">
              <label>Language</label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                disabled={busy || !!videoId} // lock after upload begins
              >
                <option value="en">English (en)</option>
                <option value="ta">Tamil (ta)</option>
              </select>
            </div>

            <div className="field">
              <label>Model</label>
              <select
                value={modelSize}
                onChange={(e) => setModelSize(e.target.value)}
                disabled={busy || !!videoId}
              >
                <option value="tiny">tiny (fastest)</option>
                <option value="base">base</option>
                <option value="small">small</option>
                <option value="medium">medium</option>
                <option value="large-v3">large-v3 (slowest)</option>
              </select>
            </div>

            <button className="secondaryBtn" onClick={resetRun} disabled={busy}>
              Reset
            </button>
          </div>

          <p className="hint">
            Tip: use <b>tiny</b> for speed while testing. Switch to <b>small</b> for better accuracy.
          </p>
        </div>

        {/* UPLOAD */}
        <div className="section">
          <div className="sectionTitle">Upload (auto-start)</div>

          <input
            className="fileInput"
            type="file"
            accept="video/*"
            disabled={busy || !!videoId}
            onChange={(e) => {
              const f = e.target.files?.[0] || null;
              setFile(f);
              if (f) {
                // start a fresh run and auto-upload
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

          {videoId && (
            <div className="metaBox">
              <div><b>Video ID:</b> {videoId}</div>
              <div><b>Stage:</b> {stage || "-"}</div>
              <div><b>Progress:</b> {progress}%</div>
            </div>
          )}
        </div>

        {/* DIALOGUE INPUT */}
        <div className="section">
          <div className="sectionTitle">Dialogue you remember</div>

          <textarea
            className="textarea"
            placeholder="Type the dialogue you remember…"
            value={dialogue}
            onChange={(e) => setDialogue(e.target.value)}
            disabled={!videoId} // allow typing after upload starts
          />

          <button className="primaryBtn" onClick={runSearch} disabled={!canSearch}>
            {searching ? "Searching…" : readyToSearch ? "Search" : "Search (wait for transcription)"}
          </button>

          {!readyToSearch && videoId && (
            <div className="smallNote">
              Search will unlock after transcription finishes.
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
                <div className="resultText">{best.text}</div>
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
                      <span className="altText">{a.text}</span>
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
