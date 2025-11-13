import React, { useState } from "react";
import { login, uploadFile, analyzeText, analyzeStored } from "./api";
import "./App.css";


function highlightViolations(text, violations = []) {
  if (!violations || violations.length === 0) return text;

  let highlighted = text;
  violations.forEach(v => {
    if (!v.match_text) return;

    const safe = v.match_text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(safe, "gi");

    highlighted = highlighted.replace(
      regex,
      match => `<mark class="highlight">${match}</mark>`
    );
  });

  return <span dangerouslySetInnerHTML={{ __html: highlighted }} />;
}

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

  async function handleAnalyzeStored(e) {
  e.preventDefault();
  if (!storedFilename) return setError("No uploaded file stored");

  // Clear previous results before analyzing new file
  setResults(null);
  await new Promise((resolve) => setTimeout(resolve, 150)); // brief UX delay
  setResults(null);
  setError(null);
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

async function handleAnalyzeText(e) {
  e.preventDefault();
  if (!text) return setError("Enter text to analyze");

  // Clear previous results before analyzing new text
  setResults(null);
  setError(null);
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


  // -------------------------------
// LOGIN SCREEN
// -------------------------------
if (!token) {
  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <h1>⚖️ LegalAI Assistant</h1>
          <p>Sign in to analyze your contracts using Indian Legal standards.</p>
        </div>

        <form onSubmit={handleLogin}>
          <div className="form-group">
            <label>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Enter your email"
              required
            />
          </div>

          <div className="form-group">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              required
            />
          </div>

          <button type="submit" className="btn-login" disabled={loading}>
            {loading ? "Logging in..." : "Login"}
          </button>

          {error && <div className="alert-login">{error}</div>}
        </form>

        <div className="login-footer">
          <p>🔒 Your data remains private and secure.</p>
        </div>
      </div>
    </div>
  );
}


  // -------------------------------
  // MAIN APP
  // -------------------------------
  return (
    <div className="container-custom">
      <header className="app-header">
  <div className="header-left">
    <div className="title-block">
      <h2>⚖️ LegalAI Assistant</h2>
      <p className="subtitle">
        Ready to analyze your contracts using Indian Legal standards.
      </p>
    </div>
  </div>
  <div className="user-info">
    <b>{email}</b>
  </div>
</header>


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

      {loading && <div className="alert alert-info">⏳ Analyzing your document…</div>}
      {error && <div className="alert alert-danger">{error}</div>}

      {/* === RESULTS === */}
      {results && (
        <section className="result-card">
          {/* RISK OVERVIEW */}
          <div className="risk-panel">
            <div className="risk-header">
              <h3>
                {results.overall_risk_level === "High"
                  ? "🚨 High Risk"
                  : results.overall_risk_level === "Medium"
                  ? "⚠️ Medium Risk"
                  : "✅ Low Risk"}
              </h3>
              <span className="risk-score">
                {Math.round(results.overall_risk_score * 100)}/100
              </span>
            </div>
            <div className="risk-bar">
              <div
                className={`risk-fill ${results.overall_risk_level.toLowerCase()}`}
                style={{ width: `${results.overall_risk_score * 100}%` }}
              ></div>
            </div>
            <p className="risk-caption">
              {results.overall_risk_level === "High"
                ? "Several problematic clauses detected. Strongly consider changes."
                : results.overall_risk_level === "Medium"
                ? "Some clauses may pose moderate risk."
                : "Minimal legal risk detected. Document appears compliant."}
            </p>
          </div>

          {/* Summary */}
          <div className="result-block">
            <h4>📝 Summary</h4>
            <p style={{ whiteSpace: "pre-wrap" }}>{results.summary}</p>
          </div>

          {/* ⚠️ Top Risky Clauses */}
{results.risky_clauses && results.risky_clauses.length > 0 && (
  <div className="result-block">
    <h4>⚠️ Top Risky Clauses</h4>

    {results.risky_clauses.map((c, i) => {
      const riskPercent = Math.round((c.risk_score || 0) * 100);

      return (
        <div key={i} className="clause-card">
          
          {/* Clause heading */}
          <div className="clause-header">
            <strong>{i + 1}. {c.clause_type.toUpperCase()}</strong>
            <span className={`risk-badge ${c.risk_level.toLowerCase()}`}>
              {c.risk_level.toUpperCase()} — {riskPercent}%
            </span>
          </div>

          {/* === ORIGINAL CLAUSE WITH HIGHLIGHTING === */}
          <h5 className="subheading">Original Clause</h5>
          <p className="original-clause">
            {highlightViolations(c.clause_text, c.violations)}
          </p>

          {/* === IMPROVED VERSION === */}
          <h5 className="subheading improved-title">✨ Improved Version (Legally Safer)</h5>

          {c.improved_clause ? (
            <p className="improved-clause">{c.improved_clause}</p>
          ) : (
            <div className="alert alert-warning">
              ⚠️ Auto-rewrite failed — showing manual suggestions instead.
            </div>
          )}

          {/* === LEGAL REFERENCES === */}
          {c.legal_references?.length > 0 && (
            <ul className="law-list">
              {c.legal_references.map((law, j) => (
                <li key={j}>
                  <b>{law.statute}</b> — {law.section}
                </li>
              ))}
            </ul>
          )}
        </div>
      );
    })}
  </div>
)}



          {/* Recommendations */}
          {results.recommendations?.length > 0 && (
            <div className="result-block">
              <h4>💡 Recommendations</h4>
              <ul>
                {results.recommendations.map((rec, i) => (
                  <li key={i}>{rec}</li>
                ))}
              </ul>
            </div>
          )}
          {/* 📘 Relevant Indian Laws */}
{results.relevant_laws && results.relevant_laws.length > 0 && (
  <div className="result-block">
    <h4>📘 Relevant Indian Laws</h4>
    <ul>
      {results.relevant_laws.map((law, i) => (
        <li key={i}>{law}</li>
      ))}
    </ul>
  </div>
)}

        </section>
      )}
    </div>
  );
}

export default App;
