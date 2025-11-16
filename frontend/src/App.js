import React, { useState } from "react";
import { login, uploadFile, analyzeText, analyzeStored } from "./api";
import "./App.css";
import CorrectedDocument from "./components/CorrectedDocument";

const lawExplanations = {
  "Indian Contract Act, 1872 – Section 27": {
    title: "Section 27 — Restraint of Trade",
    description:
      "This section declares agreements that restrain a person from practicing a lawful profession, trade, or business as void. Non-compete clauses beyond reasonable limits are unenforceable in India.",
  },

  "Indian Contract Act, 1872 – Section 73": {
    title: "Section 73 — Compensation for Breach",
    description:
      "This provision regulates how damages are awarded for breach of contract. Only actual losses that naturally arise from the breach can be claimed.",
  },

  "Indian Contract Act, 1872 – Section 74": {
    title: "Section 74 — Penalty & Liquidated Damages",
    description:
      "This section restricts excessive penalties in contracts. Courts award reasonable compensation, not automatically the penalty amount mentioned.",
  },

  "SARFAESI Act, 2002 – Section 13": {
    title: "Section 13 — Enforcement of Security Interest",
    description:
      "Allows secured creditors to enforce security interests without court intervention when a borrower defaults.",
  },
  "Indian Contract Act, 1872": {
    title: "Indian Contract Act, 1872",
    description:
      "The foundational law governing all contracts in India. It defines what constitutes a valid contract, outlines when agreements become void or voidable, and covers principles such as free consent, lawful consideration, breach consequences, and agreements in restraint of trade.",
  },

  "Transfer of Property Act, 1882": {
    title: "Transfer of Property Act, 1882",
    description:
      "This Act governs the transfer of property between living persons, covering key concepts such as sale, lease, gift, mortgage, and actionable claims. It defines the rights and liabilities of parties involved in property transactions.",
  },

  "Registration Act, 1908": {
    title: "Registration Act, 1908",
    description:
      "This Act makes the registration of certain documents compulsory—especially documents related to immovable property valued above ₹100. Registration ensures legal validity and establishes clear title and ownership through recorded documents such as sale deeds.",
  },

  "Indian Easements Act, 1882": {
    title: "Indian Easements Act, 1882",
    description:
      "This law defines easements — legal rights enjoyed by a person over another's land (e.g., right of way, right to light and air). It governs how easements are created, transferred, and extinguished.",
  },

  // CIVIL CASES

  "Code of Civil Procedure, 1908": {
    title: "Code of Civil Procedure (CPC), 1908",
    description:
      "This Act lays down the complete procedural framework for civil courts in India. It governs how civil suits are filed, the stages of a trial, execution of decrees, appeals, limitations, and jurisdiction. CPC ensures systematic, fair, and uniform civil proceedings.",
  },

  "Indian Evidence Act, 1872": {
    title: "Indian Evidence Act, 1872",
    description:
      "This Act governs the admissibility, relevancy, and evaluation of evidence in court. It defines what facts can be proved, the types of evidence allowed, burden of proof, and the standards required to establish truth in judicial proceedings.",
  },
   
  "Indian Evidence Act, 1872 – General": {
  title: "Indian Evidence Act, 1872 — General Principles",
  description:
    "The Indian Evidence Act, 1872 establishes the rules governing what facts, documents, and statements are admissible in judicial proceedings. It defines key concepts such as relevancy of facts, burden of proof, presumptions, oral and documentary evidence, expert testimony, and the standards required for proving or disproving facts in court. The Act ensures that evidence presented is reliable, legally obtained, and capable of establishing truth in both civil and criminal cases."
  },

  // LAND & PROPERTY

  "Constitution of India – Article 300A": {
    title: "Article 300A — Right to Property",
    description:
      "Provides citizens with a constitutional right to property (no longer a fundamental right). It protects individuals from being deprived of property except by authority of law, ensuring fair and lawful acquisition by the state.",
  },

  "Hindu Succession Act, 1956": {
    title: "Hindu Succession Act, 1956",
    description:
      "Governs inheritance and succession of property for Hindus, Buddhists, Jains, and Sikhs. It outlines rules for intestate succession, coparcenary rights, and equal property rights for daughters (post-2005 amendment).",
  },

  "Indian Succession Act, 1925": {
    title: "Indian Succession Act, 1925",
    description:
      "This Act governs inheritance for communities other than Hindus (unless specifically excluded). It provides rules for both testamentary succession (via a will) and intestate succession when no will exists.",
  },
};


function triggerDownloadCorrectedDoc(text, token, docName = "Corrected_Document") {
  const filename = `${docName}.docx`;

  fetch("http://localhost:8000/download-docx", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ corrected_text: text, filename }),
  })
    .then((res) => res.blob())
    .then((blob) => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      window.URL.revokeObjectURL(url);
    });
}

function highlightViolations(text, violations = []) {
  if (!violations || violations.length === 0) return text;

  let highlighted = text;
  violations.forEach((v) => {
    if (!v.match_text) return;

    const safe = v.match_text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const regex = new RegExp(safe, "gi");

    highlighted = highlighted.replace(
      regex,
      (match) => `<mark class="highlight">${match}</mark>`
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
  const [docName, setDocName] = useState("Corrected_Document");
  const [selectedLaw, setSelectedLaw] = useState(null);


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

  // LOGIN SCREEN
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

  // MAIN APP
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

      {/* RESULTS */}
      {results && (
        <section className="result-card">
          {/* RISK OVERVIEW */}
          <div className={`risk-panel theme-${results.overall_risk_level.toLowerCase()}`}>
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

          {/* TOP RISKY CLAUSES */}
          {results.risky_clauses?.length > 0 && (
            <div className="result-block">
              <h4>⚠️ Top Risky Clauses</h4>

              {results.risky_clauses.map((c, i) => {
                const riskPercent = Math.round((c.risk_score || 0) * 100);

                return (
                  <div key={i} className="clause-card">
                    <div className="clause-header">
                      <strong>
                        {i + 1}. {c.clause_type.toUpperCase()}
                      </strong>
                      <span className={`risk-badge ${c.risk_level.toLowerCase()}`}>
                        {c.risk_level.toUpperCase()} — {riskPercent}%
                      </span>
                    </div>

                    {/* Original Clause */}
                    <h5 className="subheading">Original Clause</h5>
                    <p className="original-clause">
                      {highlightViolations(c.clause_text, c.violations)}
                    </p>

                    {/* Improved Version */}
                    <h5 className="subheading improved-title">
                      ✨ Improved Legally Safer Version
                    </h5>

                    {c.improved_clause ? (
                      <p className="improved-clause">{c.improved_clause}</p>
                    ) : (
                      <div className="alert alert-warning">
                        ⚠️ Auto-rewrite failed — showing manual suggestions instead.
                      </div>
                    )}

                    {/* Legal References */}
                    {/* {c.legal_references?.length > 0 && (
                      <ul className="law-list">
                        {c.legal_references.map((law, j) => (
                          <li key={j}>
                            <b>{law.statute}</b> — {law.section}
                          </li>
                        ))}
                      </ul>
                    )} */}
                  </div>
                );
              })}
            </div>
          )}

          {/* Recommendations — ONLY shown when no risky clauses exist */}
{(!results.risky_clauses || results.risky_clauses.length === 0) &&
  results.recommendations?.length > 0 && (
    <div className="result-block">
      <h4>🛡️ Legal Safety Check</h4>
      <ul>
        {results.recommendations.map((rec, i) => (
          <li key={i}>{rec}</li>
        ))}
      </ul>
    </div>
)}


          {/* Relevant Laws */}
          {results.relevant_laws?.length > 0 && (
  <div className="result-block">
    <h4>📘 Relevant Indian Laws</h4>

    <ul>
      {results.relevant_laws.map((law, i) => (
        <li
          key={i}
          className="law-clickable"
          onClick={() => setSelectedLaw(lawExplanations[law] || {
            title: law,
            description: "No description available."
          })}
        >
          {law}
        </li>
      ))}
    </ul>
  </div>
)}

        </section>
      )}

      {/* Corrected Document Section */}
      {results?.has_corrections && results.corrected_document && (
  <CorrectedDocument
    originalClauses={results.original_clauses || []}
    correctedDocument={results.corrected_document}
  />
)}


      {/* Download Button */}
      {results?.has_corrections && results.corrected_document && (
  <div className="text-center mt-6">

    {/* Filename Input */}
    <input
      type="text"
      value={docName}
      onChange={(e) => setDocName(e.target.value)}
      className="filename-input"
      placeholder="Enter filename (without .docx)"
      style={{
        padding: "10px 14px",
        borderRadius: "8px",
        border: "1px solid #ccc",
        marginBottom: "12px",
        width: "260px"
      }}
    />

    <br/>

    {/* Download Button */}
    <button
      onClick={() =>
        triggerDownloadCorrectedDoc(results.corrected_document, token, docName)
      }
      className="px-6 py-3 bg-green-600 text-white rounded-lg shadow hover:bg-green-700"
    >
      Download Corrected Document (.docx)
    </button>

  </div>
)}
    <LawInfoModal law={selectedLaw} onClose={() => setSelectedLaw(null)} />
    </div>
  );
}

function LawInfoModal({ law, onClose }) {
  if (!law) return null;

  return (
    <div className="law-modal-overlay" onClick={onClose}>
      <div className="law-modal" onClick={(e) => e.stopPropagation()}>
        <h3 className="law-modal-title">{law.title}</h3>
        <p className="law-modal-description">{law.description}</p>

        <button className="law-modal-close" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}


export default App;
