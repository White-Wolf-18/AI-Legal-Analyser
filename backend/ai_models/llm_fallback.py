import os
import time
import requests
import json

LLM_API_URL = os.getenv("LLM_API_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "groq/compound-mini")
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "12"))
LLM_RETRIES = int(os.getenv("LLM_RETRIES", "2"))

def call_llm(prompt: str, max_tokens=6000):
    """Unified LLM caller with retries."""
    if not LLM_API_URL or not LLM_API_KEY:
        return None
    
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0
    }

    for attempt in range(LLM_RETRIES + 1):
        try:
            res = requests.post(
                LLM_API_URL,
                headers=headers,
                json=payload,
                timeout=LLM_TIMEOUT
            )
            res.raise_for_status()
            data = res.json()

            text = data["choices"][0]["message"]["content"]
            return text
        except Exception:
            if attempt == LLM_RETRIES:
                return None
            time.sleep(0.5 * (attempt + 1))
