"""
File: test/test_pipeline.py
Version: 1.2.1
Author: Clay & Copilot

Title:
    Minimal Nexus Pipeline Test Harness

Purpose:
    Validate the structural flow of:
        Stage 1 → Stage 2 → Stage 3 → Stage 4

Notes:
    - This harness does NOT require live data.
    - Stage 2 enrichment engines may return None if not wired or configured.
    - This test ensures the pipeline executes end-to-end without errors.
"""

from nexus_pipeline.stage2.build_contexts import ContextBuilder


# ----------------------------------------------------------------------
# Stage 1 (Universe Builder — Mock)
# ----------------------------------------------------------------------
def stage1_scan():
    """
    Mock Stage 1.
    In production, this is implemented by scan_pre_market.py.
    """
    return ["AAPL", "TSLA", "NVDA"]


# ----------------------------------------------------------------------
# Stage 3 (Scoring Engine — Mock)
# ----------------------------------------------------------------------
def stage3_score(contexts):
    """
    Mock Stage 3 scoring logic.
    In production, this is implemented by score_candidates.py.
    """
    scored = []
    for ctx in contexts:
        score = 0

        # Catalyst contribution
        if ctx.get("has_catalyst"):
            score += 10

        # RS contribution
        if ctx.get("rs_value"):
            score += ctx["rs_value"] * 0.1

        # Episodic Pivot contribution (KK-style)
        if ctx.get("ep_pivot_score"):
            score += ctx["ep_pivot_score"]

        ctx["score"] = score
        scored.append(ctx)

    return scored


# ----------------------------------------------------------------------
# Stage 4 (Signal Filter — Mock)
# ----------------------------------------------------------------------
def stage4_filter(scored_contexts):
    """
    Mock Stage 4 signal filter.
    In production, this is implemented by filter_signals.py.
    """
    signals = []
    for ctx in scored_contexts:
        if ctx["score"] >= 10:
            signals.append(ctx)
    return signals


# ----------------------------------------------------------------------
# End-to-End Test Runner
# ----------------------------------------------------------------------
def run_test_pipeline():
    print("\n=== Running Minimal Nexus Pipeline Test (v1.2.1) ===\n")

    # Stage 1
    symbols = stage1_scan()
    print(f"Stage 1 output: {symbols}")

    # Stage 2
    builder = ContextBuilder(logger=PrintLogger())
    contexts = builder.build(symbols)
    print("\nStage 2 output (contexts):")
    for c in contexts:
        print(c)

    # Stage 3
    scored = stage3_score(contexts)
    print("\nStage 3 output (scored):")
    for s in scored:
        print(s)

    # Stage 4
    signals = stage4_filter(scored)
    print("\nStage 4 output (signals):")
    for sig in signals:
        print(sig)

    print("\n=== Pipeline Test Complete ===\n")


################
#Logging
###############
class PrintLogger:
    def info(self, msg):
        print(msg)

    def error(self, msg):
        print(msg)


if __name__ == "__main__":
    run_test_pipeline()