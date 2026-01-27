"""
Evaluator Agent - Score backtest results and provide feedback.

Compares experimental results to baseline and determines:
- Whether the experiment improved performance
- Specific feedback for the next iteration
- Recommendation: iterate, promote, or reject
"""

import logging
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


# =============================================================================
# MODELS
# =============================================================================

class EvaluationResult(BaseModel):
    """Result of evaluating a backtest against baseline."""
    
    # Delta calculations
    win_rate_delta: float = Field(default=0.0)
    avg_r_delta: float = Field(default=0.0)
    total_return_delta: float = Field(default=0.0)
    sharpe_delta: Optional[float] = Field(default=None)
    max_dd_delta: float = Field(default=0.0, description="Positive = less drawdown")
    
    # Verdict
    improvement_score: float = Field(default=0.0, description="Weighted 0-1 score relative to baseline")
    absolute_score: float = Field(default=0.0, description="Absolute performance score (0-1) independent of baseline")
    passed_threshold: bool = Field(default=False)
    recommendation: str = Field(default="reject", description="iterate/promote/reject")
    
    # Feedback for next iteration
    summary: str = Field(default="")
    feedback: str = Field(default="", description="Specific feedback for Researcher")
    
    # Metrics
    baseline_trades: int = Field(default=0)
    variant_trades: int = Field(default=0)
    
    # Rejection reasons (if any)
    rejection_reasons: list[str] = Field(default_factory=list)


# =============================================================================
# EVALUATOR AGENT
# =============================================================================

class EvaluatorAgent:
    """Evaluates backtest results and provides structured feedback.
    
    Unlike Researcher/Coder, this agent uses rule-based logic
    rather than LLM for consistent, deterministic scoring.
    """
    
    # Thresholds
    IMPROVEMENT_THRESHOLD = 0.10  # 10% improvement required
    MIN_TRADES = 30  # For statistical significance
    MAX_SINGLE_DAY_LOSS = 0.05  # 5% max single-day loss
    MIN_WIN_RATE = 0.40  # 40% minimum win rate
    
    # Weights for composite score
    WEIGHTS = {
        "win_rate": 0.40,
        "sharpe": 0.30,
        "max_dd": 0.20,
        "min_trades": 0.10,
    }
    
    def evaluate(
        self,
        baseline_metrics: Dict[str, Any],
        variant_metrics: Dict[str, Any],
    ) -> EvaluationResult:
        """Evaluate experiment results against baseline.
        
        Args:
            baseline_metrics: Metrics from baseline backtest
            variant_metrics: Metrics from experimental backtest
            
        Returns:
            EvaluationResult with deltas, score, and recommendation
        """
        result = EvaluationResult()
        
        # Extract metrics
        b_win = baseline_metrics.get("win_rate", 0)
        v_win = variant_metrics.get("win_rate", 0)
        
        b_r = baseline_metrics.get("avg_r", 0)
        v_r = variant_metrics.get("avg_r", 0)
        
        b_return = baseline_metrics.get("total_return", 0)
        v_return = variant_metrics.get("total_return", 0)
        
        b_sharpe = baseline_metrics.get("sharpe_ratio")
        v_sharpe = variant_metrics.get("sharpe_ratio")
        
        b_dd = baseline_metrics.get("max_drawdown", 0)
        v_dd = variant_metrics.get("max_drawdown", 0)
        
        b_trades = baseline_metrics.get("total_trades", 0)
        v_trades = variant_metrics.get("total_trades", 0)
        
        # Calculate deltas
        result.win_rate_delta = v_win - b_win
        result.avg_r_delta = v_r - b_r
        result.total_return_delta = v_return - b_return
        result.max_dd_delta = b_dd - v_dd  # Positive = less DD = better
        result.baseline_trades = b_trades
        result.variant_trades = v_trades
        
        if b_sharpe is not None and v_sharpe is not None:
            result.sharpe_delta = v_sharpe - b_sharpe
        
        # Check hard rejection criteria
        rejection_reasons = []
        
        if v_win < self.MIN_WIN_RATE:
            rejection_reasons.append(f"Win rate {v_win*100:.1f}% below {self.MIN_WIN_RATE*100}% threshold")
        
        if v_trades < self.MIN_TRADES:
            rejection_reasons.append(f"Only {v_trades} trades - need {self.MIN_TRADES} for significance")
        
        result.rejection_reasons = rejection_reasons
        
        # Calculate weighted improvement score
        score = 0.0
        
        # Win rate component (normalize to 0-1 range)
        win_rate_improvement = result.win_rate_delta / 100
        score += self.WEIGHTS["win_rate"] * max(0, min(1, win_rate_improvement * 10))
        
        # Sharpe component
        if result.sharpe_delta is not None:
            sharpe_improvement = result.sharpe_delta / 2
            score += self.WEIGHTS["sharpe"] * max(0, min(1, sharpe_improvement + 0.5))
        
        # Max DD component (less drawdown = better)
        if result.max_dd_delta >= 0:
            score += self.WEIGHTS["max_dd"] * 1.0
        else:
            dd_penalty = min(1, abs(result.max_dd_delta) / 10)
            score += self.WEIGHTS["max_dd"] * (1 - dd_penalty)
        
        # Min trades component
        if v_trades >= self.MIN_TRADES:
            score += self.WEIGHTS["min_trades"] * 1.0
        
        result.improvement_score = score
        
        # Calculate absolute score based on raw variant metrics (not deltas)
        # This allows comparing scores across experiments with different baselines
        abs_score = 0.0
        
        # Win rate component: 50% win rate = 0.5 score, 60% = 0.6, etc.
        abs_score += self.WEIGHTS["win_rate"] * min(1.0, v_win / 100)
        
        # Sharpe component: positive sharpe is good
        if v_sharpe is not None:
            abs_score += self.WEIGHTS["sharpe"] * max(0, min(1, (v_sharpe + 1) / 3))
        
        # Max DD component: 0% DD = 1.0, 20% DD = 0.5, 40%+ DD = 0
        abs_score += self.WEIGHTS["max_dd"] * max(0, 1 - (abs(v_dd) / 40))
        
        # Trade count component: meets minimum = 1.0
        if v_trades >= self.MIN_TRADES:
            abs_score += self.WEIGHTS["min_trades"] * 1.0
        elif v_trades > 0:
            abs_score += self.WEIGHTS["min_trades"] * (v_trades / self.MIN_TRADES)
        
        result.absolute_score = abs_score
        
        # Determine recommendation
        if rejection_reasons:
            result.recommendation = "reject"
            result.passed_threshold = False
            result.summary = f"Rejected: {rejection_reasons[0]}"
        elif score >= 0.6:
            result.recommendation = "promote"
            result.passed_threshold = True
            result.summary = f"Pass: {result.win_rate_delta:+.1f}% win rate, score {score:.2f}"
        elif score >= 0.3:
            result.recommendation = "iterate"
            result.passed_threshold = False
            result.summary = f"Iterate: score {score:.2f}, needs improvement"
        else:
            result.recommendation = "reject"
            result.passed_threshold = False
            result.summary = f"Reject: score {score:.2f} below threshold"
        
        # Generate feedback for next iteration
        result.feedback = self._generate_feedback(result, baseline_metrics, variant_metrics)
        
        return result
    
    def _generate_feedback(
        self,
        result: EvaluationResult,
        baseline: Dict[str, Any],
        variant: Dict[str, Any],
    ) -> str:
        """Generate specific feedback for the Researcher Agent."""
        
        feedback_parts = []
        
        # Win rate feedback
        if result.win_rate_delta > 0:
            feedback_parts.append(f"Win rate improved by {result.win_rate_delta:+.1f}% - good progress")
        elif result.win_rate_delta < -5:
            feedback_parts.append(f"Win rate dropped {result.win_rate_delta:.1f}% - too aggressive, try smaller change")
        
        # R-multiple feedback
        if result.avg_r_delta > 0:
            feedback_parts.append(f"Average R improved by {result.avg_r_delta:+.2f}")
        elif result.avg_r_delta < -0.3:
            feedback_parts.append(f"Average R dropped {result.avg_r_delta:.2f} - risk/reward worsened")
        
        # Drawdown feedback
        if result.max_dd_delta > 0:
            feedback_parts.append(f"Drawdown reduced by {result.max_dd_delta:.1f}% - safer")
        elif result.max_dd_delta < -3:
            feedback_parts.append(f"Drawdown increased {abs(result.max_dd_delta):.1f}% - too risky")
        
        # Trade count feedback
        if result.variant_trades < result.baseline_trades * 0.5:
            feedback_parts.append("Filters may be too strict - reduced trades by 50%+")
        elif result.variant_trades > result.baseline_trades * 2:
            feedback_parts.append("Filters may be too loose - doubled trade count")
        
        if not feedback_parts:
            feedback_parts.append("No major changes detected - try a different approach")
        
        return "; ".join(feedback_parts)


# Singleton
_agent: Optional[EvaluatorAgent] = None


def get_evaluator_agent() -> EvaluatorAgent:
    """Get the singleton evaluator agent."""
    global _agent
    if _agent is None:
        _agent = EvaluatorAgent()
    return _agent
