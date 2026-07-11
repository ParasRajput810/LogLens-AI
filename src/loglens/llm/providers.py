from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import List, Dict, Optional


class LLMError(RuntimeError):
    """Raised when the LLM call fails after retries."""

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
    "azure": "",
}


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMConfig:
    provider: str = ""
    api_key: str = ""
    model: str = ""
    # azure-specific
    azure_endpoint: str = ""
    azure_deployment: str = ""
    azure_api_version: str = "2024-06-01"
    # request behaviour
    temperature: float = 0.2
    max_tokens: int = 1200
    timeout: int = 60
    retries: int = 2

    @classmethod
    def from_env(cls, provider: str = "", model: str = "", api_key: str = "") -> "LLMConfig":
        cfg = cls(
            provider=(provider or os.getenv("LOGLENS_LLM_PROVIDER", "")).lower().strip(),
            api_key=api_key or os.getenv("LOGLENS_LLM_API_KEY", ""),
            model=model or os.getenv("LOGLENS_LLM_MODEL", ""),
            azure_endpoint=os.getenv("LOGLENS_AZURE_ENDPOINT", "").rstrip("/"),
            azure_deployment=os.getenv("LOGLENS_AZURE_DEPLOYMENT", ""),
            azure_api_version=os.getenv("LOGLENS_AZURE_API_VERSION", "2024-06-01"),
        )
        if not cfg.provider:
            raise LLMError(
                "No LLM provider configured. Set LOGLENS_LLM_PROVIDER to "
                "'openai', 'azure' or 'groq' (or pass --provider)."
            )
        if cfg.provider not in ("openai", "azure", "groq"):
            raise LLMError(f"Unknown provider '{cfg.provider}'. Use openai | azure | groq.")
        if not cfg.api_key:
            raise LLMError("Missing API key. Set LOGLENS_LLM_API_KEY (or pass --api-key).")
        if not cfg.model:
            cfg.model = DEFAULT_MODELS[cfg.provider]
        if cfg.provider == "azure":
            if not cfg.azure_endpoint:
                raise LLMError("Azure requires LOGLENS_AZURE_ENDPOINT (https://<resource>.openai.azure.com).")
            if not cfg.azure_deployment:
                cfg.azure_deployment = cfg.model
            if not cfg.azure_deployment:
                raise LLMError("Azure requires LOGLENS_AZURE_DEPLOYMENT (or LOGLENS_LLM_MODEL).")
            if not cfg.model:
                # for display purposes — azure model comes from the deployment path
                cfg.model = cfg.azure_deployment
        return cfg


class LLMClient:

    def __init__(self, config: LLMConfig):
        self.config = config
        self.last_usage = TokenUsage()

    def _endpoint(self) -> str:
        c = self.config
        if c.provider == "openai":
            return "https://api.openai.com/v1/chat/completions"
        if c.provider == "groq":
            return "https://api.groq.com/openai/v1/chat/completions"
        # azure
        return (
            f"{c.azure_endpoint}/openai/deployments/{c.azure_deployment}"
            f"/chat/completions?api-version={c.azure_api_version}"
        )

    def _headers(self) -> Dict[str, str]:
        c = self.config
        h = {"Content-Type": "application/json"}
        if c.provider == "azure":
            h["api-key"] = c.api_key
        else:
            h["Authorization"] = f"Bearer {c.api_key}"
        return h

    def chat(self, messages: List[Dict[str, str]]) -> str:
        c = self.config
        payload: Dict = {
            "messages": messages,
            "temperature": c.temperature,
            "max_tokens": c.max_tokens,
        }
        if c.provider != "azure":
            payload["model"] = c.model

        body = json.dumps(payload).encode("utf-8")
        last_err: Optional[Exception] = None
        for attempt in range(c.retries + 1):
            try:
                req = urllib.request.Request(
                    self._endpoint(), data=body, headers=self._headers(), method="POST"
                )
                with urllib.request.urlopen(req, timeout=c.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                usage = data.get("usage") or {}
                self.last_usage = TokenUsage(
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                )
                return data["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read().decode("utf-8")[:400]
                except Exception:
                    pass
                if e.code == 401:
                    raise LLMError(f"[{c.provider}] Invalid API key (401). {detail}")
                if e.code == 404 and c.provider == "azure":
                    raise LLMError(
                        f"[azure] 404 — check endpoint/deployment name "
                        f"('{c.azure_deployment}') and api-version. {detail}"
                    )
                if e.code == 429 and attempt < c.retries:
                    time.sleep(2 ** attempt)  # backoff and retry
                    last_err = e
                    continue
                raise LLMError(f"[{c.provider}] HTTP {e.code}: {detail}")
            except Exception as e:
                last_err = e
                if attempt < c.retries:
                    time.sleep(2 ** attempt)
                    continue
        raise LLMError(f"[{self.config.provider}] request failed after retries: {last_err}")