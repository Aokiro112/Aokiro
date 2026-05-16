"""
Architect-JS Core Engine — JS Bridge
Python ↔ Node.js interop for AST compression pipeline.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..logger import get_logger

logger = get_logger("js_bridge")

# Resolve project root (core_engine/ is one level deep)
PROJECT_ROOT = Path(__file__).parent.parent.parent
ANALYZER_DIR = PROJECT_ROOT / "src" / "analyzer"
AST_COMPRESSOR = ANALYZER_DIR / "ast_compressor.js"
BABEL_VALIDATOR = ANALYZER_DIR / "babel_validator.js"


def _run_node_script(
    script_path: Path, *args: str, cwd: Optional[Path] = None, timeout: int = 30
) -> Tuple[bool, str, str]:
    """
    Run a Node.js script with given arguments.
    Returns: (success: bool, stdout: str, stderr: str)
    """
    cmd = ["node", str(script_path), *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd or PROJECT_ROOT),
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        logger.error(f"Node script timed out: {script_path}")
        return False, "", "Timeout"
    except FileNotFoundError:
        logger.error("node binary not found in PATH")
        return False, "", "node not found"
    except Exception as e:
        logger.error(f"Error running node script: {e}")
        return False, "", str(e)


def compress_file(file_path: str | Path, token_limit: int = 3500) -> Optional[Dict[str, Any]]:
    """
    Compress a React/TSX/JS file into a minimal AST JSON using the Babel pipeline.

    Args:
        file_path: Absolute path to the source file.
        token_limit: Maximum token limit for the output JSON.

    Returns:
        Parsed AST dictionary, or None if compression failed.
    """
    fp = Path(file_path).resolve()
    if not fp.exists():
        logger.error(f"File not found: {fp}")
        return None

    if not AST_COMPRESSOR.exists():
        logger.error(f"ast_compressor.js not found at {AST_COMPRESSOR}")
        return None

    success, stdout, stderr = _run_node_script(
        AST_COMPRESSOR,
        str(fp),
        "--limit", str(token_limit),
        cwd=PROJECT_ROOT,
    )

    if not success:
        logger.warning(f"AST compression failed for {fp.name}: {stderr}")
        return None

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AST JSON output: {e}")
        return None


def validate_syntax(file_path: str | Path) -> bool:
    """
    Validate JS/TS syntax using Babel parser.
    Returns True if the file is syntactically valid.
    """
    fp = Path(file_path).resolve()
    if not fp.exists():
        return False

    if not BABEL_VALIDATOR.exists():
        logger.warning("babel_validator.js not found, skipping syntax check")
        return True  # Permissive fallback

    success, stdout, _ = _run_node_script(BABEL_VALIDATOR, str(fp), cwd=PROJECT_ROOT)
    return success and stdout.strip().upper() == "VALID"


def compress_code_string(code: str, filename: str = "component.tsx", token_limit: int = 3500) -> Optional[Dict[str, Any]]:
    """
    Compress an in-memory code string by writing to a temp file first.
    """
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=Path(filename).suffix or ".tsx",
        delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        return compress_file(tmp_path, token_limit)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
