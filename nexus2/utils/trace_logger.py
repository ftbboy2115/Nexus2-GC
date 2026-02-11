"""
Trace Logger — Minimal file-based event tracer for diagnosing runner divergence.

Writes JSONL to /tmp/trace_{tag}.jsonl (Linux) or %TEMP%/trace_{tag}.jsonl (Windows).
Uses ContextVars so both sequential and concurrent runners can tag events independently.

Usage:
    set_trace_tag("seq")   # Call once at start of sequential run
    trace("price", t="09:31", sym="BATL", p=4.20)
    trace("fill", sym="BATL", qty=250, price=4.20, cash=24750.0)
"""
import json
import os
import tempfile
from contextvars import ContextVar

_runner_tag: ContextVar[str] = ContextVar('trace_runner_tag', default='')
_trace_enabled: ContextVar[bool] = ContextVar('trace_enabled', default=False)

TRACE_DIR = tempfile.gettempdir()


def set_trace_tag(tag: str):
    """Set the runner tag for this context/process. Enables tracing."""
    _runner_tag.set(tag)
    _trace_enabled.set(True)
    # Clear previous trace file
    path = os.path.join(TRACE_DIR, f"trace_{tag}.jsonl")
    if os.path.exists(path):
        os.remove(path)


def trace(event: str, **data):
    """Write a trace event. No-op if tracing not enabled."""
    if not _trace_enabled.get(False):
        return
    tag = _runner_tag.get('')
    if not tag:
        return
    entry = {"e": event, **data}
    path = os.path.join(TRACE_DIR, f"trace_{tag}.jsonl")
    try:
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Never crash on trace failure
