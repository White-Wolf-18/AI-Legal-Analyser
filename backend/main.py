# backend/main.py
import os
import io
import json
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from jose import jwt, JWTError

import fitz  # PyMuPDF
import docx
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from base64 import b64encode, b64decode
from dotenv import load_dotenv

# AI model modules
from ai_models.indian_legal_bert import IndianLegalBERT
from ai_models.risk_engine import AdvancedRiskEngine
from utils.file_processor import FileProcessor

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
AES_KEY_B64 = os.getenv("AES_KEY_B64")
SINGLE_USER_EMAIL = os.getenv("SINGLE_USER_EMAIL", "admin@example.com")
SINGLE_USER_PASSWORD = os.getenv("SINGLE_USER_PASSWORD", "changeme")

os.makedirs(UPLOAD_DIR, exist_ok=True)

print(f"[DEBUG] SINGLE_USER_EMAIL={SINGLE_USER_EMAIL}")

# ---------- Model Initialization ----------
legal_bert = None
risk_engine = None
try:
    legal_bert = IndianLegalBERT()
    risk_engine = AdvancedRiskEngine(db_session=None)
    print("[DEBUG] AI models initialized.")
except Exception as e:
    print("[WARN] Failed to initialize AI models at startup:", str(e))
    class _BrokenModel:
        def __getattr__(self, name):
            def _boom(*a, **k):
                raise RuntimeError(f"Model not available: attempted to call {name}. Original error: {e}")
            return _boom
    legal_bert = _BrokenModel()
    risk_engine = _BrokenModel()

# ---------- FastAPI ----------
app = FastAPI(title="Legal AI Document Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Token(BaseModel):
    access_token: str
    token_type: str

class LoginRequest(BaseModel):
    email: str
    password: str

# ---------- AES Encryption ----------
def _ensure_aes_key() -> bytes:
    if AES_KEY_B64:
        try:
            key = b64decode(AES_KEY_B64)
            if len(key) not in (16, 24, 32):
                raise ValueError("Invalid AES key length")
            return key
        except Exception as e:
            raise RuntimeError(f"Invalid AES_KEY_B64: {e}")

    return hashlib.sha256(SECRET_KEY.encode()).digest()[:32]

AES_KEY = _ensure_aes_key()

def _pad(b: bytes) -> bytes:
    pad_len = AES.block_size - (len(b) % AES.block_size)
    return b + bytes([pad_len]) * pad_len

def _unpad(b: bytes) -> bytes:
    return b[:-b[-1]]

def encrypt_bytes(data: bytes) -> str:
    iv = get_random_bytes(16)
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    ct = cipher.encrypt(_pad(data))
    return b64encode(iv + ct).decode("utf-8")

def decrypt_bytes(b64str: str) -> bytes:
    raw = b64decode(b64str)
    iv, ct = raw[:16], raw[16:]
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    return _unpad(cipher.decrypt(ct))

# ---------- Auth ----------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {**data, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") != SINGLE_USER_EMAIL:
            raise HTTPException(status_code=401, detail="Invalid user")
        return {"email": payload["sub"]}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

@app.post("/login", response_model=Token)
def login(body: LoginRequest):
    if body.email != SINGLE_USER_EMAIL or body.password != SINGLE_USER_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_access_token({"sub": body.email}), "token_type": "bearer"}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), user=Depends(get_current_user)):
    fname = file.filename
    content = await file.read()

    if not fname.lower().endswith((".pdf", ".docx")):
        raise HTTPException(status_code=400, detail="Only .pdf and .docx supported")

    enc = encrypt_bytes(content)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    h = hashlib.sha256(content).hexdigest()[:12]
    out_name = f"{stamp}_{h}_{os.path.basename(fname)}.enc"
    out_path = os.path.join(UPLOAD_DIR, out_name)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(enc)

    return {"stored_filename": out_name}

# ---------- Local Extractors ----------
def extract_text_from_pdf_bytes(b: bytes) -> str:
    try:
        text = []
        with fitz.open(stream=b, filetype="pdf") as doc:
            for page in doc:
                text.append(page.get_text("text"))
        return "\n".join(text)
    except:
        return b.decode("utf-8", errors="replace")

def extract_text_from_docx_bytes(b: bytes) -> str:
    try:
        doc = docx.Document(io.BytesIO(b))
        return "\n".join([p.text for p in doc.paragraphs])
    except:
        return b.decode("utf-8", errors="replace")
# ---------------- PART 2: /analyze endpoint and helpers ----------------

import re

def generate_improved_clause(clause_text: str, clause_type: str) -> str:
    """
    Produce a safer, lower-risk version of a clause.
    Strategy:
      - Use heuristic replacements for common risky patterns (penalties, unlimited liability, vague 'reasonable', long non-competes).
      - If model summarizer is available, ask it to rewrite concisely and safely (best-effort).
      - Always return a readable clause (not empty).
    """
    # quick normalization
    t = clause_text.strip()

    # Heuristic safe rewrites (ordered)
    # 1) unlimited liability -> capped liability
    t_safe = re.sub(r'unlimited\s+liability', 'liability capped to a reasonable aggregate amount not exceeding INR 1,00,00,000', t, flags=re.IGNORECASE)

    # 2) penalty % -> convert to reasonable penalty or suggest liquidated damages wording
    t_safe = re.sub(r'penalty\s*@?\s*(\d+)%', r'penalty at \1% (subject to reasonable cap and judicial review)', t_safe, flags=re.IGNORECASE)

    # 3) 'reasonable time' -> make concrete
    t_safe = re.sub(r'reasonable\s+time', 'within 30 days', t_safe, flags=re.IGNORECASE)

    # 4) 'at discretion' -> require 'reasonable written notice and justification'
    t_safe = re.sub(r'at\s+its\s+discretion', 'upon reasonable written notice and justification', t_safe, flags=re.IGNORECASE)
    t_safe = re.sub(r'at\s+discretion', 'upon reasonable written notice and justification', t_safe, flags=re.IGNORECASE)

    # 5) non-compete durations -> cap to 2 years and add geographic scope
    t_safe = re.sub(r'non-?compete.*?(\d{1,2})\s*years?', 'non-compete limited to 2 years and a defined geographic scope as reasonably necessary to protect legitimate business interests', t_safe, flags=re.IGNORECASE)

    # 6) vague 'subject to change' -> add notice period
    t_safe = re.sub(r'subject\s+to\s+change', 'subject to change with at least 30 days prior written notice and mutual agreement', t_safe, flags=re.IGNORECASE)

    # 7) deposit forfeiture -> add basis/justification
    t_safe = re.sub(r'forfeit(ed)?\s+deposit', 'forfeiture of deposit only where objectively justified and after prior notice and opportunity to cure', t_safe, flags=re.IGNORECASE)

    # If heuristics changed something, prefer that
    if t_safe != t:
        # ensure sentence ends properly
        t_safe = t_safe.strip()
        if not t_safe.endswith('.'):
            t_safe += '.'
        return t_safe

    # If heuristics didn't touch clause much, try model summarizer to rewrite (if available)
    try:
        if hasattr(legal_bert, "summarizer"):
            prompt = (
                "Rewrite the following legal clause to reduce legal risk while preserving "
                "the original intent. Make language concrete, cap open-ended liability, "
                "replace vague timelines with specific ones and keep it suitable for an "
                "Indian commercial contract. Provide only the rewritten clause.\n\n"
                f"Clause: {t}"
            )
            # call model summarizer (text2text) if available
            out = legal_bert.summarizer(prompt, max_length=150, min_length=40, do_sample=False, truncation=True)
            if out and isinstance(out, list) and out[0].get("generated_text"):
                rewritten = out[0]["generated_text"].strip()
                if rewritten and len(rewritten) > 10:
                    if not rewritten.endswith('.'):
                        rewritten += '.'
                    return rewritten
    except Exception:
        # model failed -> fall back
        pass

    # Final simple safe fallback: produce a templated safer clause
    fallback = (
        "Suggested safer clause: The parties shall comply with applicable law; "
        "liability shall be limited to direct damages and capped at a reasonable amount; "
        "penalties (if any) shall be proportionate and reasonable and calculated as liquidated damages. "
        "Any timelines shall be specified in writing (for example, within 30 days)."
    )
    return fallback


@app.post("/analyze")
async def analyze_document(payload: dict, user=Depends(get_current_user)):
    """
    Analyze uploaded text or stored encrypted file.
    Returns a structure compatible with your frontend:
     - summary, overall_risk_score, overall_risk_level
     - detailed_summary (hidden when risky clauses exist)
     - risky_clauses (each includes an improved_clause if >= threshold)
     - risky_summary (plain text summary)
     - recommendations (deduped)
     - relevant_laws (deduped list)
     - count, message, detected_risks
    """
    text = payload.get("text")
    stored_filename = payload.get("stored_filename")

    # Decrypt and extract text from stored file if needed
    if not text and stored_filename:
        path = os.path.join(UPLOAD_DIR, stored_filename)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="stored file not found")
        enc = open(path, "r", encoding="utf-8").read()
        try:
            raw = decrypt_bytes(enc)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to decrypt stored file: {e}")

        # choose extractor heuristically
        lower = path.lower()
        if lower.endswith(".docx.enc"):
            text = extract_text_from_docx_bytes(raw)
        else:
            # try pdf, then docx
            text = extract_text_from_pdf_bytes(raw) or extract_text_from_docx_bytes(raw) or raw.decode("utf-8", errors="replace")

    if not text:
        raise HTTPException(status_code=400, detail="text or stored_filename required")

    # segmentation into clauses (use FileProcessor.preprocess_text if available)
    try:
        clauses = FileProcessor.preprocess_text(text)
    except Exception:
        clauses = [c.strip() for c in text.split("\n\n") if c.strip()]

    if not clauses:
        clauses = [text]

    results: List[Dict[str, Any]] = []
    total_risk = 0.0
    MAX_CLAUSES = 50

    # Analyze clauses
    for clause in clauses[:MAX_CLAUSES]:
        # clause type
        try:
            clause_type, confidence = legal_bert.predict_clause_type(clause)
        except Exception:
            clause_type, confidence = "general", 0.0

        # risk analysis
        try:
            risk_data = risk_engine.analyze_risk_with_statutes(clause, clause_type)
        except Exception:
            risk_data = {
                "risk_level": "low",
                "risk_score": 0.0,
                "violations": [],
                "compliance_issues": [],
                "legal_references": [],
                "statute_references": [],
                "pattern_violations": []
            }

        # legal refs (if engine provides)
        try:
            legal_refs = risk_engine.get_legal_references(clause, clause_type)
        except Exception:
            legal_refs = risk_data.get("legal_references", [])

        # summary
        try:
            summary = legal_bert.generate_dynamic_summary(clause)
        except Exception:
            summary = (clause[:250] + "...") if len(clause) > 250 else clause

        # recommendations
        try:
            recommendations = risk_engine.generate_dynamic_recommendations(clause, risk_data, legal_refs)
        except Exception:
            recommendations = ["Review clause carefully; automated recommendations unavailable."]

        # --- determine if clause is risky ---
        is_risky = float(risk_data.get("risk_score", 0.0)) >= 0.20

        # --- generate improved clause ONLY for risky ones ---
        improved = None
        try:
            if is_risky:
                improved = generate_improved_clause(clause, clause_type)
        except Exception:
            improved = None

         # --- append full clause details ---
        results.append({
            "clause_text": clause,                       # FULL original clause, not trimmed
            "clause_type": clause_type, 
            "confidence": float(confidence),
            "risk_level": risk_data.get("risk_level", "low"),
            "risk_score": float(risk_data.get("risk_score", 0.0)),
            "summary": summary,
            "violations": risk_data.get("violations", []),
            "compliance_issues": risk_data.get("compliance_issues", []),
            "recommendations": recommendations,
            "legal_references": legal_refs,
            "improved_clause": improved                 # ← Added improved version (only for risky)
        })
        total_risk += float(risk_data.get("risk_score", 0.0))

    # Document-level aggregates
    avg_risk = (total_risk / len(results)) if results else 0.0
    overall_risk_level = "High" if avg_risk >= 0.7 else ("Medium" if avg_risk >= 0.3 else "Low")

    # document summary
    try:
        document_summary = legal_bert.generate_dynamic_summary(text, max_length=150)
    except Exception:
        document_summary = " ".join([r["summary"] for r in results[:5]])

    # Prepare risky clause filtering & final outputs
    RISK_THRESHOLD = 0.2  # 20%
    top_sorted = sorted(results, key=lambda x: x["risk_score"], reverse=True)
    risky_clauses = [r for r in top_sorted if r["risk_score"] >= RISK_THRESHOLD]

    # If no risky clauses, produce friendly detailed_summary; otherwise hide detailed_summary
    if not risky_clauses:
        detailed_summary = (
            "✅ No significant risks detected.\n"
            "All clauses in this document have risk scores below 20%.\n"
            "The document appears legally safe and compliant.\n"
        )
    else:
        detailed_summary = ""  # hide if risky clauses present

    # Build recommendations (deduped) from risky_clauses only and remove law references embedded in recs
    recs_acc = []
    law_set = set()
    for r in risky_clauses:
        for rec in r.get("recommendations", []):
            # strip law-prefixed lines like '📘' or 'Reference:' if present
            if isinstance(rec, str) and (rec.strip().startswith("📘") or rec.strip().lower().startswith("reference") or rec.strip().lower().startswith("- reference")):
                # skip, we'll collect laws separately
                continue
            if isinstance(rec, str) and rec.strip() and rec.strip() not in recs_acc:
                recs_acc.append(rec.strip())

        # collect laws from legal_references field
        for ref in r.get("legal_references", []):
            if isinstance(ref, dict):
                statute = ref.get("statute", "").strip()
                section = ref.get("section", "").strip()
                if statute:
                    if section and section not in statute:
                        law_set.add(f"{statute} – {section}")
                    else:
                        law_set.add(statute)
            elif isinstance(ref, str):
                law_set.add(ref.strip())

    # If no recommendations were collected (no risky clauses), add safe-note
    if not recs_acc and not risky_clauses:
        recs_acc = [
            "✅ No significant risks detected.",
            "The document appears legally compliant and safe."
        ]

    # Dedupe and cap recommendations
    final_recommendations = []
    for r in recs_acc:
        if r not in final_recommendations:
            final_recommendations.append(r)
    final_recommendations = final_recommendations[:20]

    # Prepare relevant_laws list
    relevant_laws = sorted(list(law_set))

    # Prepare risky_summary (text) for frontend convenience
    risky_summary = ""
    if risky_clauses:
        risky_summary += "⚠️ Top Risky Clauses\n(Only clauses with risk ≥ 20% are shown)\n\n"
        for idx, r in enumerate(risky_clauses[:10], start=1):
            risk_percent = round(r.get("risk_score", 0.0) * 100)
            risky_summary += (
                f"{idx}. {r.get('clause_type', 'Unknown').upper()} — "
                f"{r.get('risk_level', 'Unknown').upper()} ({risk_percent}%)\n"
                f"{r.get('summary')}\n\n"
            )

    # Prepare response risky_clauses output trimmed for frontend
    risky_clauses_out = []
    for r in risky_clauses[:10]:
        # include 'improved_clause' only for risky ones (already generated above)
        risky_clauses_out.append({
            "clause_type": r.get("clause_type"),
            "risk_level": r.get("risk_level"),
            "risk_score": float(r.get("risk_score", 0.0)),
            "summary": r.get("summary"),
            "clause_text": r.get("clause_text"), 
            "recommendations": r.get("recommendations", [])[:6],
            "legal_references": r.get("legal_references", [])[:6],
            "improved_clause": r.get("improved_clause")
        })

    detected_risk_types = [r["clause_type"] for r in results]

    # Determine message
    if risky_clauses:
        if overall_risk_level == "High":
            message = "🚨 Several problematic clauses detected. Strongly consider revisions."
        elif overall_risk_level == "Medium":
            message = "⚠️ Some clauses may pose moderate risk. Review recommended."
        else:
            message = "⚠️ Risky clauses detected. Please review recommendations."
    else:
        message = "✅ No significant risks found. The document appears safe."

    return {
        "summary": document_summary,
        "overall_risk_score": avg_risk,
        "overall_risk_level": overall_risk_level,
        "detailed_summary": detailed_summary,
        "risky_clauses": risky_clauses_out,
        "risky_summary": risky_summary,
        "detected_risks": detected_risk_types,
        "recommendations": final_recommendations,
        "relevant_laws": relevant_laws,
        "count": len(results),
        "message": message
    }
