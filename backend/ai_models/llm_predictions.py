import os
import time
import json
import hashlib
import requests
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

LLM_API_URL = os.getenv("LLM_API_URL", "https://api.groq.com/openai/v1/chat/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "groq/compound-mini")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "12"))
LLM_RETRIES = int(os.getenv("LLM_RETRIES", "2"))
USE_LLM_FIRST = os.getenv("USE_LLM_FIRST", "true").lower() == "true"

_headers = {
    "Authorization": f"Bearer {LLM_API_KEY}",
    "Content-Type": "application/json"
}

_llm_cache = {}

def ask_llm(prompt: str, max_tokens: int = 6000) -> Optional[str]:

    if not LLM_API_KEY:
        print("[LLM] Missing API Key")
        return None

    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens
    }

    for attempt in range(LLM_RETRIES + 1):
        try:
            r = requests.post(
                LLM_API_URL,
                headers=_headers,
                json=payload,
                timeout=LLM_TIMEOUT
            )

            if r.status_code != 200:
                print("[LLM ERROR]", r.status_code, r.text)
                time.sleep(1)
                continue

            data = r.json()

            # RESPONSE FORMAT
            return data["choices"][0]["message"]["content"].strip()

        except Exception as e:
            print(f"[LLM ERROR attempt {attempt}] {e}")
            time.sleep(1)
    print("[LLM] Calling model:", LLM_MODEL)
    print("[LLM] URL:", LLM_API_URL)

    return None

def llm_generate_improved_clause(clause_text: str) -> Optional[str]:
    """
    India-law-compliant clause rewrite with:
      - No content omission
      - Sentence-by-sentence correction
      - Same number of sentences
      - Similar total length to the original clause
      - Enforces Indian legal standards (ICA, Constitution, SRA)
    """

    key = "improve_india_len_" + hashlib.sha256(clause_text.encode()).hexdigest()
    if key in _llm_cache:
        return _llm_cache[key]

    prompt = f"""
You are an expert Indian contract lawyer.

Your task is to REWRITE the clause into a legally safer, enforceable, India-compliant version.

### STRICT RULES:
1. **Do NOT omit any sentence or obligation. Zero content loss.**
2. Break the clause into sentences → legally correct EACH → merge back.
3. **The rewritten clause MUST have the SAME NUMBER OF SENTENCES** as the original.
4. **The rewritten clause must be roughly the SAME LENGTH as the original**  
   (no summarizing, no shortening, no compression).
5. Correct unlawful or high-risk elements under:
   - Indian Contract Act, 1872 — Sections 27 (Restraint of Trade), 73 (Compensation for Breach), 74 (Penalty & Liquidated Damages)
   - SARFAESI Act, 2002 — Section 13 (Enforcement of Security Interest)
   - Transfer of Property Act, 1882
   - Registration Act, 1908
   - Indian Easements Act, 1882
   - Code of Civil Procedure, 1908 (CPC)
   - Indian Evidence Act, 1872
   - Constitution of India — Article 300A (Right to Property)
   - Hindu Succession Act, 1956
   - Indian Succession Act, 1925
6. Apply legal safeguards:
   - Replace absolute/unilateral powers with reasonable, reviewable powers.
   - Ensure fairness, consent, reasonableness, and proportional timelines.
   - Add liability caps (reasonable, direct damages only).
   - Replace overbroad confidentiality with lawful exceptions.
   - Remove perpetual or indefinite restrictions.
   - Restore access to legal remedy (cannot say “final, binding, unappealable”).
7. DO NOT merge, shorten, or compress sentences.
8. NO bullet points, no headers, no explanation — return **only the final clause**.

### ORIGINAL CLAUSE:
\"\"\"{clause_text}\"\"\"

### NOW RETURN ONLY THE FULL, LENGTH-PRESERVING, LEGALLY SAFER CLAUSE:
"""

    result = ask_llm(prompt, max_tokens=8000)

    if result:
        cleaned = result.strip()
        _llm_cache[key] = cleaned
        return cleaned

    return None

def llm_generate_summary(clause_text: str) -> Optional[str]:
    key = "summary_" + hashlib.sha256(clause_text.encode()).hexdigest()
    if key in _llm_cache:
        return _llm_cache[key]

    prompt = f"""
Summarize this legal clause in 3–4 sentences.
Do NOT rewrite it. Do NOT remove any obligations.

Clause:
\"\"\"{clause_text}\"\"\"

Summary:
"""

    result = ask_llm(prompt, max_tokens=1000)
    _llm_cache[key] = result
    return result

def llm_predict_clause_type(clause_text: str) -> Optional[dict]:
    key = "type_" + hashlib.sha256(clause_text.encode()).hexdigest()
    if key in _llm_cache:
        return _llm_cache[key]

    prompt = f"""
Identify the type of this legal clause and respond ONLY in valid JSON.

Return:
- clause_type (e.g., confidentiality, liability, payment, termination, dispute_resolution)
- confidence (value between 0 and 1)

Clause:
\"\"\"{clause_text}\"\"\"

JSON:
"""

    raw = ask_llm(prompt, max_tokens=500)

    if not raw:
        return None

    try:
        parsed = json.loads(raw)
        _llm_cache[key] = parsed
        return parsed
    except:
        return None
