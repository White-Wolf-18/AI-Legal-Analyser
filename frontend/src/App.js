import React, { useState } from "react";
import { login, uploadFile, analyzeText, analyzeStored } from "./api";
import "./App.css"; // ✅ Import your new CSS

function App() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState(null);
  const [file, setFile] = useState(null);
  const [storedFilename, setStoredFilename] = useState(null);
  const [text, setText] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleLogin(e) {
    e.preventDefault();
    setError(null);
    try {
      const res = await login(email, password);
      setToken(res.data.access_token);
    } catch (err) {
      setError(err?.response?.data?.detail || "Login failed");
    }
  }

  async function handleUpload(e) {
    e.preventDefault();
    if (!file) return setError("Select a file first");
    setLoading(true);
    try {
      const res = await uploadFile(file, token);
      setStoredFilename(res.data.stored_filename);
    } catch (err) {
      setError(err?.response?.data?.detail || "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleAnalyzeText(e) {
    e.preventDefault();
    if (!text) return setError("Enter text to analyze");
    setLoading(true);
    try {
      const res = await analyzeText(text, token);
      setResults(res.data);
    } catch (err) {
      setError(err?.response?.data?.detail || "Analyze failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleAnalyzeStored(e) {
    e.preventDefault();
    if (!storedFilename) return setError("No uploaded file stored");
    setLoading(true);
    try {
      const res = await analyzeStored(storedFilename, token);
      setResults(res.data);
    } catch (err) {
      setError(err?.response?.data?.detail || "Analyze failed");
    } finally {
      setLoading(false);
    }
  }

  // -------------------------------
  // LOGIN SCREEN
  // -------------------------------
  if (!token) {
    return (
      <div className="container-custom">
        <h2>🔐 Legal AI Analyzer — Login</h2>
        <form onSubmit={handleLogin} className="section-box">
          <div className="mb-3">
            <label>Email</label>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Enter your email"
            />
          </div>
          <div className="mb-3">
            <label>Password</label>
            <input
              type="password"
              value={password}
              placeholder="Enter password"
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button className="btn-primary" type="submit">
            Login
          </button>
          {error && <div className="alert alert-danger">{error}</div>}
        </form>
      </div>
    );
  }

  // -------------------------------
  // MAIN APP
  // -------------------------------
  return (
    <div className="container-custom">
      <h2>⚖️ Legal AI Document Analyzer</h2>
      <p>
        Logged in as: <b>{email}</b>
      </p>

      {/* Upload Section */}
      <section className="section-box">
        <h4>📂 Upload Document</h4>
        <input type="file" onChange={(e) => setFile(e.target.files[0])} />
        <button
          className="btn-outline"
          onClick={handleUpload}
          disabled={loading || !file}
        >
          Upload & Encrypt
        </button>
        {storedFilename && (
          <div className="alert alert-info">
            Stored as: <code>{storedFilename}</code>
          </div>
        )}
      </section>

      {/* Analyze Section */}
      <section className="section-box">
        <h4>🧠 Analyze Uploaded File</h4>
        <button
          className="btn-primary"
          onClick={handleAnalyzeStored}
          disabled={loading || !storedFilename}
        >
          Analyze Uploaded File
        </button>
      </section>

      {/* Text Analysis */}
      <section className="section-box">
        <h4>✍️ Analyze Pasted Text</h4>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={8}
          placeholder="Paste your contract or legal text here..."
        />
        <button
          className="btn-primary"
          onClick={handleAnalyzeText}
          disabled={loading || !text}
        >
          Analyze Text
        </button>
      </section>

      {/* Status */}
      {loading && <div className="alert alert-info">⏳ Working…</div>}
      {error && <div className="alert alert-danger">{error}</div>}

      {/* Results */}
      {results && (
        <section className="result-card">
          <h3>📊 Analysis Results</h3>

          <h4>📝 Summary</h4>
          <p style={{ whiteSpace: "pre-wrap" }}>{results.summary}</p>

          <h4>⚖️ Overall Risk</h4>
          <p>
            <b>Level:</b>{" "}
            <span
              className={
                results.overall_risk_level === "High"
                  ? "risk-high"
                  : results.overall_risk_level === "Medium"
                  ? "risk-medium"
                  : "risk-low"
              }
            >
              {results.overall_risk_level}
            </span>{" "}
            ({Math.round(results.overall_risk_score * 100)}%)
          </p>

          <div className="progress">
            <div
              className={`progress-bar ${
                results.overall_risk_level.toLowerCase()
              }`}
              style={{ width: `${results.overall_risk_score * 100}%` }}
            ></div>
          </div>

          {results.detected_risks?.length > 0 && (
            <>
              <h4>🚨 Detected Risk Indicators</h4>
              <ul>
                {results.detected_risks.map((risk, i) => (
                  <li key={i}>{risk}</li>
                ))}
              </ul>
            </>
          )}

          {results.recommendations?.length > 0 && (
            <>
              <h4>🛠️ Recommendations</h4>
              <ul>
                {results.recommendations.map((rec, i) => (
                  <li key={i}>{rec}</li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}
    </div>
  );
}

export default App;
