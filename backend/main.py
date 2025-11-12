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

# AI model modules (you must have these files available under ai_models/)
from ai_models.indian_legal_bert import IndianLegalBERT
from ai_models.risk_engine import AdvancedRiskEngine
from utils.file_processor import FileProcessor

# ---------- Load env ----------
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

# ---------- Model initialization (defensive) ----------
legal_bert = None
risk_engine = None
try:
    legal_bert = IndianLegalBERT()
    # pass None for db_session if you don't have a DB yet; AdvancedRiskEngine handles it
    risk_engine = AdvancedRiskEngine(db_session=None)
    print("[DEBUG] AI models initialized.")
except Exception as e:
    # don't crash at import time; provide clear message
    print("[WARN] Failed to initialize AI models at startup:", str(e))
    # Create placeholders that raise helpful errors when called
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

# ---------- Auth models ----------
class Token(BaseModel):
    access_token: str
    token_type: str

class LoginRequest(BaseModel):
    email: str
    password: str

# ---------- AES helpers ----------
def _ensure_aes_key() -> bytes:
    if AES_KEY_B64:
        try:
            key = b64decode(AES_KEY_B64)
            if len(key) not in (16, 24, 32):
                raise ValueError("Invalid AES key length")
            return key
        except Exception as e:
            raise RuntimeError(f"Invalid AES_KEY_B64: {e}")
    # fallback insecure key (dev only)
    return hashlib.sha256(SECRET_KEY.encode()).digest()[:32]

AES_KEY = _ensure_aes_key()

def _pad(b: bytes) -> bytes:
    pad_len = AES.block_size - (len(b) % AES.block_size)
    return b + bytes([pad_len]) * pad_len

def _unpad(b: bytes) -> bytes:
    pad_len = b[-1]
    return b[:-pad_len]

def encrypt_bytes(data: bytes) -> str:
    iv = get_random_bytes(16)
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    ct = cipher.encrypt(_pad(data))
    return b64encode(iv + ct).decode("utf-8")

def decrypt_bytes(b64str: str) -> bytes:
    raw = b64decode(b64str)
    iv, ct = raw[:16], raw[16:]
    cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
    pt = cipher.decrypt(ct)
    return _unpad(pt)

# ---------- JWT helpers ----------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(request: Request):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = auth.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email != SINGLE_USER_EMAIL:
            raise HTTPException(status_code=401, detail="Invalid user")
        return {"email": email}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ---------- Local byte-based extractors (used when reading encrypted stored files) ----------
def extract_text_from_pdf_bytes(b: bytes) -> str:
    try:
        text = []
        with fitz.open(stream=b, filetype="pdf") as doc:
            for page in doc:
                text.append(page.get_text("text"))
        return "\n".join(text)
    except Exception:
        # return best-effort decode
        try:
            return b.decode("utf-8", errors="replace")
        except Exception:
            return ""

def extract_text_from_docx_bytes(b: bytes) -> str:
    try:
        # python-docx expects a file-like object
        doc = docx.Document(io.BytesIO(b))
        return "\n".join([p.text for p in doc.paragraphs])
    except Exception:
        try:
            return b.decode("utf-8", errors="replace")
        except Exception:
            return ""

# ---------- Routes ----------
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

@app.post("/login", response_model=Token)
def login(body: LoginRequest):
    print(f"[DEBUG] Login attempt: {body.email}")
    if body.email != SINGLE_USER_EMAIL or body.password != SINGLE_USER_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": body.email})
    return {"access_token": access_token, "token_type": "bearer"}

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

@app.post("/analyze")
async def analyze_document(payload: dict, user=Depends(get_current_user)):
    """
    payload expected:
      - text: optional raw text to analyze
      - stored_filename: optional stored encrypted filename (use upload endpoint first)
    """
    text = payload.get("text")
    stored_filename = payload.get("stored_filename")

    # Step 1: If stored file provided, decrypt and extract text
    if not text and stored_filename:
        path = os.path.join(UPLOAD_DIR, stored_filename)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="stored file not found")
        enc = open(path, "r", encoding="utf-8").read()
        try:
            raw = decrypt_bytes(enc)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to decrypt stored file: {e}")

        # Determine extension from original filename inside stored_filename
        lower = path.lower()
        if lower.endswith(".docx.enc"):
            text = extract_text_from_docx_bytes(raw)
        elif lower.endswith(".pdf.enc") or lower.endswith(".enc"):
            # try pdf first, fallback to docx
            try:
                text = extract_text_from_pdf_bytes(raw)
            except Exception:
                text = extract_text_from_docx_bytes(raw)
        else:
            # best effort
            text = extract_text_from_pdf_bytes(raw) or extract_text_from_docx_bytes(raw) or raw.decode("utf-8", errors="replace")

    if not text:
        raise HTTPException(status_code=400, detail="text or stored_filename required")

    # Step 2: segmentation (use FileProcessor.preprocess_text if available)
    try:
        clauses = FileProcessor.preprocess_text(text)
    except Exception:
        # fallback to paragraph split
        clauses = [c.strip() for c in text.split("\n\n") if c.strip()]

    if not clauses:
        clauses = [text]

    results: List[Dict[str, Any]] = []
    total_risk = 0.0

    # Step 3: Analyze first N clauses
    MAX_CLAUSES = 50
    for clause in clauses[:MAX_CLAUSES]:
        # predict clause type + confidence
        try:
            clause_type, confidence = legal_bert.predict_clause_type(clause)
        except Exception as e:
            clause_type, confidence = "general", 0.0

        # risk analysis (AdvancedRiskEngine)
        try:
            risk_data = risk_engine.analyze_risk_with_statutes(clause, clause_type)
        except Exception as e:
            # fail-safe structure
            risk_data = {
                "risk_level": "low",
                "risk_score": 0.0,
                "violations": [],
                "compliance_issues": [],
                "legal_references": [],
                "statute_references": [],
                "pattern_violations": []
            }

        # legal references (if provided)
        try:
            legal_refs = risk_engine.get_legal_references(clause, clause_type)
        except Exception:
            legal_refs = []

        # clause summary
        try:
            summary = legal_bert.generate_dynamic_summary(clause)
        except Exception:
            summary = (clause[:250] + "...") if len(clause) > 250 else clause

        # recommendations
        try:
            recommendations = risk_engine.generate_dynamic_recommendations(clause, risk_data, legal_refs)
        except Exception:
            recommendations = ["Review clause carefully; automated recommendations unavailable."]

        results.append({
            "clause_text": clause[:1000],
            "clause_type": clause_type,
            "confidence": confidence,
            "risk_level": risk_data.get("risk_level", "low"),
            "risk_score": float(risk_data.get("risk_score", 0.0)),
            "summary": summary,
            "violations": risk_data.get("violations", []),
            "recommendations": recommendations,
            "legal_references": legal_refs
        })

        total_risk += float(risk_data.get("risk_score", 0.0))

    # Step 4: Document-level aggregation
    avg_risk = (total_risk / len(results)) if results else 0.0
    overall_risk_level = "High" if avg_risk >= 0.7 else ("Medium" if avg_risk >= 0.3 else "Low")

    # document summary (try full-document summary; fall back to concatenating clause summaries)
    try:
        document_summary = legal_bert.generate_dynamic_summary(text, max_length=150)
    except Exception:
        # fallback: join top clause summaries
        document_summary = " ".join([r["summary"] for r in results[:5]])

    # build detailed_summary string similar to your example
    # --- Filter & report top risky clauses ---
    # --- Filter & report top risky clauses ---
    # === Step 5: Generate filtered risky clauses and summaries ===
    RISK_THRESHOLD = 0.2  # 20%

    # Sort all clause results by risk score (highest first)
    top_sorted = sorted(results, key=lambda x: x["risk_score"], reverse=True)
    risky_clauses = [r for r in top_sorted if r["risk_score"] >= RISK_THRESHOLD]

    # === CASE 1: No risky clauses ===
    if not risky_clauses:
        detailed_summary = (
            "✅ No significant risks detected.\n"
            "All clauses in this document have risk scores below 20%.\n"
            "The document appears legally safe and compliant.\n"
        )
    else:
        # === CASE 2: Risky clauses exist → Hide detailed summary completely ===
        detailed_summary = ""

    # --- Build Recommendations and Legal References ---
    recommendations = []
    legal_refs_set = set()  # To remove duplicates

    for r in risky_clauses:
        # Collect recommendations
        recs = r.get("recommendations", [])
        recommendations.extend(recs)

        # Collect unique law names
        for ref in r.get("legal_references", []):
            statute = ref.get("statute")
            section = ref.get("section")
            if statute:
                if section and section not in statute:
                    legal_refs_set.add(f"{statute} – {section}")
                else:
                    legal_refs_set.add(statute)


    # --- Remove legal references from recommendations ---
    recommendations = [
        rec for rec in recommendations
        if not rec.strip().startswith(("📘", "Reference:", "- Reference:"))
    ]


    # --- Deduplicate and clean ---
    cleaned_recommendations = []
    for rec in recommendations:
        rec = rec.strip()
        if rec and rec not in cleaned_recommendations:
            cleaned_recommendations.append(rec)
    recommendations = cleaned_recommendations

    # --- Handle case: no risky clauses ---
    if not recommendations:
        recommendations = [
            "✅ No significant risks detected.",
            "The document appears legally compliant and safe."
        ]

    # --- Convert unique laws set into sorted list ---
    relevant_laws = sorted(list(legal_refs_set))


    # Fallback if there are no risky clauses
    if not recommendations:
        recommendations = [
            "✅ No significant risks detected.",
            "The document appears legally compliant and safe."
        ]

    # --- Deduplicate and trim recommendations ---
    all_recs = []
    for rec in recommendations:
        if rec not in all_recs:
            all_recs.append(rec)
    all_recs = all_recs[:20]

    # --- Create a readable “Top Risky Clauses” summary (for frontend display) ---
    risky_summary = ""
    if risky_clauses:
        risky_summary += "⚠️ Top Risky Clauses\n(Only clauses with risk ≥ 20% are shown)\n\n"
        for idx, r in enumerate(risky_clauses[:5], 1):
            risk_percent = round(r.get("risk_score", 0) * 100)
            risky_summary += (
                f"{idx}. {r.get('clause_type', 'Unknown').upper()} — "
                f"{r.get('risk_level', 'Unknown').upper()} ({risk_percent}%)\n"
                f"{r.get('summary')}\n\n"
            )

    # --- Collect detected risk clause types (for quick frontend list) ---
    detected_risks = [r["clause_type"] for r in results]

    # --- Final API Response (matches your frontend expectations) ---
    return {
        "summary": document_summary,
        "overall_risk_score": avg_risk,
        "overall_risk_level": overall_risk_level,
        "detailed_summary": detailed_summary,        # hidden if risky clauses exist
        "risky_clauses": risky_clauses[:5],
        "risky_summary": risky_summary,              # added summary of top risky clauses
        "detected_risks": detected_risks,
        "recommendations": all_recs,
        "relevant_laws": relevant_laws,
        "count": len(results),
        "message": (
            "⚠️ High-risk clauses detected above 20%."
            if risky_clauses
            else "✅ No significant risks found. The document appears safe."
        ),
    }

