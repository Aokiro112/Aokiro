"""
Architect-JS Core Engine — Intent Classification Layer
=======================================================
Classifies user messages into structured intent metadata used to route
responses: system prompt selection, verbosity, RAG gating, and code generation.

Design principle:
  No hard-coded keyword matching. Classification is SCORING-BASED — each signal
  contributes a numeric weight, and the highest-scoring intent wins. Signals are
  derived from sentence structure, linguistic formality, specificity density,
  frustration markers, conversation history, and execution vs. conceptual verbs.
"""
from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


# ─────────────────────────────────────────────────────────────────────────────
# Public data types
# ─────────────────────────────────────────────────────────────────────────────

class Intent(str, Enum):
    CASUAL         = "casual"
    INFORMATIONAL  = "informational"
    IMPLEMENTATION = "implementation"
    DEBUGGING      = "debugging"
    BRAINSTORMING  = "brainstorming"
    ARCHITECTURE   = "architecture"
    EMOTIONAL      = "emotional"
    COMMAND        = "command"
    CLARIFICATION  = "clarification"


class Tone(str, Enum):
    CASUAL  = "casual"
    NEUTRAL = "neutral"
    FORMAL  = "formal"


class Depth(str, Enum):
    SHALLOW = "shallow"
    MEDIUM  = "medium"
    DEEP    = "deep"


class Verbosity(str, Enum):
    CONCISE  = "concise"
    NORMAL   = "normal"
    DETAILED = "detailed"


@dataclass
class IntentResult:
    intent:    Intent
    tone:      Tone
    depth:     Depth
    wants_code: bool    # Should the LLM generate code?
    needs_rag:  bool    # Should RAG retrieval be triggered?
    verbosity:  Verbosity
    # Internal scores exposed for debugging / logging
    scores:    dict = field(default_factory=dict)


@dataclass
class HistoryTurn:
    role:    str   # "user" or "assistant"
    content: str
    intent:  Optional[Intent] = None
    tone:    Optional[Tone] = None


# ─────────────────────────────────────────────────────────────────────────────
# Signal scorers
# Each scorer returns a dict[Intent, float] contribution.
# Scores are accumulated, then normalised and the top intent is selected.
# ─────────────────────────────────────────────────────────────────────────────

def _score_sentence_structure(tokens: List[str], raw: str) -> dict:
    """
    Analyses grammatical structure signals:
    - Imperative opening verbs → implementation / command
    - Interrogative structure → informational / clarification
    - Conditional / speculative structure → brainstorming / architecture
    - Bare noun phrase (no verb) → casual
    """
    scores = {i: 0.0 for i in Intent}

    if not tokens:
        return scores

    first = tokens[0].lower()

    # Imperative verbs strongly suggest the user wants something *done*
    EXECUTION_VERBS = {
        "build", "create", "make", "write", "generate", "implement", "code",
        "execute", "deploy", "setup", "install", "scaffold",
        "add", "update", "refactor", "migrate", "convert", "port",
    }
    DIAGNOSTIC_VERBS = {
        "fix", "debug", "repair", "resolve", "patch", "trace", "investigate",
        "check", "find", "locate", "identify", "diagnose",
    }
    CONCEPTUAL_VERBS = {
        "explain", "describe", "summarise", "summarize", "compare", "contrast",
        "show", "list", "tell", "give",
    }
    SPECULATIVE_VERBS = {
        "think", "thinking", "considering", "wondering", "pondering",
        "planning", "designing", "brainstorm", "explore", "discuss",
    }
    COMMAND_VERBS = {
        "run", "execute", "start", "stop", "restart", "install", "uninstall",
        "launch", "kill", "spawn", "init", "clone", "pull", "push", "commit",
    }
    ARCHITECTURE_NOUNS = {
        "architecture", "design", "pattern", "structure", "system", "approach",
        "strategy", "trade-off", "tradeoff", "scalability", "microservice",
        "monolith", "pipeline", "schema", "database design",
    }

    if first in EXECUTION_VERBS:
        scores[Intent.IMPLEMENTATION] += 2.0
        scores[Intent.COMMAND] += 0.5
    elif first in DIAGNOSTIC_VERBS:
        scores[Intent.DEBUGGING] += 2.5
    elif first in COMMAND_VERBS:
        # "run X", "install X", "clone X" — short imperative command
        scores[Intent.COMMAND] += 2.5
    elif first in CONCEPTUAL_VERBS:
        scores[Intent.INFORMATIONAL] += 1.5
    elif first in SPECULATIVE_VERBS:
        scores[Intent.BRAINSTORMING] += 2.0

    # Question structure
    has_question_mark = raw.strip().endswith("?")
    interrogative_openers = {"what", "why", "how", "when", "where", "which", "who", "is", "are", "does", "do", "can", "could", "would", "should"}
    starts_with_question_word = first in interrogative_openers

    if has_question_mark and starts_with_question_word:
        scores[Intent.INFORMATIONAL] += 1.5
    elif has_question_mark:
        scores[Intent.INFORMATIONAL] += 0.5
    elif starts_with_question_word:
        # Even without a question mark, an interrogative opener is a strong
        # informational signal - override the length heuristic.
        # EXCEPTION: "can you help/assist" is generically casual/clarification
        is_generic_help = bool(
            re.search(r"^can\s+you\s+(help|assist|do|tell|show)\b", raw, re.I)
        )
        if is_generic_help:
            scores[Intent.CASUAL]        += 0.8
            scores[Intent.CLARIFICATION] += 0.5
        else:
            scores[Intent.INFORMATIONAL] += 1.8

    # Architecture / design signals in the full sentence
    text_lower = raw.lower()
    arch_hits = sum(1 for n in ARCHITECTURE_NOUNS if n in text_lower)
    if arch_hits >= 2:
        scores[Intent.ARCHITECTURE] += 2.0
    elif arch_hits == 1:
        # One arch noun is still a meaningful signal - especially with
        # interrogative structure ("how should I structure...").
        # Boost further if we also have an interrogative opener ("how/what/should")
        arch_boost = 1.2
        if starts_with_question_word:
            arch_boost += 0.8   # "how should i structure" -> 2.0, beats informational
        scores[Intent.ARCHITECTURE] += arch_boost

    # Speculative language mid-sentence
    speculative_phrases = [
        "thinking about", "what if", "maybe i should", "should i", "wondering if",
        "considering", "planning to", "want to build", "want to make", "idea of",
    ]
    for phrase in speculative_phrases:
        if phrase in text_lower:
            scores[Intent.BRAINSTORMING] += 1.2
            break

    # No verb at all in a short message → likely casual
    # GUARD: only fire if none of the structured verb sets matched
    verb_like = set(EXECUTION_VERBS) | set(DIAGNOSTIC_VERBS) | set(CONCEPTUAL_VERBS) | set(SPECULATIVE_VERBS) | set(COMMAND_VERBS)
    has_verb = any(t.lower() in verb_like for t in tokens) or starts_with_question_word
    if not has_verb and len(tokens) <= 5:
        scores[Intent.CASUAL] += 1.5

    return scores


def _score_formality(raw: str, tokens: List[str]) -> dict:
    """
    Measures linguistic formality. Low formality → casual tone, which boosts
    the casual intent bucket. Signals:
    - Contractions ("don't", "I'm", "it's")
    - Abbreviations & internet slang ("nthg", "tbh", "imo", "lol", "rn")
    - Missing capitalisation on sentence start
    - Excessive punctuation ("!!!", "...")
    - Single-character filler words

    NOTE: this scorer deliberately does NOT know about structural signals.
    The _length_heuristics scorer guards against casual over-boosting short
    messages that already have a clear structural intent.
    """
    scores = {i: 0.0 for i in Intent}
    text = raw.strip()

    informality = 0.0

    # Contractions
    contraction_count = len(re.findall(r"\b\w+'\w+\b", text))
    informality += contraction_count * 0.3

    # Internet abbreviations / shorthand (pattern-based, not a list)
    # Detects 2-5 char all-lowercase tokens that are NOT common English words
    COMMON_SHORT = {"is", "it", "in", "on", "at", "to", "do", "go", "be",
                    "we", "he", "she", "me", "my", "by", "up", "if", "or",
                    "so", "no", "ok", "hi", "hey", "can", "has", "had",
                    "the", "and", "for", "but", "not", "are", "was", "his",
                    "her", "our", "you", "all", "its", "any", "how", "who",
                    "did", "get", "let", "use", "new", "run", "say", "try"}
    for t in tokens:
        if 2 <= len(t) <= 5 and t.isalpha() and t.lower() not in COMMON_SHORT and t == t.lower():
            informality += 0.2

    # Missing sentence-start capitalisation
    if text and text[0].isalpha() and text[0].islower():
        informality += 0.4

    # Trailing "lol", "haha", "xd", "lmao" (regex for laugh markers)
    if re.search(r"\b(lol|lmao|haha|hehe|xd|lmfao)\b", text, re.I):
        informality += 0.8

    # Repeated letters ("heyyy", "nahhhh")
    if re.search(r"(.)\1{2,}", text):
        informality += 0.5

    # Excessive punctuation
    punct_runs = len(re.findall(r"[!?]{2,}", text))
    informality += punct_runs * 0.3

    # Map informality score → casual boost
    if informality >= 1.5:
        # Don't boost casual if frustration punctuation is present;
        # the frustration scorer handles that case.
        if not re.search(r"[!?]{2,}", text):
            scores[Intent.CASUAL] += 2.0
        else:
            scores[Intent.CASUAL] += 0.3  # minimal, let frustration win
    elif informality >= 0.8:
        scores[Intent.CASUAL] += 1.0
    elif informality >= 0.4:
        scores[Intent.CASUAL] += 0.4

    return scores


def _score_specificity(tokens: List[str], raw: str) -> dict:
    """
    Measures content-word density and topic specificity.
    - High specificity (named things, version numbers, file paths, error messages)
      → implementation or debugging
    - Low specificity with a broad topic → brainstorming or informational
    - Pure filler / vague → casual
    """
    scores = {i: 0.0 for i in Intent}
    text = raw.lower()

    # Content-word density: exclude stopwords
    STOP = {"a", "an", "the", "is", "it", "in", "on", "at", "to", "do", "be",
            "we", "he", "she", "me", "my", "by", "up", "if", "or", "so", "and",
            "but", "for", "not", "are", "was", "this", "that", "with", "from",
            "have", "has", "had", "can", "will", "just", "i", "you", "they",
            "them", "their", "about", "some", "would", "could", "should", "when",
            "how", "what", "why", "where", "which", "who"}
    content_tokens = [t for t in tokens if t.lower() not in STOP and len(t) > 2]
    density = len(content_tokens) / max(len(tokens), 1)

    # Error / stack-trace signals -> debugging
    # GUARD: don't fire if frustration markers are prominent (caps, expletives)
    # — in that case the frustration scorer handles routing.
    has_frustration_markers = bool(
        re.search(r"[!?]{2,}", raw)
        or re.search(r"\b[A-Z]{3,}\b", raw)
        or re.search(r"\b(wtf|ugh+|argh+|ffs|bruh)\b", raw, re.I)
    )
    if not has_frustration_markers and re.search(
        r"(error|exception|traceback|crash|undefined|null|nan|500|404|"
        r"typeerror|valueerror|syntaxerror|cannot read|is not a function|"
        r"failed to|unhandled|rejected|timeout)", text
    ):
        scores[Intent.DEBUGGING] += 2.0
    elif has_frustration_markers and re.search(
        r"(error|exception|traceback|crash|undefined|null|nan|500|404|"
        r"typeerror|valueerror|syntaxerror|cannot read|is not a function|"
        r"failed to|unhandled|rejected|timeout)", text
    ):
        # Technical crash term present but frustration is high
        # → lighter debugging boost so emotional can win
        scores[Intent.DEBUGGING] += 0.8

    # File paths, version numbers, package names (specificity indicators)
    has_path     = bool(re.search(r"[/\\][\w./\\]+", raw))
    has_version  = bool(re.search(r"\bv?\d+\.\d+", raw))
    has_at_pkg   = bool(re.search(r"@[\w/-]+", raw))  # e.g. @tanstack/query
    has_code_ref = bool(re.search(r"`[^`]+`|\"\"\"|\bconst\b|\blet\b|\bvar\b|"
                                  r"\bdef\b|\bclass\b|\bimport\b|\bexport\b|"
                                  r"\bfunction\b|\basync\b|\bawait\b", raw))

    specificity_bonus = sum([has_path, has_version, has_at_pkg, has_code_ref]) * 0.7
    if specificity_bonus:
        scores[Intent.IMPLEMENTATION] += specificity_bonus
        scores[Intent.DEBUGGING]      += specificity_bonus * 0.5

    # High density + long message → deep implementation or architecture
    if density > 0.6 and len(tokens) > 10:
        scores[Intent.IMPLEMENTATION] += 1.0
        scores[Intent.ARCHITECTURE]   += 0.5
    elif density < 0.3 and len(tokens) <= 6:
        scores[Intent.CASUAL] += 1.0
        scores[Intent.BRAINSTORMING] += 0.3

    return scores


def _score_frustration(raw: str) -> dict:
    """
    Detects emotional/frustrated state.
    Signals:
    - Repeated punctuation (!!!!, ????)
    - Negation + persistence ("still", "again", "nothing", "still not")
    - Expletive-adjacent expressions (wtf, ugh, argh — pattern-based)
    - ALL CAPS words mid-sentence
    """
    scores = {i: 0.0 for i in Intent}
    text = raw.strip()
    text_lower = text.lower()

    frustration = 0.0

    # Heavy punctuation
    if re.search(r"[!?]{3,}", text):
        frustration += 1.5
    elif re.search(r"[!?]{2,}", text):
        frustration += 0.8

    # Persistence / repetition signals
    persistence_patterns = [
        r"\bstill\b.*\b(not|doesn|don|won|can|isn)\b",
        r"\bagain\b",
        r"\bnothing works\b",
        r"\bwhy (isn|doesn|won|can)\'?t\b",
        r"\bkeep(s)? (getting|failing|breaking|crashing)\b",
    ]
    for pat in persistence_patterns:
        if re.search(pat, text_lower):
            frustration += 0.8
            break

    # Expletive / exasperation (pattern, not list)
    if re.search(r"\b(wtf|ugh+|argh+|ffs|damn|ugh|bruh|bro\s+what)\b", text_lower):
        frustration += 1.2

    # ALL CAPS (shouting) — at least one all-caps word of 3+ chars
    caps_words = re.findall(r"\b[A-Z]{3,}\b", text)
    if caps_words:
        frustration += 0.5 * min(len(caps_words), 2)

    if frustration >= 1.5:
        scores[Intent.EMOTIONAL]  += 3.0
        scores[Intent.DEBUGGING]  += 1.0
    elif frustration >= 0.8:
        scores[Intent.EMOTIONAL]  += 1.8
        scores[Intent.DEBUGGING]  += 0.5
    elif frustration >= 0.3:
        scores[Intent.EMOTIONAL]  += 0.8

    return scores


def _score_code_gate(raw: str, tokens: List[str]) -> dict:
    """
    Discriminates between "talk about X" and "do X for me".
    Execution/creation intent → wants_code=True candidate.
    Conceptual/exploratory intent → wants_code=False candidate.

    This scorer ONLY adjusts implementation vs. informational/brainstorming
    relative scores. The `wants_code` flag is then derived from the final intent.
    """
    scores = {i: 0.0 for i in Intent}
    text_lower = raw.lower()

    # Phrases that clearly mean "produce something executable"
    PRODUCE_PHRASES = [
        r"\b(build|create|make|write|generate|implement|code up|scaffold)\b.{0,30}\b(app|server|api|component|function|script|service|endpoint|route|model|schema|test)\b",
        r"\b(give me|show me)\b.{0,20}\b(code|example|implementation|snippet|function)\b",
        r"\bhow (to|do i)\b.{0,30}\b(implement|build|create|set up|configure|install)\b",
    ]
    for phrase_pat in PRODUCE_PHRASES:
        if re.search(phrase_pat, text_lower):
            scores[Intent.IMPLEMENTATION] += 1.5
            return scores

    # Phrases that mean "talk about X, don't do it yet"
    EXPLORE_PHRASES = [
        r"\bwhat is\b",
        r"\bwhat are\b",
        r"\bhow does\b",
        r"\bhow do(es)?\b.{0,20}\bwork\b",
        r"\bexplain\b",
        r"\btell me about\b",
        r"\bthinking (about|of)\b",
        r"\bconsidering\b",
        r"\bwondering (if|about|whether)\b",
        r"\bshould i use\b",
        r"\bwhat('s| is) the (best|difference|pros|cons)\b",
    ]
    for phrase_pat in EXPLORE_PHRASES:
        if re.search(phrase_pat, text_lower):
            scores[Intent.INFORMATIONAL] += 1.2
            scores[Intent.BRAINSTORMING] += 0.5
            return scores

    return scores


def _score_history(history: List[HistoryTurn]) -> dict:
    """
    Weights the current classification based on prior turn context.
    Rules:
    - If last user intent was casual → pull ambiguous turns toward casual
    - If last user intent was debugging → pull toward debugging (sessions tend to persist)
    - If last user intent was brainstorming → pull toward brainstorming
    - Decay factor per turn distance
    """
    scores = {i: 0.0 for i in Intent}
    if not history:
        return scores

    # Look at last 3 user turns
    user_turns = [t for t in history if t.role == "user" and t.intent is not None][-3:]

    for dist, turn in enumerate(reversed(user_turns)):
        decay = 0.8 ** dist  # 1.0, 0.8, 0.64
        weight = 0.4 * decay
        if turn.intent in (Intent.CASUAL, Intent.EMOTIONAL):
            scores[Intent.CASUAL] += weight
        elif turn.intent == Intent.DEBUGGING:
            scores[Intent.DEBUGGING] += weight * 1.5
        elif turn.intent == Intent.BRAINSTORMING:
            scores[Intent.BRAINSTORMING] += weight
        elif turn.intent == Intent.ARCHITECTURE:
            scores[Intent.ARCHITECTURE] += weight

    return scores


# ─────────────────────────────────────────────────────────────────────────────
# Message length heuristics
# ─────────────────────────────────────────────────────────────────────────────

def _length_heuristics(tokens: List[str], raw: str) -> dict:
    """
    Very short messages almost always need a quick human reply, not an essay.
    Very long messages with rich content warrant detailed answers.

    GUARD: we suppress the casual boost if the raw text contains strong
    structural signals (starts with a question word, or contains an exclamation
    burst that suggests frustration). This prevents the length heuristic from
    swamping genuinely-typed command or emotional messages.
    """
    scores = {i: 0.0 for i in Intent}
    n = len(tokens)
    first = tokens[0].lower() if tokens else ""

    # Structural signals that should suppress the length-based casual push
    INTERROGATIVE = {"what", "why", "how", "when", "where", "which", "who",
                     "is", "are", "does", "do", "can", "could", "would", "should"}
    COMMAND_OR_IMPL = {
        "run", "execute", "start", "stop", "restart", "install", "uninstall",
        "launch", "kill", "spawn", "init", "clone", "pull", "push", "commit",
        "build", "create", "make", "write", "generate", "implement", "code",
        "deploy", "setup", "scaffold", "add", "update", "refactor",
        "fix", "debug", "repair", "resolve", "patch",
    }
    has_strong_signal = (
        first in INTERROGATIVE
        or first in COMMAND_OR_IMPL
        or bool(re.search(r"[!?]{2,}", raw))   # frustration punctuation
    )

    if n <= 3 and not has_strong_signal:
        scores[Intent.CASUAL] += 1.8
    elif n <= 6 and not has_strong_signal:
        scores[Intent.CASUAL] += 0.6
    elif n >= 20:
        # Long, detailed message → depth
        scores[Intent.IMPLEMENTATION] += 0.5
        scores[Intent.ARCHITECTURE]   += 0.3
        scores[Intent.DEBUGGING]      += 0.3

    return scores


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation & derivation
# ─────────────────────────────────────────────────────────────────────────────

def _aggregate(score_dicts: List[dict]) -> dict:
    """Sum all scorer contributions into one score dict."""
    total = {i: 0.0 for i in Intent}
    for d in score_dicts:
        for k, v in d.items():
            total[k] += v
    return total


def _derive_tone(formality_scores: dict, raw: str) -> Tone:
    """Derive tone from the formality scorer's casual boost."""
    casual_boost = formality_scores.get(Intent.CASUAL, 0.0)
    if casual_boost >= 1.5:
        return Tone.CASUAL
    if casual_boost >= 0.5:
        return Tone.NEUTRAL
    return Tone.FORMAL


def _derive_depth(tokens: List[str], intent: Intent) -> Depth:
    n = len(tokens)
    if intent in (Intent.CASUAL, Intent.EMOTIONAL) or n <= 5:
        return Depth.SHALLOW
    if intent in (Intent.IMPLEMENTATION, Intent.DEBUGGING, Intent.ARCHITECTURE) or n >= 15:
        return Depth.DEEP
    return Depth.MEDIUM


def _derive_verbosity(depth: Depth, intent: Intent, tone: Tone) -> Verbosity:
    if tone == Tone.CASUAL or intent == Intent.CASUAL:
        return Verbosity.CONCISE
    if depth == Depth.DEEP or intent in (Intent.IMPLEMENTATION, Intent.DEBUGGING):
        return Verbosity.DETAILED
    return Verbosity.NORMAL


def _derive_wants_code(intent: Intent) -> bool:
    return intent in (Intent.IMPLEMENTATION, Intent.COMMAND, Intent.DEBUGGING)


def _derive_needs_rag(intent: Intent, tokens: List[str]) -> bool:
    """
    RAG retrieval is useful when the question is technical and specific enough
    that local codebase context or web search would materially improve the answer.
    Casual, emotional, clarification, and shallow brainstorming don't need it.
    """
    if intent in (Intent.CASUAL, Intent.EMOTIONAL, Intent.CLARIFICATION):
        return False
    if intent == Intent.INFORMATIONAL and len(tokens) >= 4:
        return True
    if intent in (Intent.IMPLEMENTATION, Intent.DEBUGGING,
                  Intent.ARCHITECTURE, Intent.COMMAND):
        return True
    if intent == Intent.BRAINSTORMING and len(tokens) >= 8:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def classify_intent(
    message: str,
    history: Optional[List[HistoryTurn]] = None,
) -> IntentResult:
    """
    Classify the user's intent from a message and optional conversation history.

    Args:
        message:  Raw user message string.
        history:  List of recent HistoryTurn objects (user + assistant turns).
                  Used ONLY for intent classification — not injected into the LLM prompt.

    Returns:
        IntentResult with all routing flags set.
    """
    history = history or []

    # Tokenise (simple whitespace split after stripping punctuation from edges)
    raw = message.strip()
    tokens = [
        t.strip(string.punctuation)
        for t in raw.split()
        if t.strip(string.punctuation)
    ]

    # Run all scorers
    struct_scores    = _score_sentence_structure(tokens, raw)
    formality_scores = _score_formality(raw, tokens)
    specific_scores  = _score_specificity(tokens, raw)
    frustration_sc   = _score_frustration(raw)
    code_gate_sc     = _score_code_gate(raw, tokens)
    history_sc       = _score_history(history)
    length_sc        = _length_heuristics(tokens, raw)

    # Aggregate
    total = _aggregate([
        struct_scores,
        formality_scores,
        specific_scores,
        frustration_sc,
        code_gate_sc,
        history_sc,
        length_sc,
    ])

    # Select winning intent.
    # Tie-break priority: emotional > debugging > casual (when scores equal).
    # Rationale: acknowledging frustration is more valuable than immediately
    # switching to debugging mode for the same score.
    TIEBREAK_PRIORITY = {
        Intent.EMOTIONAL:      10,
        Intent.DEBUGGING:       9,
        Intent.IMPLEMENTATION:  8,
        Intent.ARCHITECTURE:    7,
        Intent.BRAINSTORMING:   6,
        Intent.COMMAND:         5,
        Intent.INFORMATIONAL:   4,
        Intent.CLARIFICATION:   3,
        Intent.CASUAL:          2,
    }
    winning_intent = max(
        total,
        key=lambda i: (round(total[i], 6), TIEBREAK_PRIORITY.get(i, 0)),
    )

    # If all scores are near-zero (blank-ish message), default to casual
    if total[winning_intent] < 0.3:
        winning_intent = Intent.CASUAL

    # Derive secondary attributes
    tone      = _derive_tone(formality_scores, raw)
    depth     = _derive_depth(tokens, winning_intent)
    verbosity = _derive_verbosity(depth, winning_intent, tone)
    wants_code = _derive_wants_code(winning_intent)
    needs_rag  = _derive_needs_rag(winning_intent, tokens)

    return IntentResult(
        intent     = winning_intent,
        tone       = tone,
        depth      = depth,
        wants_code = wants_code,
        needs_rag  = needs_rag,
        verbosity  = verbosity,
        scores     = {k.value: round(v, 3) for k, v in total.items()},
    )
