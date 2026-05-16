"""
Aokiro Core Engine — Full Terminal CLI
Interactive menu system for all core functions.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Fix Windows console encoding issues before any rich imports
if sys.platform == "win32":
    import io
    # Force UTF-8 output encoding for the terminal
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.environ["PYTHONIOENCODING"] = "utf-8"

# Ensure core_engine is importable when run directly
_ENGINE_ROOT = Path(__file__).parent
_PROJECT_ROOT = _ENGINE_ROOT.parent
sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import click
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn
    from rich.prompt import Confirm, Prompt
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("[ERROR] Required packages missing. Run: pip install rich click")
    print("        Or run setup.bat (Windows) / setup.sh (Linux/macOS)")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Console & Globals
# ─────────────────────────────────────────────────────────────────────────────

# Force rich to use markup/ANSI instead of Windows legacy console API
console = Console(force_terminal=True, markup=True, highlight=True)

BANNER = r"""
    ___              __    _ __           __        _______
   /   |  __________/ /_  (_) /____  ____/ /_      / / ___/
  / /| | / ___/ ___/ __ \/ / __/ _ \/ __/ __/_____/ /\__ \
 / ___ |/ /  / /__/ / / / / /_/  __/ /_/ /_/_____/ /___/ /
/_/  |_/_/   \___/_/ /_/_/\__/\___/\__/\__/     /_//____/

  Local-First AI Architect  •  AST Compression  •  RAG Pipeline
"""


def print_banner():
    console.print(Panel(
        Text(BANNER, style="bold cyan", justify="center"),
        border_style="cyan",
        padding=(0, 2),
    ))


def print_status(message: str, status: str = "info"):
    styles = {"info": "blue", "ok": "green", "warn": "yellow", "error": "red"}
    icons = {"info": "ℹ", "ok": "✓", "warn": "⚠", "error": "✗"}
    style = styles.get(status, "white")
    icon = icons.get(status, "•")
    console.print(f"  [{style}]{icon}[/{style}]  {message}")


# ─────────────────────────────────────────────────────────────────────────────
# Logger
# ─────────────────────────────────────────────────────────────────────────────

from core_engine.logger import get_logger
logger = get_logger("main")

# ─────────────────────────────────────────────────────────────────────────────
# Lazy imports (avoid slow startup)
# ─────────────────────────────────────────────────────────────────────────────

def _get_config():
    from core_engine.config import get_config
    return get_config()


def _get_rag():
    from core_engine.rag.pipeline import RagPipeline
    return RagPipeline()


def _get_llm():
    from core_engine.llm_client import LLMClient, LlamaServerError
    return LLMClient(), LlamaServerError


# ─────────────────────────────────────────────────────────────────────────────
# Interactive Menu Helpers
# ─────────────────────────────────────────────────────────────────────────────

def check_llama_server() -> bool:
    """Check if llama-server is alive."""
    try:
        from core_engine.llm_client import LLMClient
        client = LLMClient()
        return client.is_alive()
    except Exception:
        return False


def check_rag_status() -> dict:
    """Get RAG index status."""
    try:
        rag = _get_rag()
        return rag.get_status()
    except Exception as e:
        return {"status": "error", "error": str(e)}


def render_status_panel():
    """Render a status overview panel."""
    cfg = _get_config()
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    llama_alive = check_llama_server()
    llm_status = "[green]● Online[/green]" if llama_alive else "[red]● Offline[/red]"
    table.add_row("LLM Server", f"{llm_status}  ({cfg.llama.server_url})")

    rag_info = check_rag_status()
    rag_count = rag_info.get("total_chunks", 0)
    rag_sources = rag_info.get("unique_sources", 0)
    rag_status = "[green]● Ready[/green]" if rag_count > 0 else "[yellow]● Empty[/yellow]"
    table.add_row("RAG Index", f"{rag_status}  ({rag_count} chunks, {rag_sources} files)")

    table.add_row("Model", cfg.llama.model_path)
    table.add_row("Embedding", cfg.rag.embedding_model)

    console.print(Panel(table, title="[bold]System Status[/bold]", border_style="dim"))


# ─────────────────────────────────────────────────────────────────────────────
# Core Commands
# ─────────────────────────────────────────────────────────────────────────────

def cmd_chat():
    """Interactive chat mode with the local LLM."""
    console.print("  [bold cyan]Aokiro[/bold cyan]  [dim]— type [bold]exit[/bold] to quit[/dim]\n")

    if not check_llama_server():
        console.print(
            "  [yellow]⚠  llama-server is not running.[/yellow] "
            "Start it with: [bold cyan].\\llama-server.exe -m models\\qwen2.5-coder-1.5b-instruct-q4_k_m.gguf -c 2048 --port 8080[/bold cyan]\n"
        )
        if not Confirm.ask("  Continue anyway (for testing)?", default=False):
            return

    from core_engine.llm_client import LLMClient, LlamaServerError
    from core_engine.rag.pipeline import RagPipeline
    from core_engine.intent import classify_intent, HistoryTurn

    client = LLMClient()
    rag = RagPipeline()

    # Conversation history buffer — used ONLY by the intent classifier.
    # Capped at 6 turns to bound memory usage. NOT injected into LLM prompts.
    conv_history: list = []  # list[HistoryTurn]
    _MAX_HISTORY = 6

    while True:
        try:
            user_input = Prompt.ask("\n  [bold green]You[/bold green]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print()
            break

        if user_input.lower() in {"exit", "quit", "q", ":q"}:
            break

        if not user_input:
            continue

        # ── 1. Classify intent ────────────────────────────────────────────────
        intent = classify_intent(user_input, conv_history)
        logger.debug(
            f"Intent: {intent.intent.value} | tone={intent.tone.value} "
            f"| depth={intent.depth.value} | wants_code={intent.wants_code} "
            f"| needs_rag={intent.needs_rag} | verbosity={intent.verbosity.value} "
            f"| scores={intent.scores}"
        )

        # ── 2. Conditionally retrieve context ─────────────────────────────────
        context = ""
        source_type = "none"

        if intent.needs_rag:
            with console.status("[dim]Searching context...[/dim]", spinner="dots"):
                chunks, context = rag.retrieve(user_input)
                source_type = getattr(rag, "_last_source_type", "codebase")

        # ── 3. Generate response ──────────────────────────────────────────────
        with console.status("[dim]Thinking...[/dim]", spinner="dots"):
            try:
                if context:
                    result = client.rag_complete(
                        user_input, context,
                        source_type=source_type,
                        intent=intent,
                    )
                else:
                    result = client.complete_with_intent(user_input, intent)
                    source_type = "none"
            except LlamaServerError as e:
                console.print(f"\n  [red]Error:[/red] {e}")
                continue

        # ── 4. Update conversation history for next turn's classifier ─────────
        conv_history.append(HistoryTurn(
            role="user",
            content=user_input,
            intent=intent.intent,
            tone=intent.tone,
        ))
        conv_history.append(HistoryTurn(role="assistant", content=result.content))
        if len(conv_history) > _MAX_HISTORY * 2:
            conv_history = conv_history[-(  _MAX_HISTORY * 2):]

        # ── 5. Render ─────────────────────────────────────────────────────────
        source_icon = {
            "web":     " [cyan]\U0001f310 web[/cyan]",
            "hybrid":  " [cyan]\U0001f310+\U0001f4c1 hybrid[/cyan]",
            "codebase": " [dim]\U0001f4c1 local[/dim]",
        }.get(source_type, "")

        console.print()
        console.print(Panel(
            result.content,
            title=(
                f"[bold blue]Aokiro[/bold blue]{source_icon}  "
                f"[dim]({result.latency_ms}ms | {result.tokens_predicted} tokens)[/dim]"
            ),
            border_style="blue",
            padding=(1, 2),
        ))


def cmd_rag_query(query: Optional[str] = None):
    """RAG-augmented query with context injection."""
    console.rule("[bold magenta]RAG Query Mode[/bold magenta]")

    rag = _get_rag()
    status = rag.get_status()

    if status.get("total_chunks", 0) == 0:
        console.print(Panel(
            "[yellow]RAG index is empty.[/yellow]\n\n"
            "Index your codebase first:\n"
            "[bold cyan]  python core_engine/main.py index --path ./src[/bold cyan]",
            title="⚠  Index Empty",
            border_style="yellow",
        ))
        return

    if not query:
        try:
            query = Prompt.ask("\n  [bold magenta]Query[/bold magenta]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print()
            return

    if not query:
        return

    with console.status("[magenta]Retrieving context...[/magenta]", spinner="dots"):
        chunks, context = rag.retrieve(query)

    if not chunks:
        console.print("\n  [yellow]No relevant chunks found.[/yellow]")
        return

    # Show retrieved sources
    src_table = Table(title="Retrieved Context", box=box.ROUNDED, show_lines=True)
    src_table.add_column("#", style="dim", width=3)
    src_table.add_column("Source", style="cyan")
    src_table.add_column("Language", style="green")
    src_table.add_column("Similarity", justify="right")

    for i, chunk in enumerate(chunks, 1):
        src_table.add_row(
            str(i),
            chunk.source_ref,
            chunk.language,
            f"{chunk.similarity:.3f}",
        )
    console.print(src_table)

    if not check_llama_server():
        console.print("\n  [yellow]LLM server offline — showing retrieved context only.[/yellow]")
        console.print(Panel(context, title="Retrieved Context", border_style="dim"))
        return

    with console.status("[cyan]Generating answer with context...[/cyan]", spinner="dots"):
        from core_engine.llm_client import LLMClient, LlamaServerError
        client = LLMClient()
        source_type = getattr(rag, "_last_source_type", "codebase")
        try:
            result = client.rag_complete(query, context, source_type=source_type)
        except LlamaServerError as e:
            console.print(f"\n  [red]LLM Error:[/red] {e}")
            return

    console.print()
    console.print(Panel(
        result.content,
        title=f"[bold blue]Answer[/bold blue]  ({result.latency_ms}ms | {result.tokens_predicted} tokens)",
        border_style="blue",
        padding=(1, 2),
    ))


def cmd_index(path: str):
    """Index a directory or file into the RAG vector store."""
    console.rule("[bold green]Indexing[/bold green]")
    target = Path(path)

    if not target.exists():
        console.print(f"  [red]Path not found:[/red] {target}")
        return

    console.print(f"  Indexing: [cyan]{target.resolve()}[/cyan]")

    rag = _get_rag()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Indexing...", total=100)

        def progress_callback(current, total, message):
            progress.update(task, completed=current, description=message)

        result = rag.index(target, progress_callback=progress_callback)

    console.print()
    summary = Table(box=box.SIMPLE, show_header=False)
    summary.add_column("Key", style="dim")
    summary.add_column("Value", style="bold")
    summary.add_row("Documents processed", str(result.docs_processed))
    summary.add_row("Chunks generated", str(result.chunks_generated))
    summary.add_row("New chunks added", str(result.chunks_added))
    summary.add_row("Duration", f"{result.duration_seconds:.1f}s")
    summary.add_row("Collection", result.collection)
    console.print(Panel(summary, title="[green]✓ Indexing Complete[/green]", border_style="green"))


def cmd_index_status():
    """Show RAG index status."""
    console.rule("[bold]Index Status[/bold]")
    rag = _get_rag()
    info = rag.get_status()

    table = Table(box=box.ROUNDED)
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Status", f"[green]{info.get('status', 'unknown')}[/green]")
    table.add_row("Collection", info.get("collection", "N/A"))
    table.add_row("Database Path", info.get("db_path", "N/A"))
    table.add_row("Total Chunks", str(info.get("total_chunks", 0)))
    table.add_row("Unique Sources", str(info.get("unique_sources", 0)))

    console.print(table)

    sources = info.get("sources", [])
    if sources:
        console.print(f"\n  [dim]Indexed files ({len(sources)}):[/dim]")
        for src in sources[:20]:
            try:
                rel = Path(src).relative_to(Path.cwd())
            except ValueError:
                rel = src
            console.print(f"    [dim]•[/dim] {rel}")
        if len(sources) > 20:
            console.print(f"    [dim]... and {len(sources) - 20} more[/dim]")


def cmd_compress(filepath: str):
    """Compress a React/TSX file into an AST JSON."""
    console.rule("[bold yellow]AST Compression[/bold yellow]")
    fp = Path(filepath)

    if not fp.exists():
        console.print(f"  [red]File not found:[/red] {filepath}")
        return

    from core_engine.tools import compress_file
    with console.status(f"[yellow]Compressing {fp.name}...[/yellow]", spinner="dots"):
        result = compress_file(fp)

    if result is None:
        console.print(f"  [red]Compression failed for {fp.name}[/red]")
        return

    json_str = json.dumps(result, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)
    console.print(Panel(syntax, title=f"[yellow]AST: {fp.name}[/yellow]", border_style="yellow"))


def cmd_logs():
    """Show recent log entries."""
    console.rule("[bold]Logs[/bold]")
    cfg = _get_config()
    log_path = Path(cfg.log.log_file)

    if not log_path.exists():
        console.print(f"  [dim]No log file at {log_path}[/dim]")
        return

    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
        recent = lines[-50:]  # Last 50 lines

        table = Table(box=box.MINIMAL, show_header=False, padding=(0, 1))
        table.add_column("", style="dim", width=8)
        table.add_column("", style="dim", width=8)
        table.add_column("")

        for line in recent:
            parts = line.split(" | ", 3)
            if len(parts) >= 4:
                _, level, _, msg = parts
                style = {"ERROR": "red", "WARNING": "yellow", "INFO": "blue", "DEBUG": "dim"}.get(level.strip(), "")
                table.add_row(parts[0].strip(), f"[{style}]{level.strip()}[/{style}]", msg.strip())
            else:
                table.add_row("", "", line)

        console.print(table)
        console.print(f"  [dim]Log file: {log_path}[/dim]")
    except Exception as e:
        console.print(f"  [red]Error reading logs:[/red] {e}")


def cmd_config():
    """Display current configuration."""
    console.rule("[bold]Configuration[/bold]")
    cfg = _get_config()

    env_path = Path.cwd() / ".env"
    console.print(f"  [dim]Config file: {env_path}[/dim]\n")

    sections = {
        "LLM Server": {
            "URL": cfg.llama.server_url,
            "Temperature": str(cfg.llama.temperature),
            "Max Tokens": str(cfg.llama.max_tokens),
            "Context Size": str(cfg.llama.context_size),
            "Model Path": cfg.llama.model_path,
        },
        "RAG Pipeline": {
            "Collection": cfg.rag.collection_name,
            "DB Path": cfg.rag.db_path,
            "Embedding Model": cfg.rag.embedding_model,
            "Top K": str(cfg.rag.top_k),
            "Chunk Size": str(cfg.rag.chunk_size),
            "Chunk Overlap": str(cfg.rag.chunk_overlap),
        },
        "Logging": {
            "Level": cfg.log.level,
            "Log File": cfg.log.log_file,
            "Log Full Prompts": str(cfg.log.log_full_prompts),
        },
        "Data Paths": {
            "Data Dir": cfg.data.data_dir,
            "Datasets Dir": cfg.data.datasets_dir,
            "Train File": cfg.data.train_file,
        },
    }

    for section_name, items in sections.items():
        table = Table(box=box.SIMPLE, show_header=False, title=f"[bold]{section_name}[/bold]")
        table.add_column("Key", style="dim", width=20)
        table.add_column("Value")
        for k, v in items.items():
            table.add_row(k, v)
        console.print(table)


def interactive_menu():
    """Full interactive TUI menu."""
    print_banner()
    render_status_panel()

    MENU_OPTIONS = [
        ("1", "💬  Chat", "Send messages and AST JSON to the LLM"),
        ("2", "🔍  RAG Query", "Search indexed codebase and get context-aware answers"),
        ("3", "📁  Index Codebase", "Index files/directories into the RAG vector store"),
        ("4", "📊  Index Status", "Show RAG index statistics and indexed files"),
        ("5", "🗜  Compress File", "Compress a React/TSX file to AST JSON"),
        ("6", "📋  View Logs", "Show recent application logs"),
        ("7", "⚙  Config", "View current configuration"),
        ("8", "🔄  Refresh Status", "Refresh system status"),
        ("q", "🚪  Quit", "Exit Aokiro"),
    ]

    while True:
        console.rule("[dim]Main Menu[/dim]")
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        table.add_column("Key", style="bold cyan", width=4)
        table.add_column("Action", style="bold")
        table.add_column("Description", style="dim")

        for key, action, desc in MENU_OPTIONS:
            table.add_row(f"[{key}]", action, desc)

        console.print(table)

        try:
            choice = Prompt.ask("\n  [bold]Select option[/bold]").strip().lower()
        except (KeyboardInterrupt, EOFError):
            console.print("\n  Exiting...")
            break

        console.print()

        if choice == "1":
            cmd_chat()
        elif choice == "2":
            cmd_rag_query()
        elif choice == "3":
            path = Prompt.ask("  [green]Path to index[/green]", default="./src")
            cmd_index(path)
        elif choice == "4":
            cmd_index_status()
        elif choice == "5":
            path = Prompt.ask("  [yellow]File path to compress[/yellow]")
            cmd_compress(path)
        elif choice == "6":
            cmd_logs()
        elif choice == "7":
            cmd_config()
        elif choice == "8":
            render_status_panel()
        elif choice in {"q", "quit", "exit"}:
            console.print("  [cyan]Goodbye![/cyan]")
            break
        else:
            console.print(f"  [dim]Unknown option: {choice}[/dim]")


# ─────────────────────────────────────────────────────────────────────────────
# Click CLI Entry Points
# ─────────────────────────────────────────────────────────────────────────────

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """
    Aokiro — Local-First AI Coding Assistant

    Run without a subcommand to open an interactive chat session.
    """
    if ctx.invoked_subcommand is None:
        cmd_chat()


@cli.command()
@click.option("--path", "-p", default="./src", help="Path to file or directory to index", show_default=True)
@click.option("--reset", is_flag=True, help="Clear existing index before indexing")
def index(path, reset):
    """Index files/directories into the RAG vector store."""
    if reset:
        if Confirm.ask(f"  [yellow]Reset the RAG index before indexing?[/yellow]", default=False):
            rag = _get_rag()
            rag.reset_index()
            console.print("  [green]Index reset.[/green]")
    cmd_index(path)


@cli.command()
@click.argument("query", nargs=-1)
@click.option("--n", "-n", default=5, help="Number of chunks to retrieve", show_default=True)
def query(query, n):
    """Run a RAG query against the indexed codebase."""
    q = " ".join(query) if query else None
    if q:
        rag = _get_rag()
        rag.retriever.top_k = n
        cmd_rag_query(q)
    else:
        cmd_rag_query()


@cli.command()
@click.argument("filepath")
def compress(filepath):
    """Compress a React/TSX file to AST JSON."""
    cmd_compress(filepath)


@cli.command()
@click.argument("message", nargs=-1)
def chat(message):
    """Send a single message to the LLM and print the response."""
    if message:
        msg = " ".join(message)
        from core_engine.llm_client import LLMClient, LlamaServerError
        client = LLMClient()
        with console.status("[cyan]Generating...[/cyan]", spinner="dots"):
            try:
                result = client.complete(msg)
                console.print(result.content)
            except LlamaServerError as e:
                console.print(f"[red]Error:[/red] {e}", err=True)
                sys.exit(1)
    else:
        cmd_chat()


@cli.command()
def status():
    """Show system status (LLM server, RAG index, config)."""
    print_banner()
    render_status_panel()
    cmd_index_status()


@cli.command()
def config():
    """Display current configuration."""
    cmd_config()


@cli.command()
@click.option("--lines", "-n", default=50, help="Number of log lines to show", show_default=True)
def logs(lines):
    """Show recent application logs."""
    cmd_logs()


@cli.command("reset-index")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
def reset_index(yes):
    """Delete and recreate the RAG vector store collection."""
    if not yes:
        if not Confirm.ask("[yellow]This will delete all indexed data. Continue?[/yellow]", default=False):
            return
    rag = _get_rag()
    rag.reset_index()
    console.print("[green]✓ RAG index has been reset.[/green]")


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
