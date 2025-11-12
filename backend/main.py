import os
import io
import json
import hashlib
from typing import Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import jwt, JWTError
from pydantic import BaseModel

import fitz  # PyMuPDF
import docx
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from base64 import b64encode, b64decode
from dotenv import load_dotenv

# ---------------- AI Models ----------------
from ai_models.indian_legal_bert import IndianLegalBERT
from ai_models.risk_engine import AdvancedRiskEngine
from utils.file_processor import FileProcessor

# ---------- Load ENV ----------
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
AES_KEY_B64 = os.getenv("AES_KEY_B64")
SINGLE_USER_EMAIL = os.getenv("SINGLE_USER_EMAIL", "admin@example.com")
SINGLE_USER_PASSWORD = os.getenv("SINGLE_USER_PASSWORD", "changeme")

print(f"[DEBUG] Loaded Email: {SINGLE_USER_EMAIL}")
print(f"[DEBUG] Loaded Password: {SINGLE_USER_PASSWORD}")

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------- Initialize AI Models ----------
legal_bert = IndianLegalBERT()
risk_engine = AdvancedRiskEngine(db_session=None)

# ---------- FastAPI ----------
app = FastAPI(title="Legal AI Document Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Auth Models ----------
class Token(BaseModel):
    access_token: str
    token_type: str

class LoginRequest(BaseModel):
    email: str
    password: str

# ---------- AES Helpers ----------
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

# ---------- JWT Helpers ----------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
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

# ---------- Health Check ----------
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

# ---------- Login ----------
@app.post("/login", response_model=Token)
def login(body: LoginRequest):
    print(f"[DEBUG] Login attempt: {body.email}")
    if body.email != SINGLE_USER_EMAIL or body.password != SINGLE_USER_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": body.email})
    return {"access_token": access_token, "token_type": "bearer"}

# ---------- File Upload ----------
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

# ---------- File Text Extraction ----------
def extract_text_from_pdf_bytes(b: bytes) -> str:
    text = []
    with fitz.open(stream=b, filetype="pdf") as doc:
        for page in doc:
            text.append(page.get_text("text"))
    return "\n".join(text)

def extract_text_from_docx_bytes(b: bytes) -> str:
    doc = docx.Document(io.BytesIO(b))
    return "\n".join([p.text for p in doc.paragraphs])

# ---------- Document Analysis ----------
@app.post("/analyze")
async def analyze_document(payload: dict, user=Depends(get_current_user)):
    try:
        text = payload.get("text")
        stored_filename = payload.get("stored_filename")

        if not text and stored_filename:
            path = os.path.join(UPLOAD_DIR, stored_filename)
            if not os.path.exists(path):
                raise HTTPException(status_code=404, detail="File not found")
            enc = open(path, "r", encoding="utf-8").read()
            raw = decrypt_bytes(enc)
            if path.lower().endswith(".docx.enc"):
                text = extract_text_from_docx_bytes(raw)
            else:
                text = extract_text_from_pdf_bytes(raw)

        if not text:
            raise HTTPException(status_code=400, detail="Text or stored_filename required")

        # ----------- Analysis using new models -----------
        clauses = FileProcessor.preprocess_text(text)
        results = []
        total_risk = 0

        for clause in clauses[:50]:  # Limit to first 50 clauses for performance
            clause_type, confidence = legal_bert.predict_clause_type(clause)
            risk_data = risk_engine.analyze_risk_with_statutes(clause, clause_type)
            legal_refs = risk_engine.get_legal_references(clause, clause_type)
            summary = legal_bert.generate_dynamic_summary(clause)
            recommendations = risk_engine.generate_dynamic_recommendations(clause, risk_data, legal_refs)

            results.append({
                "clause_text": clause[:600],
                "clause_type": clause_type,
                "risk_level": risk_data["risk_level"],
                "risk_score": risk_data["risk_score"],
                "confidence": confidence,
                "summary": summary,
                "recommendations": recommendations,
            })
            total_risk += risk_data["risk_score"]

        # ----------- Aggregate Results -----------
        document_summary = legal_bert.generate_dynamic_summary(text)
        avg_risk = total_risk / len(results) if results else 0
        high = sum(1 for r in results if r["risk_level"] == "high")
        medium = sum(1 for r in results if r["risk_level"] == "medium")
        low = sum(1 for r in results if r["risk_level"] == "low")

        return {
            "summary": document_summary,
            "overall_risk_score": avg_risk,
            "overall_risk_level": "High" if avg_risk >= 0.7 else "Medium" if avg_risk >= 0.3 else "Low",
            "risk_distribution": {"high": high, "medium": medium, "low": low},
            "clauses_analyzed": len(results),
            "detailed_analysis": results,
            "recommendations": list({rec for r in results for rec in r["recommendations"]})[:15],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
