"""
GC API Client — Antigravity helper to trigger GC tasks directly.

Usage (from Antigravity):
  from gc_api_client import verify_claim, run_test, get_top_gaps, read_memory

  # Verify a P&L claim
  result = verify_claim("ROLR is $61K")
  # {'verdict': 'CONFIRMED', 'actual': '$61,566', ...}

  # Run a test case
  result = run_test(["ROLR"])
  # {batch result JSON}

  # Get top gaps
  result = get_top_gaps(top=5)
  # {gaps JSON}

  # Read GC memory
  content = read_memory("wb-benchmark")
  # {markdown content}
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error

GC_API_URL = "http://127.0.0.1:3033"


def _request(method: str, path: str, body: dict | None = None, timeout: int = 600) -> dict:
    """Make HTTP request to GC Task API."""
    url = f"{GC_API_URL}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        return {"error": f"GC API not reachable at {url}: {e}"}
    except Exception as e:
        return {"error": f"Request failed: {e}"}


def is_gc_running() -> bool:
    """Check if GC Task API is running."""
    result = _request("GET", "/health", timeout=5)
    return result.get("status") == "ok"


def verify_claim(claim: str, silent: bool = True) -> dict:
    """Verify a P&L claim against GC's verified benchmark data.
    
    Args:
        claim: The claim to verify (e.g., "ROLR is $61K")
        silent: If True (default), Telegram notification is silent. 
                Set False for important verifications Clay should notice.
    """
    result = _request("POST", "/task", {"type": "verify", "args": {"claim": claim}, "silent": silent})
    return result.get("result", result)


def run_test(cases: list[str] | None = None, silent: bool = True) -> dict:
    """Run test cases via GC.
    
    Args:
        cases: List of symbols or case IDs. None = run all.
        silent: If True (default), Telegram notification is silent.
    """
    args = {"cases": cases} if cases else {}
    return _request("POST", "/task", {"type": "test", "args": args, "silent": silent}, timeout=600)


def get_top_gaps(top: int = 10, silent: bool = True) -> dict:
    """Get the biggest P&L gaps from GC's benchmark data."""
    return _request("POST", "/task", {"type": "top-gaps", "args": {"top": top}, "silent": silent})


def read_memory(slug: str) -> str | None:
    """Read a GC memory file by slug (e.g., 'wb-benchmark').
    
    Returns the markdown content, or None if not found.
    """
    result = _request("GET", f"/memory/{slug}", timeout=10)
    return result.get("content")


def notify_clay(message: str) -> dict:
    """Send a loud Telegram notification to Clay via GC.
    
    Use at pivotal moments:
    - Start/end of an iteration session
    - When Clay's input is needed
    - Important discoveries or results
    """
    return _request("POST", "/task", {
        "type": "notify",
        "args": {"message": message},
        "silent": False
    })


def store_analysis(topic: str, analysis: str, claims: list[str] | None = None) -> dict:
    """Store analysis in GC memory for cross-session persistence.
    
    GC will verify any claims against benchmark data before storing.
    If claims are WRONG, GC will challenge and notify Clay.
    
    Args:
        topic: Short topic name (e.g., "NPT-gap", "guard-effectiveness")
        analysis: Your analysis text (markdown supported)
        claims: Optional list of P&L claims to verify (e.g., ["NPT is 17K", "capture is 37%"])
    
    Returns dict with: stored, slug, verification results, and whether any claims were challenged.
    """
    body: dict = {"type": "store-analysis", "args": {"topic": topic, "analysis": analysis}}
    if claims:
        body["args"]["claims"] = claims
    result = _request("POST", "/task", body)
    return result.get("result", result)


def recall_analysis(topic: str | None = None) -> dict | str | None:
    """Retrieve past analysis from GC memory.
    
    Args:
        topic: Topic to recall. If None, lists all stored analyses.
    
    Returns:
        If topic given: markdown content of the analysis, or None if not found
        If topic is None: dict with list of all stored analyses
    """
    result = _request("POST", "/task", {"type": "recall", "args": {"topic": topic}})
    inner = result.get("result", result)
    if topic and isinstance(inner, dict):
        return inner.get("content")
    return inner


def start_session(goal: str, plan: str | None = None, topic: str | None = None) -> dict:
    """Start an iteration session — sends loud Telegram notification to Clay.
    
    Args:
        goal: What this session aims to accomplish
        plan: High-level plan (optional)
        topic: Related topic/case (optional)
    """
    args: dict = {"goal": goal}
    if plan: args["plan"] = plan
    if topic: args["topic"] = topic
    result = _request("POST", "/task", {"type": "session-start", "args": args})
    return result.get("result", result)


def end_session(summary: str, results: str | None = None, next_steps: str | None = None) -> dict:
    """End an iteration session — sends loud Telegram notification to Clay.
    
    Args:
        summary: What was accomplished
        results: Key metrics or outcomes (optional)
        next_steps: What to do next (optional)
    """
    args: dict = {"summary": summary}
    if results: args["results"] = results
    if next_steps: args["next_steps"] = next_steps
    result = _request("POST", "/task", {"type": "session-end", "args": args})
    return result.get("result", result)


def read_activity_log() -> str | None:
    """Read the activity log to see what Antigravity has been doing."""
    return read_memory("ag-activity-log")


# CLI test
if __name__ == "__main__":
    import sys
    
    if not is_gc_running():
        print("❌ GC Task API not running at", GC_API_URL)
        print("   Start GC with: npm run dev (in gravity-claw)")
        sys.exit(1)
    
    print("✅ GC Task API is running")
    
    # Test verify
    print("\n--- Verify: ROLR is 61K ---")
    r = verify_claim("ROLR is 61K")
    print(json.dumps(r, indent=2))
    
    # Test memory read
    print("\n--- Memory: wb-benchmark ---")
    content = read_memory("wb-benchmark")
    if content:
        # Show first 5 lines
        for line in content.split("\n")[:10]:
            print(f"  {line}")
    else:
        print("  (not found)")
