import React, { useState } from "react";

export default function CorrectedDocument({
  originalClauses = [],
  correctedDocument = "",
}) {
  const [view, setView] = useState("corrected");

  // Combine all original clauses into one string
  const originalText = originalClauses.join("\n\n");

  // Render paragraphs
  const renderFormatted = (text) => {
    return text
      .split(/\n\s*\n/)
      .map((p, i) => p.trim())
      .filter((p) => p.length > 0)
      .map((p, i) => (
        <p key={i} className="doc-paragraph">
          {p}
        </p>
      ));
  };

  return (
    <div className="corrected-doc-container">
      <h2>📄 Corrected Document (AI-Reconstructed)</h2>

      {/* Toggle Buttons */}
      <div className="corrected-toggle-buttons">
        <button
          className={view === "corrected" ? "active" : "inactive"}
          onClick={() => setView("corrected")}
        >
          AI-Corrected Version
        </button>
        <button
          className={view === "original" ? "active" : "inactive"}
          onClick={() => setView("original")}
        >
          Original Document
        </button>
        <button
          className={view === "compare" ? "active" : "inactive"}
          onClick={() => setView("compare")}
        >
          Side-by-Side Compare
        </button>
      </div>

      {/* Content Box */}
      <div className="corrected-doc-box">
        {view === "corrected" && (
          <div className="docx-view">
            {renderFormatted(correctedDocument)}
          </div>
        )}
        {view === "original" && (
          <div className="docx-view">
            {renderFormatted(originalText)}
          </div>
        )}
        {view === "compare" && (
          <div className="compare-grid">
            <div className="compare-column">
              <h4 className="compare-title original-title">Original</h4>
              <div className="docx-view">
                {renderFormatted(originalText)}
              </div>
            </div>
            <div className="compare-column">
              <h4 className="compare-title improved-title">Improved</h4>
              <div className="docx-view">
                {renderFormatted(correctedDocument)}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
