"""
Architect-JS Core Engine — Configuration
Loads and validates environment variables from .env
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Load .env file if present
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(_env_path)
except ImportError:
    pass  # dotenv not installed, rely on real env vars


@dataclass(frozen=True)
class LlamaConfig:
    server_url: str = field(default_factory=lambda: os.getenv("LLAMA_SERVER_URL", "http://localhost:8080"))
    port: int = field(default_factory=lambda: int(os.getenv("LLAMA_SERVER_PORT", "8080")))
    model_path: str = field(default_factory=lambda: os.getenv("LLAMA_MODEL_PATH", "models/architect-js-1.5b-unsloth.Q4_K_M.gguf"))
    temperature: float = field(default_factory=lambda: float(os.getenv("LLAMA_TEMPERATURE", "0.1")))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("LLAMA_MAX_TOKENS", "-1")))
    context_size: int = field(default_factory=lambda: int(os.getenv("LLAMA_CONTEXT_SIZE", "2048")))


@dataclass(frozen=True)
class RagConfig:
    collection_name: str = field(default_factory=lambda: os.getenv("RAG_COLLECTION_NAME", "architect_js_codebase"))
    db_path: str = field(default_factory=lambda: os.getenv("RAG_DB_PATH", "./data/rag_db"))
    embedding_model: str = field(default_factory=lambda: os.getenv("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2"))
    top_k: int = field(default_factory=lambda: int(os.getenv("RAG_TOP_K", "5")))
    chunk_size: int = field(default_factory=lambda: int(os.getenv("RAG_CHUNK_SIZE", "512")))
    chunk_overlap: int = field(default_factory=lambda: int(os.getenv("RAG_CHUNK_OVERLAP", "50")))


@dataclass(frozen=True)
class LogConfig:
    level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    log_file: str = field(default_factory=lambda: os.getenv("LOG_FILE", "./logs/architect_js.log"))
    log_full_prompts: bool = field(default_factory=lambda: os.getenv("LOG_FULL_PROMPTS", "false").lower() == "true")


@dataclass(frozen=True)
class DataConfig:
    data_dir: str = field(default_factory=lambda: os.getenv("DATA_DIR", "./data"))
    datasets_dir: str = field(default_factory=lambda: os.getenv("DATASETS_DIR", "./datasets"))
    repos_dir: str = field(default_factory=lambda: os.getenv("REPOS_DIR", "./workspace/repos"))
    train_file: str = field(default_factory=lambda: os.getenv("TRAIN_FILE", "./data/train.jsonl"))
    manual_fixes_file: str = field(default_factory=lambda: os.getenv("MANUAL_FIXES_FILE", "./data/manual_fixes.json"))
    unseen_test_file: str = field(default_factory=lambda: os.getenv("UNSEEN_TEST_FILE", "./data/unseen_test.json"))
    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    hf_token: str = field(default_factory=lambda: os.getenv("HF_TOKEN", ""))


@dataclass(frozen=True)
class WebSearchConfig:
    enabled: bool = field(default_factory=lambda: os.getenv("WEB_SEARCH_ENABLED", "true").lower() == "true")
    google_api_key: str = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY", ""))
    google_cse_id: str = field(default_factory=lambda: os.getenv("GOOGLE_CSE_ID", ""))
    max_results: int = field(default_factory=lambda: int(os.getenv("WEB_SEARCH_MAX_RESULTS", "4")))
    # Minimum local similarity score below which web search kicks in (0.0–1.0)
    fallback_threshold: float = field(default_factory=lambda: float(os.getenv("WEB_SEARCH_FALLBACK_THRESHOLD", "0.45")))


@dataclass(frozen=True)
class Config:
    llama: LlamaConfig = field(default_factory=LlamaConfig)
    rag: RagConfig = field(default_factory=RagConfig)
    log: LogConfig = field(default_factory=LogConfig)
    data: DataConfig = field(default_factory=DataConfig)
    web_search: WebSearchConfig = field(default_factory=WebSearchConfig)

    @property
    def completion_endpoint(self) -> str:
        return f"{self.llama.server_url}/completion"

    @property
    def health_endpoint(self) -> str:
        return f"{self.llama.server_url}/health"


# Singleton config instance
_config: Config | None = None


def get_config() -> Config:
    """Returns the singleton config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
