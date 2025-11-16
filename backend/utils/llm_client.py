import os
import requests
import time
from typing import Optional
from dotenv import load_dotenv
load_dotenv()


class LLMClient:
    """
    Universal LLM wrapper for APIs.
    Falls back gracefully by returning None if model fails.
    """

    def __init__(self):
        self.api_url = os.getenv("LLM_API_URL", "").strip()
        self.api_key = os.getenv("LLM_API_KEY", "").strip()
        self.model = os.getenv("LLM_MODEL", "groq/compound-mini")
        self.timeout = int(os.getenv("LLM_TIMEOUT", "12"))
        self.retries = int(os.getenv("LLM_RETRIES", "2"))
        self.enabled = os.getenv("USE_LLM_FIRST", "true").lower() == "true"

        if not self.api_url or not self.api_key:
            print("[LLM] WARNING: LLM is disabled. Missing LLM_API_URL or LLM_API_KEY.")
            self.enabled = False

    def ask(self, prompt: str, max_tokens: int = 6000) -> Optional[str]:
        """
        Sends the prompt to the LLM. 
        Returns LLM response text, or None if LLM fails.
        """

        if not self.enabled:
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a legal AI assistant specializing in Indian law."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens
        }

        # Retry logic
        for attempt in range(self.retries + 1):
            try:
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    data = response.json()
                    text = data["choices"][0]["message"]["content"].strip()
                    return text

                else:
                    print(f"[LLM] API error {response.status_code}: {response.text}")

            except requests.exceptions.Timeout:
                print("[LLM] Timeout, retrying...")
            except Exception as e:
                print(f"[LLM] Error: {e}")

            # wait before retry
            if attempt < self.retries:
                time.sleep(0.5)

        print("[LLM] Failed after retries. Falling back to BERT.")
        return None
