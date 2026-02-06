import { useState } from "react";
import axios from "axios";
import "./App.css"; // Don't forget to import the CSS!

const API_BASE = "http://localhost:8000";

export default function App() {
  const [file, setFile] = useState(null);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const upload = async () => {
    setError("");
    setResult(null);
    setProgress(0);

    if (!file) {
      setError("Please select a video file first.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await axios.post(`${API_BASE}/videos/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (evt) => {
          if (!evt.total) return;
          const pct = Math.round((evt.loaded * 100) / evt.total);
          setProgress(pct);
        },
      });

      setResult(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "Upload failed");
    }
  };

  return (
    <div className="container">
      <h2>Video Moment Finder</h2>

      <div className="upload-card">
        <input
          type="file"
          accept="video/*"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
        />

        <div className="input-group">
          <button className="upload-button" onClick={upload}>
            Upload
          </button>
        </div>

        <div className="progress-container">
          <div>Upload progress: {progress}%</div>
          <div className="progress-bar-bg">
            <div 
              className="progress-bar-fill" 
              style={{ width: `${progress}%` }} 
            />
          </div>
        </div>

        {error && (
          <p className="error-message">
            Error: {error}
          </p>
        )}

        {result && (
          <div className="result-box">
            <pre>
              {JSON.stringify(result, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}