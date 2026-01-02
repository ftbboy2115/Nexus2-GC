# core/risk_engine.py

"""
Risk Engine (v1.1.0)
--------------------
Computes basic risk metrics and ratings for strategy objects.

Changelog:
- v1.1.0:
    - Incorporated rs_raw as a secondary factor in risk_score.

- v1.0.0:
    - Initial implementation using catalyst_score, risk_per_share, setup.
"""

from typing import Dict, Any


def _score_risk(strategy: Dict[str, Any]) -> float:
    """
    Compute a simple numeric risk score (0-100).

    Inputs (v1.1):
        - risk_per_share
        - catalyst_score
        - setup
        - rs_raw (optional)

    Heuristic:
        - Base score from catalyst_score (0–100).
        - Penalty for large risk_per_share.
        - Small bonus for EP setups.
        - Mild boost/penalty from rs_raw.
    """
    catalyst_score = strategy.get("catalyst_score") or 0.0
    rps = strategy.get("risk_per_share")
    setup = (strategy.get("setup") or "").upper()
    rs_raw = strategy.get("rs_raw")

    score = float(catalyst_score)

    if rps is not None:
        if rps > 5:
            score -= 10
        if rps > 10:
            score -= 10

    if setup == "EP":
        score += 5

    # RS influence: rs_raw is typically in [-0.5, +0.5] range (±50% vs SPY)
    if rs_raw is not None:
        # Scale rs_raw to a reasonable impact: ~[-10, +10] in extreme cases
        score += max(-10.0, min(10.0, rs_raw * 100.0))

    return max(0.0, min(100.0, score))


def _rating_from_score(score: float) -> str:
    if score >= 80:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    if score >= 20:
        return "D"
    return "F"


def _position_size_factor(score: float) -> float:
    if score >= 80:
        return 1.0
    if score >= 60:
        return 0.75
    if score >= 40:
        return 0.5
    if score >= 20:
        return 0.25
    return 0.0


def get_risk_profile(strategy: Dict[str, Any]) -> Dict[str, Any]:
    score = _score_risk(strategy)
    rating = _rating_from_score(score)
    size_factor = _position_size_factor(score)

    return {
        "risk_rating": rating,
        "risk_score": score,
        "position_size_factor": size_factor,
    }