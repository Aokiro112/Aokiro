"""
Architect-JS Core Engine — LLM Client
Thin HTTP client for local llama.cpp server (/completion endpoint).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

from .config import get_config
from .logger import get_logger

logger = get_logger("llm_client")


@dataclass
class CompletionResult:
    content: str
    tokens_predicted: int
    latency_ms: int
    model: str = ""
    stop_reason: str = ""


class LlamaServerError(Exception):
    """Raised when the llama.cpp server is unreachable or returns an error."""
    pass


class LLMClient:
    """
    HTTP client for local llama.cpp server.
    Endpoint: POST /completion
    """

    SYSTEM_PROMPT = (
        "You are Architect-JS. You receive compressed AST graphs of React/TypeScript components. "
        "Output your architectural reasoning inside <thought> tags and exact code patches inside <diff> tags. "
        "Do not include any conversational filler outside these tags."
    )

    def __init__(self, base_url: Optional[str] = None):
        cfg = get_config()
        self.base_url = (base_url or cfg.llama.server_url).rstrip("/")
        self.completion_url = f"{self.base_url}/completion"
        self.health_url = f"{self.base_url}/health"
        self.temperature = cfg.llama.temperature
        self.max_tokens = cfg.llama.max_tokens

    def is_alive(self) -> bool:
        """Check if the llama-server is running and healthy."""
        try:
            req = urllib.request.urlopen(self.health_url, timeout=3)
            return req.status == 200
        except Exception:
            return False

    def complete(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> CompletionResult:
        """
        Send a completion request using the ChatML format compatible with Qwen.
        """
        sys_prompt = system_prompt or self.SYSTEM_PROMPT
        temp = temperature if temperature is not None else self.temperature
        n_predict = max_tokens if max_tokens is not None else self.max_tokens

        # Build ChatML prompt
        prompt = (
            f"<|im_start|>system\n{sys_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{user_message}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        cfg = get_config()
        if cfg.log.log_full_prompts:
            logger.debug(f"Prompt:\n{prompt}")

        payload = json.dumps({
            "prompt": prompt,
            "n_predict": n_predict,
            "temperature": temp,
            "stop": ["<|im_end|>"],
        }).encode("utf-8")

        start_ms = int(time.time() * 1000)

        try:
            req = urllib.request.Request(
                self.completion_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
        except urllib.error.URLError as e:
            raise LlamaServerError(
                f"Cannot reach llama-server at {self.completion_url}. "
                f"Is it running? Error: {e}"
            ) from e
        except json.JSONDecodeError as e:
            raise LlamaServerError(f"Invalid JSON response from llama-server: {e}") from e

        end_ms = int(time.time() * 1000)

        content = data.get("content", "")
        tokens = data.get("tokens_predicted", 0)

        if cfg.log.log_full_prompts:
            logger.debug(f"Response:\n{content}")

        return CompletionResult(
            content=content,
            tokens_predicted=tokens,
            latency_ms=end_ms - start_ms,
            model=data.get("model", ""),
            stop_reason=data.get("stop_type", ""),
        )

    def rag_complete(
        self,
        query: str,
        retrieved_context: str,
        temperature: Optional[float] = None,
    ) -> CompletionResult:
        """
        RAG-augmented completion: injects retrieved context into the prompt.
        """
        user_message = (
            f"Context retrieved from codebase:\n"
            f"---\n{retrieved_context}\n---\n\n"
            f"User Query: {query}"
        )
        return self.complete(user_message, temperature=temperature)
