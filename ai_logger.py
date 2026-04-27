"""
ai_logger.py — Structured logging for PawPal+ AI calls
=======================================================
Writes two newline-delimited JSON (JSONL) files under logs/:
  ai_calls.jsonl    — one entry per API call (success or failure)
  ai_feedback.jsonl — one entry per human thumbs-up / thumbs-down rating

JSONL format lets entries be appended without loading the full file and
makes it trivial to pipe into jq, pandas, or any analytics tool later.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

_LOG_DIR = Path(__file__).parent / "logs"


def _write(filename: str, entry: dict) -> None:
    _LOG_DIR.mkdir(exist_ok=True)
    with open(_LOG_DIR / filename, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def log_call(
    method: str,
    context_summary: str,
    response: str | None,
    latency_ms: float,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    error: Exception | None = None,
) -> None:
    """Record one AI API call — success or failure — to ai_calls.jsonl."""
    _write("ai_calls.jsonl", {
        "ts":               datetime.now(timezone.utc).isoformat(),
        "method":           method,
        "context":          context_summary[:300],
        "response_preview": response[:300] if response else None,
        "latency_ms":       round(latency_ms, 1),
        "input_tokens":     input_tokens,
        "output_tokens":    output_tokens,
        "error":            str(error) if error else None,
        "ok":               error is None,
    })


def log_feedback(
    method: str,
    context_summary: str,
    response_preview: str,
    rating: str,          # "up" or "down"
) -> None:
    """Record a human thumbs-up / thumbs-down rating to ai_feedback.jsonl."""
    _write("ai_feedback.jsonl", {
        "ts":               datetime.now(timezone.utc).isoformat(),
        "method":           method,
        "context":          context_summary[:300],
        "response_preview": response_preview[:300],
        "rating":           rating,
    })


def read_stats() -> dict:
    """Return aggregate stats from ai_calls.jsonl for the UI dashboard."""
    path = _LOG_DIR / "ai_calls.jsonl"
    if not path.exists():
        return {"total": 0, "errors": 0, "avg_latency_ms": None, "total_tokens": None}

    entries = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    total     = len(entries)
    errors    = sum(1 for e in entries if not e.get("ok", True))
    latencies = [e["latency_ms"] for e in entries if e.get("latency_ms") is not None]
    tokens    = [
        (e.get("input_tokens") or 0) + (e.get("output_tokens") or 0)
        for e in entries
        if e.get("input_tokens") is not None
    ]
    return {
        "total":          total,
        "errors":         errors,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "total_tokens":   sum(tokens) if tokens else None,
    }


def read_feedback_stats() -> dict:
    """Return thumbs-up / thumbs-down counts from ai_feedback.jsonl."""
    path = _LOG_DIR / "ai_feedback.jsonl"
    if not path.exists():
        return {"up": 0, "down": 0}

    entries = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {
        "up":   sum(1 for e in entries if e.get("rating") == "up"),
        "down": sum(1 for e in entries if e.get("rating") == "down"),
    }
