"""
Talk to any OpenAI-compatible chat API (DeepSeek, OpenAI, Qwen, a local Ollama...).

Each provider preset says where the API lives, which environment variable holds
the key, and a default model. Users can override the model or point to any
other compatible server with --base-url.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests

PROVIDERS = {
    "deepseek": {"base_url": "https://api.deepseek.com", "key_env": "DEEPSEEK_API_KEY",
                 "model": "deepseek-chat"},
    "openai": {"base_url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY",
               "model": "gpt-4o-mini"},
    "qwen": {"base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
             "key_env": "DASHSCOPE_API_KEY", "model": "qwen-plus"},
    "ollama": {"base_url": "http://localhost:11434/v1", "key_env": None, "model": "llama3.1"},
}


class LLMError(RuntimeError):
    pass


@dataclass
class LLMClient:
    base_url: str
    model: str
    api_key: Optional[str] = None
    timeout: int = 90
    max_retries: int = 3

    @classmethod
    def from_provider(cls, provider: str, model: Optional[str] = None,
                      base_url: Optional[str] = None) -> "LLMClient":
        if provider not in PROVIDERS:
            raise LLMError(f"Unknown provider '{provider}'. Choose from: {', '.join(PROVIDERS)}")
        preset = PROVIDERS[provider]
        key = None
        if preset["key_env"]:
            key = (os.environ.get(preset["key_env"]) or "").strip() or None
            if not key:
                raise LLMError(f"Set the {preset['key_env']} environment variable to use {provider}.")
        return cls(base_url=(base_url or preset["base_url"]).rstrip("/"),
                   model=model or preset["model"], api_key=key)

    def chat_json(self, prompt: str, temperature: float = 0.0) -> dict:
        """Send one prompt, get back a parsed JSON object. Retries on rate limits and server errors."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {"model": self.model, "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"}}

        last_error = ""
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(f"{self.base_url}/chat/completions",
                                     headers=headers, json=body, timeout=self.timeout)
            except requests.RequestException as e:
                last_error = f"network error: {e}"
                time.sleep(2 ** attempt)
                continue
            if resp.status_code == 401:
                raise LLMError("API key rejected (401). Check the key has no spaces or line breaks.")
            if resp.status_code == 402:
                raise LLMError("Account balance too low (402). Top up with your LLM provider.")
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                time.sleep(2 ** attempt)
                continue
            if resp.status_code >= 400:
                raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            text = resp.json()["choices"][0]["message"]["content"]
            return parse_json(text)
        raise LLMError(f"LLM request failed after {self.max_retries} tries ({last_error}).")


def parse_json(text: str) -> dict:
    """Parse a JSON object, tolerating ```json fences that some models add."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"Model did not return JSON: {text[:120]}")
    return json.loads(text[start:end + 1])
