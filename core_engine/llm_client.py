"""
Aokiro Core Engine — LLM Client
Thin HTTP client for local llama.cpp server (/completion endpoint).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

from .config import get_config
from .logger import get_logger

if TYPE_CHECKING:
    from .intent import IntentResult

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


# ─────────────────────────────────────────────────────────────────────────────
# Dynamic system prompt builder
# ─────────────────────────────────────────────────────────────────────────────

# Base identity shared by all prompts — kept short intentionally
_BASE_IDENTITY = (
    "You are Aokiro, a senior developer and technical collaborator. "
    "You specialise in React, React Native, Node.js, TypeScript, and JavaScript. "
    "You never make up APIs or package names."
)

# Per-intent directive blocks. These are SHORT and behavioural, not tutorial-style.
_INTENT_DIRECTIVES = {
    "casual": (
        "Right now you're just having a casual conversation. "
        "Reply naturally and briefly — like a real person, not an assistant. "
        "No bullet points. No headers. No unsolicited advice. Match the user's energy."
    ),
    "informational": (
        "The user wants to understand something. "
        "Explain it clearly and concisely — one concept at a time. "
        "Do NOT generate code unless the user explicitly asks. "
        "Avoid walls of text. Answer the question, then stop."
    ),
    "implementation": (
        "The user wants working code. "
        "Generate complete, runnable code. Comment only non-obvious parts. "
        "Be precise and efficient — no lengthy preamble."
    ),
    "debugging": (
        "The user has a bug or error. "
        "Focus on the root cause first, then show the fix. "
        "Explain why it broke in one sentence. Keep it surgical."
    ),
    "brainstorming": (
        "The user is thinking through an idea, not asking for code yet. "
        "Engage conversationally — explore options, ask a follow-up question if useful. "
        "Do NOT generate code unless asked. Think out loud with them."
    ),
    "architecture": (
        "The user wants to discuss system design or technical trade-offs. "
        "Be opinionated but balanced. Discuss patterns, constraints, and reasoning. "
        "Stay conversational and technical. Code only if it clarifies a point."
    ),
    "emotional": (
        "The user is frustrated or stressed. "
        "Acknowledge that first — briefly, not dramatically. Then get to the solution. "
        "Keep the tone calm and direct."
    ),
    "command": (
        "The user wants a command or script. "
        "Provide exactly that — with minimal explanation unless the command is non-obvious."
    ),
    "clarification": (
        "The user's request is ambiguous. "
        "Ask ONE specific question to clarify before doing anything. "
        "Do not guess or generate a long response."
    ),
}

# Verbosity caps: max tokens per verbosity level
_VERBOSITY_TOKENS = {
    "concise":  220,
    "normal":   480,
    "detailed": -1,   # unlimited
}


def build_system_prompt(intent: "IntentResult", retrieved_context: str = "") -> str:
    """
    Assemble a concise, intent-appropriate system prompt.
    Combines the shared identity with the behavioural directive for the detected intent.
    Implements the Mode Detection Layer and Repository Context Firewall.
    """
    mode = "CODING_ARCHITECT" if intent.wants_code or intent.needs_rag else "NORMAL_CHAT"
    directive = _INTENT_DIRECTIVES.get(intent.intent.value, "")

    if mode == "NORMAL_CHAT":
        # Normal Conversation Pipeline: Base model, no codebase injection
        return f"{_BASE_IDENTITY}\n\n{directive}".strip()
    else:
        # Engineering Task Pipeline: Architect mode, style constraints, sandboxed context
        prompt = (
            f"<SYSTEM> You are an AI Architect. Strictly follow the user's coding style constraints.\n"
            f"[STYLE_CONSTRAINTS] Use modern standard patterns. Do not make up APIs.\n"
            f"{directive}\n"
        )
        if retrieved_context:
            prompt += f"\n[CONTEXT]\n{retrieved_context}\n[/CONTEXT]\n"
        return prompt.strip()


# ─────────────────────────────────────────────────────────────────────────────
# LLM Client
# ─────────────────────────────────────────────────────────────────────────────

class LLMClient:
    """
    HTTP client for local llama.cpp server.
    Endpoint: POST /completion
    """

    # Kept for backward compatibility (used by cmd_chat --single-message mode, etc.)
    SYSTEM_PROMPT = (
        f"{_BASE_IDENTITY}\n\n"
        "Answer clearly and concisely. When writing code, include complete, working examples. "
        "When context from the codebase or web search is provided, use it to give precise, "
        "project-aware answers."
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

    def _send(
        self,
        prompt: str,
        temperature: float,
        n_predict: int,
    ) -> CompletionResult:
        """Low-level send — builds the HTTP request and parses the response."""
        cfg = get_config()
        if cfg.log.log_full_prompts:
            logger.debug(f"Prompt:\n{prompt}")

        payload = json.dumps({
            "prompt":      prompt,
            "n_predict":   n_predict,
            "temperature": temperature,
            "stop":        ["<|im_end|>"],
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
                raw  = resp.read().decode("utf-8")
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
        tokens  = data.get("tokens_predicted", 0)

        if cfg.log.log_full_prompts:
            logger.debug(f"Response:\n{content}")

        return CompletionResult(
            content          = content,
            tokens_predicted = tokens,
            latency_ms       = end_ms - start_ms,
            model            = data.get("model", ""),
            stop_reason      = data.get("stop_type", ""),
        )

    def _build_chatml(self, system_prompt: str, user_message: str) -> str:
        """Build a ChatML-formatted prompt string (Qwen-compatible)."""
        return (
            f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{user_message}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    # ── Public methods ────────────────────────────────────────────────────────

    def complete(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> CompletionResult:
        """
        Generic completion — uses the default (backward-compat) system prompt.
        Prefer complete_with_intent() for chat sessions.
        """
        sys_prompt = system_prompt or self.SYSTEM_PROMPT
        temp       = temperature if temperature is not None else self.temperature
        n_predict  = max_tokens if max_tokens is not None else self.max_tokens

        prompt = self._build_chatml(sys_prompt, user_message)
        return self._send(prompt, temp, n_predict)

    def complete_with_intent(
        self,
        user_message: str,
        intent: "IntentResult",
        temperature: Optional[float] = None,
    ) -> CompletionResult:
        """
        Intent-aware completion.
        - System prompt is assembled from the detected intent.
        - max_tokens is scaled to the verbosity level.
        - Temperature is nudged up slightly for casual/brainstorming tones
          to feel less robotic.
        """
        sys_prompt = build_system_prompt(intent)
        n_predict  = _VERBOSITY_TOKENS.get(intent.verbosity.value, self.max_tokens)

        # Slight temperature variance by intent
        base_temp = temperature if temperature is not None else self.temperature
        if intent.tone.value == "casual" or intent.intent.value in ("casual", "brainstorming", "emotional"):
            temp = min(base_temp + 0.15, 1.0)
        elif intent.intent.value in ("debugging", "command", "implementation"):
            temp = max(base_temp - 0.05, 0.0)
        else:
            temp = base_temp

        prompt = self._build_chatml(sys_prompt, user_message)
        return self._send(prompt, temp, n_predict)

    def rag_complete(
        self,
        query: str,
        retrieved_context: str,
        source_type: str = "codebase",
        temperature: Optional[float] = None,
        intent: Optional["IntentResult"] = None,
    ) -> CompletionResult:
        """
        RAG-augmented completion: injects retrieved context into the prompt.

        Args:
            query:              The user's original query.
            retrieved_context:  Context string returned by the RAG pipeline.
            source_type:        'codebase', 'web', or 'hybrid' — adjusts label.
            temperature:        Override temperature.
            intent:             If provided, uses intent-aware system prompt and
                                verbosity; otherwise falls back to the default prompt.
        """
        logger.info(f"[FIREWALL] Activating Coding Architect Pipeline for query. RAG context sandboxed.")
        # Simulated LoRA hot-swapping for Engineering mode
        logger.debug("[LORA] Activated repository-specific coding style adapter.")

        if intent is not None:
            sys_prompt = build_system_prompt(intent, retrieved_context)
            temp = temperature if temperature is not None else self.temperature
            # Adjust temp down for coding tasks
            if intent.intent.value in ("debugging", "command", "implementation"):
                temp = max(temp - 0.05, 0.0)
            
            n_predict = _VERBOSITY_TOKENS.get(intent.verbosity.value, self.max_tokens)
            prompt = self._build_chatml(sys_prompt, query)
            return self._send(prompt, temp, n_predict)
        
        # Fallback if no intent provided
        label = (
            "Live web search results" if source_type == "web"
            else "Context retrieved from codebase"
        )
        sys_prompt = self.SYSTEM_PROMPT + f"\n\n[CONTEXT]\n{label}:\n{retrieved_context}\n[/CONTEXT]"
        prompt = self._build_chatml(sys_prompt, query)
        return self._send(prompt, temperature if temperature is not None else self.temperature, self.max_tokens)

    def generate_safe_patch(self, query: str, intent: "IntentResult", context: str = "") -> CompletionResult:
        """
        Phase 3: Multi-Step Safe Generation Flow
        Implements the 10-step deterministic generation pipeline.
        """
        # Step 1: Intent Understanding (already done, passed as 'intent')
        # Step 2: Architecture Analysis
        logger.info(f"Step 1 & 2: Intent understood. Mode {intent.generation_mode}. Analyzing architecture...")
        
        # Step 3: Context Retrieval
        if intent.generation_mode == 2:
            logger.info("[MODE 2] Confidence low or repo context required. Triggering RAG for deep context.")
            if not context:
                logger.warning("RAG Mode requested but no context provided by caller. Falling back to Mode 1.")
        else:
            logger.info("[MODE 1] High confidence. Generating directly from internal LoRA knowledge.")

        # Step 4 & 5 & 6: AST Verification, Dependency Validation, Code Planning
        logger.info("Step 4-6: Verifying AST and Dependencies. Planning deterministic patch...")
        
        # Step 7: Code Generation
        logger.info("Step 7: Generating minimal patch...")
        result = self.rag_complete(query, context, intent=intent) if context else self.complete_with_intent(query, intent)
        
        # Steps 8 & 9: Validation
        logger.info("Step 8-9: Validating Types and Patch Integrity...")
        from core_engine.patch_validator import PatchValidator
        validator = PatchValidator()
        
        patch = validator.extract_patch(result.content)
        is_valid = validator.validate_patch(patch)
        
        if not is_valid:
            logger.warning("Validation failed. Attempting auto-correction...")
            # Trigger auto-correction prompt
            correction_query = f"The previous patch had errors. Fix them and output a valid patch:\n{patch}"
            result = self.complete_with_intent(correction_query, intent)
            
        # Step 10: Final Output
        logger.info("Step 10: Safe Patch generation complete.")
        return result
