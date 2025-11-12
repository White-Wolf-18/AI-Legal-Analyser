import re
import json
from typing import Dict, List, Tuple, Any
import spacy
from transformers import pipeline
import logging

class AdvancedRiskEngine:
    """
    Enhanced risk analysis engine for Indian legal documents.
    Context-aware clause-level risk evaluation with statute references
    and adaptive recommendations.
    """
    def __init__(self, db_session=None):
        self.db = db_session
        self.nlp = spacy.load("en_core_web_sm")
        self.statute_cache = self._load_statutes()

        # QA pipeline for contextual statute reference extraction
        self.legal_reference_pipeline = pipeline(
            "question-answering",
            model="deepset/roberta-base-squad2"
        )

        # Dynamic risk patterns mapped to Indian statutes
        self.risk_patterns = {
            "high": [
                {
                    "pattern": r"unlimited.*liability",
                    "explanation": "Unlimited liability clauses can expose parties to excessive financial risk beyond reasonable bounds.",
                    "statute_reference": "Indian Contract Act, 1872 – Section 73"
                },
                {
                    "pattern": r"forfeit.*deposit",
                    "explanation": "Deposit forfeiture without due cause can be legally challenged under property laws.",
                    "statute_reference": "Transfer of Property Act, 1882 – Deposit refund obligations"
                },
                {
                    "pattern": r"non[- ]?compete.*\d+.*year",
                    "explanation": "Excessive non-compete durations may be unenforceable in India.",
                    "statute_reference": "Indian Contract Act, 1872 – Section 27: Restraint of trade"
                },
                {
                    "pattern": r"penalty.*\d+%",
                    "explanation": "High penalty rates may be deemed excessive and void under Indian law.",
                    "statute_reference": "Indian Contract Act, 1872 – Section 74: Penalty for breach of contract"
                },
            ],
            "medium": [
                {
                    "pattern": r"subject.*to.*change",
                    "explanation": "Clauses that allow unilateral change create uncertainty and imbalance.",
                    "statute_reference": "Indian Contract Act, 1872 – Section 62"
                },
                {
                    "pattern": r"reasonable.*time",
                    "explanation": "Ambiguous ‘reasonable time’ wording can lead to disputes.",
                    "statute_reference": "Indian Contract Act, 1872 – Section 55"
                },
                {
                    "pattern": r"at.*discretion",
                    "explanation": "Discretion clauses must specify limits to avoid arbitrary enforcement.",
                    "statute_reference": "Indian Contract Act, 1872 – Section 56"
                }
            ],
            "low": [
                {
                    "pattern": r"as.*per.*law",
                    "explanation": "Standard compliance language is generally valid.",
                    "statute_reference": "Constitution of India – Article 14"
                }
            ]
        }

    # -------------------------------------------------------------------------
    def _load_statutes(self):
        """Minimal built-in legal statutes."""
        return {
            "Indian Contract Act, 1872 – Section 73": {
                "section": "Section 73",
                "description": "Compensation for loss or damage caused by breach of contract.",
                "keywords": ["breach", "compensation", "damages", "loss"],
                "applicable_clauses": ["loan", "employment", "rental", "partnership"]
            },
            "Indian Contract Act, 1872 – Section 27": {
                "section": "Section 27",
                "description": "Agreements in restraint of trade are void.",
                "keywords": ["non-compete", "restraint", "trade"],
                "applicable_clauses": ["employment", "partnership"]
            },
            "Indian Contract Act, 1872 – Section 74": {
                "section": "Section 74",
                "description": "Penalty for breach of contract.",
                "keywords": ["penalty", "fine", "default"],
                "applicable_clauses": ["loan", "employment", "rental"]
            },
            "SARFAESI Act, 2002": {
                "section": "Section 13",
                "description": "Enforcement of security interest by secured creditors.",
                "keywords": ["security", "pledge", "collateral"],
                "applicable_clauses": ["loan", "security", "mortgage"]
            }
        }

    # -------------------------------------------------------------------------
    def analyze_risk_with_statutes(self, clause: str, clause_type: str) -> Dict:
        """Perform multi-layer risk analysis for a given clause."""
        clause_lower = clause.lower()

        pattern_violations = self._analyze_pattern_violations(clause)
        statute_violations = []
        compliance_issues = []
        legal_references = []

        # Cross-check clause with relevant statutes
        for statute_name, statute in self.statute_cache.items():
            if clause_type in statute["applicable_clauses"]:
                relevance = self._calculate_relevance(clause, statute["keywords"])
                legal_references.append({
                    "statute": statute_name,
                    "section": statute["section"],
                    "description": statute["description"],
                    "relevance_score": relevance
                })

                for keyword in statute["keywords"]:
                    if keyword in clause_lower:
                        if re.search(r"not\s+" + re.escape(keyword), clause_lower):
                            statute_violations.append({
                                "statute": statute_name,
                                "section": statute["section"],
                                "violation": f"Clause contradicts {statute['section']}: missing compliance with {keyword}",
                                "severity": "high",
                                "explanation": f"This clause appears to contradict {statute['section']} of {statute_name}."
                            })
                        elif "ambiguous" in clause_lower or "unclear" in clause_lower:
                            compliance_issues.append({
                                "statute": statute_name,
                                "section": statute["section"],
                                "issue": f"Ambiguity regarding {keyword} compliance.",
                                "severity": "medium",
                                "explanation": f"Ambiguous compliance with {statute_name} – may lead to interpretational disputes."
                            })

        # Merge all violations
        all_violations = pattern_violations + statute_violations
        high = len([v for v in all_violations if v.get("severity") == "high"])
        medium = len([v for v in all_violations if v.get("severity") == "medium"])
        risk_score = min((high * 0.4 + medium * 0.2), 1.0)

        risk_level = "high" if risk_score >= 0.7 else "medium" if risk_score >= 0.3 else "low"

        return {
            "risk_level": risk_level,
            "risk_score": round(risk_score, 2),
            "violations": all_violations,
            "compliance_issues": compliance_issues,
            "legal_references": sorted(legal_references, key=lambda x: x["relevance_score"], reverse=True)[:5]
        }

    # -------------------------------------------------------------------------
    def _analyze_pattern_violations(self, clause: str) -> List[Dict]:
        """Check clause text for pattern-based violations."""
        clause_lower = clause.lower()
        found = []

        for severity, patterns in self.risk_patterns.items():
            for pattern in patterns:
                if re.search(pattern["pattern"], clause_lower, re.IGNORECASE):
                    found.append({
                        "type": "pattern_violation",
                        "severity": severity,
                        "violation_description": pattern["explanation"],
                        "statute_reference": pattern["statute_reference"],
                        "explanation": pattern["explanation"]
                    })
        return found

    def _calculate_relevance(self, clause: str, keywords: List[str]) -> float:
        """Compute keyword relevance score."""
        clause_lower = clause.lower()
        score = sum(1 for k in keywords if k in clause_lower) / (len(keywords) or 1)
        return min(score + (0.1 if "shall" in clause_lower else 0), 1.0)

    # -------------------------------------------------------------------------
    def generate_dynamic_recommendations(
        self, clause: str, risk_data: Dict, legal_refs: List[Dict]
    ) -> List[str]:
        """Generate detailed, context-aware recommendations per clause."""
        recs = []
        c = clause.lower()

        # Clause-based insights
        if "pledge" in c or "collateral" in c:
            recs.append("Ensure pledged security is clearly identified and not transferred without consent.")
        if "penalty" in c:
            recs.append("Check if the penalty percentage is reasonable and proportionate to breach.")
        if "termination" in c and "notice" not in c:
            recs.append("Add a defined notice period before termination to avoid sudden enforcement.")
        if "indemnify" in c:
            recs.append("Limit indemnity scope to direct losses only, not consequential damages.")
        if "without objection" in c or "demur" in c:
            recs.append("Avoid 'without demur' phrasing — replace with 'subject to valid objections'.")
        if "loan" in c and "interest" in c and "%" not in c:
            recs.append("Specify exact interest rate and payment frequency to avoid ambiguity.")
        if not recs:
            recs.append("Clause appears compliant under Indian Contract Act norms.")

        # Add high-risk violations with fix actions
        for v in risk_data.get("violations", []):
            if v["severity"] == "high":
                recs.append(f"⚠️ Critical: {v['violation_description']}")
                recs.append(f"   - Reference: {v['statute_reference']}")

        # Medium issues → contextual fix
        for v in risk_data.get("compliance_issues", []):
            recs.append(f"⚠️ Review: {v['issue']}")
            recs.append(f"   - Suggestion: Clarify or define ambiguous terms explicitly.")

        # Add relevant laws
        top_laws = [r["statute"] for r in legal_refs[:2]]
        if top_laws:
            recs.append(f"📘 Relevant Indian Laws: {', '.join(top_laws)}")

        return recs
    
    def get_legal_references(self, clause: str, clause_type: str) -> List[Dict]:
        """Return the most relevant legal statutes and sections for a clause."""
        legal_refs = []
        clause_lower = clause.lower()

        # Search through loaded statute cache
        for statute_name, statute_info in self.statute_cache.items():
            relevance = self._calculate_relevance(clause, statute_info["keywords"])
            if relevance > 0:
                legal_refs.append({
                    "statute": statute_name,
                    "section": statute_info["section"],
                    "description": statute_info["description"],
                    "relevance_score": relevance,
                    "matched_keywords": [
                        kw for kw in statute_info["keywords"] if kw.lower() in clause_lower
                    ]
                })

        # Add clause-type-based fallback using IndianLegalBERT law mapping
        from ai_models.indian_legal_bert import IndianLegalBERT
        bert = IndianLegalBERT()
        law_name = bert.get_relevant_law(clause_type)

        # If nothing found via statute cache, still include this default
        if not legal_refs:
            legal_refs.append({
                "statute": law_name,
                "section": "—",
                "description": f"Relevant under {law_name}",
                "relevance_score": 0.5,
                "matched_keywords": []
            })

        # Sort descending by relevance
        legal_refs.sort(key=lambda x: x["relevance_score"], reverse=True)

        # Return top 3 for clarity
        return legal_refs[:3]

