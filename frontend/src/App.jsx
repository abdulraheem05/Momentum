// App.jsx

import { useEffect, useState } from "react";
import axios from "axios";
import { supabase } from "./supabase";
import "./App.css";

const API = "http://localhost:8000";

export default function App() {

  const [user, setUser] = useState(null);

  const [mode, setMode] = useState("both");

  const [file, setFile] = useState(null);

  const [youtubeUrl, setYoutubeUrl] = useState("");

  const [uploading, setUploading] = useState(false);

  const [uploadProgress, setUploadProgress] = useState(0);

  const [jobId, setJobId] = useState("");

  const [jobStatus, setJobStatus] = useState("");

  const [ready, setReady] = useState(false);

  const [sceneQuery, setSceneQuery] = useState("");

  const [audioQuery, setAudioQuery] = useState("");

  const [results, setResults] = useState([]);

  const [selectedClip, setSelectedClip] = useState(null);

  const [history, setHistory] = useState([]);

  useEffect(() => {

    supabase.auth.getSession().then(({ data }) => {
      setUser(data.session?.user || null);
    });

    const {
      data: { subscription }
    } = supabase.auth.onAuthStateChange((event, session) => {
      setUser(session?.user || null);
    });

    return () => subscription.unsubscribe();

  }, []);

  const login = async () => {

    await supabase.auth.signInWithOAuth({
      provider: "google"
    });

  };

  const logout = async () => {

    await supabase.auth.signOut();

  };

  const uploadVideo = async () => {

    if (!user) return;

    setUploading(true);

    try {

      const token = (
        await supabase.auth.getSession()
      ).data.session.access_token;

      // YOUTUBE FLOW
      if (youtubeUrl.trim()) {

        const res = await axios.post(
          `${API}/jobs/create`,
          {
            source_type: "youtube",
            youtube_url: youtubeUrl,
            mode
          },
          {
            headers: {
              Authorization: `Bearer ${token}`
            }
          }
        );

        setJobId(res.data.job_id);

        pollJob(res.data.job_id);

        return;
      }

      // GET SAS TOKEN
      const sas = await axios.get(
        `${API}/upload/sas-token`,
        {
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );

      // DIRECT AZURE UPLOAD
      await axios.put(
        sas.data.upload_url,
        file,
        {
          headers: {
            "x-ms-blob-type": "BlockBlob",
            "Content-Type": file.type
          },
          onUploadProgress: (evt) => {

            const pct = Math.round(
              (evt.loaded * 100) / evt.total
            );

            setUploadProgress(pct);

          }
        }
      );

      // CREATE JOB
      const job = await axios.post(
        `${API}/jobs/create`,
        {
          source_type: "upload",
          blob_url: sas.data.blob_url,
          mode
        },
        {
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );

      setJobId(job.data.job_id);

      pollJob(job.data.job_id);

    } catch (err) {

      console.log(err);

    } finally {

      setUploading(false);

    }
  };

  const pollJob = async (id) => {

    const token = (
      await supabase.auth.getSession()
    ).data.session.access_token;

    const interval = setInterval(async () => {

      const res = await axios.get(
        `${API}/jobs/${id}`,
        {
          headers: {
            Authorization: `Bearer ${token}`
          }
        }
      );

      setJobStatus(res.data.status);

      if (res.data.status === "READY") {

        setReady(true);

        clearInterval(interval);

      }

    }, 3000);

  };

  const searchScene = async () => {

    const token = (
      await supabase.auth.getSession()
    ).data.session.access_token;

    const res = await axios.post(
      `${API}/search/scene`,
      {
        job_id: jobId,
        query: sceneQuery
      },
      {
        headers: {
          Authorization: `Bearer ${token}`
        }
      }
    );

    setResults(res.data);

  };

  const searchAudio = async () => {

    const token = (
      await supabase.auth.getSession()
    ).data.session.access_token;

    const res = await axios.post(
      `${API}/search/audio`,
      {
        job_id: jobId,
        query: audioQuery
      },
      {
        headers: {
          Authorization: `Bearer ${token}`
        }
      }
    );

    setResults(res.data);

  };

  return (

    <div className="app">

      <div className="navbar">

        <h1>Momentum</h1>

        {
          user && (
            <div className="navRight">

              <span>0/5 Uses</span>

              <button onClick={logout}>
                Logout
              </button>

            </div>
          )
        }

      </div>

      {
        !user && (

          <div className="authBox">

            <h1>AI Video Search</h1>

            <button onClick={login}>
              Continue with Google
            </button>

          </div>

        )
      }

      {
        user && (

          <>

            <div className="uploadBox">

              <h2>Upload Once, Search Either</h2>

              <input
                type="file"
                accept="video/*"
                onChange={(e) => setFile(e.target.files[0])}
              />

              <div className="or">
                OR
              </div>

              <input
                type="text"
                placeholder="Paste YouTube URL"
                value={youtubeUrl}
                onChange={(e) => setYoutubeUrl(e.target.value)}
              />

              <div className="modeButtons">

                <button
                  className={mode === "audio" ? "active" : ""}
                  onClick={() => setMode("audio")}
                >
                  Audio
                </button>

                <button
                  className={mode === "video" ? "active" : ""}
                  onClick={() => setMode("video")}
                >
                  Video
                </button>

                <button
                  className={mode === "both" ? "active" : ""}
                  onClick={() => setMode("both")}
                >
                  Both
                </button>

              </div>

              <button
                className="uploadBtn"
                onClick={uploadVideo}
              >
                {
                  uploading
                  ? `Uploading ${uploadProgress}%`
                  : "Start Processing"
                }
              </button>

              {
                jobStatus && (
                  <div className="status">
                    {jobStatus}
                  </div>
                )
              }

            </div>

            {
              ready && (

                <div className="searchSplit">

                  <div className="searchPanel">

                    <h2>Explain a Scene</h2>

                    <textarea
                      value={sceneQuery}
                      onChange={(e) => {
                        setSceneQuery(e.target.value);
                        setAudioQuery("");
                      }}
                    />

                    <button
                      disabled={audioQuery.length > 0}
                      onClick={searchScene}
                    >
                      Search Video
                    </button>

                  </div>

                  <div className="divider">
                    OR
                  </div>

                  <div className="searchPanel">

                    <h2>Dialogue Search</h2>

                    <textarea
                      value={audioQuery}
                      onChange={(e) => {
                        setAudioQuery(e.target.value);
                        setSceneQuery("");
                      }}
                    />

                    <button
                      disabled={sceneQuery.length > 0}
                      onClick={searchAudio}
                    >
                      Search Audio
                    </button>

                  </div>

                </div>

              )
            }

            {
              results.length > 0 && (

                <div className="resultsSection">

                  <h2>Results</h2>

                  <div className="resultsGrid">

                    {
                      results.map((item, idx) => (

                        <div
                          key={idx}
                          className="clipCard"
                          onClick={() => setSelectedClip(item)}
                        >

                          <video
                            src={item.clip_url}
                            muted
                            autoPlay
                            loop
                            playsInline
                          />

                          <div className="clipInfo">

                            <span>
                              {Math.round(item.score * 100)}%
                            </span>

                            <span>
                              {Math.floor(item.timestamp)}s
                            </span>

                          </div>

                          <a
                            href={item.clip_url}
                            download
                            onClick={(e) => e.stopPropagation()}
                          >
                            Download
                          </a>

                        </div>

                      ))
                    }

                  </div>

                </div>

              )
            }

            {
              selectedClip && (

                <div className="playerSection">

                  <video
                    src={selectedClip.clip_url}
                    controls
                    autoPlay
                  />

                </div>

              )
            }

          </>

        )
      }

    </div>

  );

}