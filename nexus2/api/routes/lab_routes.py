"""
Lab API Routes - Strategy management endpoints.

Provides REST API for the R&D Lab:
- List strategies
- Get strategy details
- Create new strategy versions
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from nexus2.domain.lab import StrategySpec
from nexus2.domain.lab.strategy_registry import get_registry


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lab", tags=["lab"])


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class StrategyListItem(BaseModel):
    """Summary of a strategy for listing."""
    name: str
    versions: list[str]
    latest: str


class StrategyListResponse(BaseModel):
    """Response for list strategies endpoint."""
    strategies: list[StrategyListItem]
    count: int


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/strategies", response_model=StrategyListResponse)
async def list_strategies():
    """List all available strategies with their versions."""
    registry = get_registry()
    strategies = registry.list_strategies()
    
    return StrategyListResponse(
        strategies=[StrategyListItem(**s) for s in strategies],
        count=len(strategies),
    )


@router.get("/strategies/{name}", response_model=StrategySpec)
async def get_strategy(name: str, version: Optional[str] = None):
    """Get a strategy by name, optionally specifying version.
    
    If no version specified, returns the latest version.
    """
    registry = get_registry()
    strategy = registry.load_strategy(name, version)
    
    if not strategy:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy not found: {name}" + (f" v{version}" if version else ""),
        )
    
    return strategy


@router.get("/strategies/{name}/{version}", response_model=StrategySpec)
async def get_strategy_version(name: str, version: str):
    """Get a specific version of a strategy."""
    registry = get_registry()
    strategy = registry.load_strategy(name, version)
    
    if not strategy:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy not found: {name} v{version}",
        )
    
    return strategy


@router.post("/strategies", response_model=dict)
async def create_strategy(spec: StrategySpec):
    """Create a new strategy version.
    
    Strategy versions are immutable - once created, they cannot be modified.
    To make changes, create a new version.
    """
    registry = get_registry()
    
    # Check if version already exists
    if registry.strategy_exists(spec.name, spec.version):
        raise HTTPException(
            status_code=409,
            detail=f"Strategy version already exists: {spec.name} v{spec.version}",
        )
    
    # Save the strategy
    success = registry.save_strategy(spec)
    
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to save strategy",
        )
    
    return {
        "status": "created",
        "name": spec.name,
        "version": spec.version,
        "path": str(registry.get_strategy_path(spec.name, spec.version)),
    }


@router.get("/health")
async def lab_health():
    """Health check for Lab API."""
    registry = get_registry()
    strategies = registry.list_strategies()
    
    return {
        "status": "ok",
        "strategies_count": len(strategies),
        "strategies": [s["name"] for s in strategies],
    }


# =============================================================================
# BACKTEST ENDPOINTS
# =============================================================================

class BacktestRequest(BaseModel):
    """Request for running a backtest."""
    strategy_name: str
    strategy_version: Optional[str] = None
    start_date: str  # ISO format: YYYY-MM-DD
    end_date: str
    initial_capital: float = 25000.0
    symbols: Optional[list[str]] = None


@router.post("/backtest")
async def run_backtest(request: BacktestRequest):
    """Run a backtest for a strategy.
    
    Returns the full BacktestResult with trades, metrics, and equity curve.
    """
    from datetime import date as dt_date
    from decimal import Decimal
    from nexus2.domain.lab.strategy_registry import get_registry
    from nexus2.domain.lab.backtest_runner import get_backtest_runner
    
    registry = get_registry()
    strategy = registry.load_strategy(request.strategy_name, request.strategy_version)
    
    if not strategy:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy not found: {request.strategy_name}",
        )
    
    try:
        start = dt_date.fromisoformat(request.start_date)
        end = dt_date.fromisoformat(request.end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    
    runner = get_backtest_runner()
    result = runner.run(
        strategy=strategy,
        start_date=start,
        end_date=end,
        initial_capital=Decimal(str(request.initial_capital)),
        symbols=request.symbols,
    )
    
    return result.model_dump(mode="json")


class CompareRequest(BaseModel):
    """Request for comparing two strategies."""
    baseline_name: str
    baseline_version: Optional[str] = None
    variant_name: str
    variant_version: Optional[str] = None
    start_date: str
    end_date: str
    initial_capital: float = 25000.0


@router.post("/compare")
async def compare_strategies(request: CompareRequest):
    """Compare two strategies by running backtests and generating a comparison.
    
    Returns deltas, improvement score, and recommendation.
    """
    from datetime import date as dt_date
    from decimal import Decimal
    from nexus2.domain.lab.strategy_registry import get_registry
    from nexus2.domain.lab.backtest_runner import get_backtest_runner
    
    registry = get_registry()
    
    baseline = registry.load_strategy(request.baseline_name, request.baseline_version)
    if not baseline:
        raise HTTPException(status_code=404, detail=f"Baseline not found: {request.baseline_name}")
    
    variant = registry.load_strategy(request.variant_name, request.variant_version)
    if not variant:
        raise HTTPException(status_code=404, detail=f"Variant not found: {request.variant_name}")
    
    try:
        start = dt_date.fromisoformat(request.start_date)
        end = dt_date.fromisoformat(request.end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    
    runner = get_backtest_runner()
    capital = Decimal(str(request.initial_capital))
    
    # Run both backtests
    baseline_result = runner.run(baseline, start, end, capital)
    variant_result = runner.run(variant, start, end, capital)
    
    # Compare
    comparison = runner.compare(baseline_result, variant_result)
    
    return {
        "baseline": {
            "name": baseline.name,
            "version": baseline.version,
            "win_rate": baseline_result.metrics.win_rate,
            "avg_r": baseline_result.metrics.avg_r,
            "total_return": baseline_result.total_return,
            "trades": baseline_result.metrics.total_trades,
        },
        "variant": {
            "name": variant.name,
            "version": variant.version,
            "win_rate": variant_result.metrics.win_rate,
            "avg_r": variant_result.metrics.avg_r,
            "total_return": variant_result.total_return,
            "trades": variant_result.metrics.total_trades,
        },
        "deltas": {
            "win_rate": comparison.win_rate_delta,
            "avg_r": comparison.avg_r_delta,
            "total_return": comparison.total_return_delta,
            "max_dd": comparison.max_dd_delta,
        },
        "improvement_score": comparison.improvement_score,
        "recommendation": comparison.recommendation,
        "summary": comparison.summary,
    }


# =============================================================================
# AGENT ENDPOINTS (Phase 3)
# =============================================================================

class ResearchRequest(BaseModel):
    """Request for generating a hypothesis."""
    strategy_name: str
    strategy_version: Optional[str] = None
    evaluator_feedback: Optional[str] = None
    transcript_insights: list[str] = []


@router.post("/agents/research")
async def generate_hypothesis(request: ResearchRequest):
    """Generate a strategy improvement hypothesis using AI.
    
    The Researcher Agent analyzes the strategy and proposes improvements.
    """
    from nexus2.domain.lab.strategy_registry import get_registry
    from nexus2.domain.lab.researcher_agent import get_researcher_agent, ResearchContext
    
    registry = get_registry()
    strategy = registry.load_strategy(request.strategy_name, request.strategy_version)
    
    if not strategy:
        raise HTTPException(status_code=404, detail=f"Strategy not found: {request.strategy_name}")
    
    # Build context from strategy
    context = ResearchContext(
        strategy_name=strategy.name,
        strategy_version=strategy.version,
        rules_summary=strategy.description,
        evaluator_feedback=request.evaluator_feedback,
        transcript_insights=request.transcript_insights,
    )
    
    agent = get_researcher_agent()
    hypothesis = agent.propose(context)
    
    return hypothesis.model_dump(mode="json")


class CodeRequest(BaseModel):
    """Request for generating strategy code."""
    hypothesis: dict
    base_strategy_name: str
    base_strategy_version: Optional[str] = None
    new_strategy_name: str
    new_strategy_version: str


@router.post("/agents/code")
async def generate_code(request: CodeRequest):
    """Generate strategy code from a hypothesis.
    
    The Coder Agent creates scanner, engine, monitor, and tests.
    """
    from nexus2.domain.lab.strategy_registry import get_registry
    from nexus2.domain.lab.coder_agent import get_coder_agent
    import yaml
    
    registry = get_registry()
    base = registry.load_strategy(request.base_strategy_name, request.base_strategy_version)
    
    if not base:
        raise HTTPException(status_code=404, detail=f"Base strategy not found: {request.base_strategy_name}")
    
    # Convert base strategy to YAML
    base_config = yaml.dump(base.model_dump(mode="json"), default_flow_style=False)
    
    agent = get_coder_agent()
    code = agent.generate(
        hypothesis=request.hypothesis,
        base_config=base_config,
        strategy_name=request.new_strategy_name,
        strategy_version=request.new_strategy_version,
    )
    
    return {
        "strategy_name": code.strategy_name,
        "strategy_version": code.strategy_version,
        "is_valid": code.is_valid,
        "validation_errors": code.validation_errors,
        "files": {
            "config_yaml": code.config_yaml[:500] + "..." if len(code.config_yaml) > 500 else code.config_yaml,
            "scanner_py": f"{len(code.scanner_py)} bytes",
            "engine_py": f"{len(code.engine_py)} bytes",
            "monitor_py": f"{len(code.monitor_py)} bytes",
            "tests_py": f"{len(code.tests_py)} bytes",
        },
    }


class EvaluateRequest(BaseModel):
    """Request for evaluating backtest results."""
    baseline_metrics: dict
    variant_metrics: dict


@router.post("/agents/evaluate")
async def evaluate_results(request: EvaluateRequest):
    """Evaluate experiment results against baseline.
    
    Returns deltas, improvement score, and recommendation.
    """
    from nexus2.domain.lab.evaluator_agent import get_evaluator_agent
    
    agent = get_evaluator_agent()
    result = agent.evaluate(request.baseline_metrics, request.variant_metrics)
    
    return result.model_dump(mode="json")


# =============================================================================
# ORCHESTRATOR ENDPOINT (Phase 4)
# =============================================================================

class ExperimentRequest(BaseModel):
    """Request for running a full experiment."""
    base_strategy_name: str
    base_strategy_version: Optional[str] = None
    start_date: str  # YYYY-MM-DD
    end_date: str
    initial_capital: float = 25000.0
    max_iterations: int = 5
    promotion_threshold: float = 0.6
    transcript_insights: list[str] = []


@router.post("/experiment")
async def run_experiment(request: ExperimentRequest):
    """Run a full experiment loop.
    
    Orchestrates: Researcher → Coder → Backtest → Evaluator
    Loops until promotion or max_iterations.
    """
    from datetime import date as dt_date
    from decimal import Decimal
    from nexus2.domain.lab.orchestrator import get_orchestrator, ExperimentConfig
    
    try:
        start = dt_date.fromisoformat(request.start_date)
        end = dt_date.fromisoformat(request.end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    
    config = ExperimentConfig(
        base_strategy_name=request.base_strategy_name,
        base_strategy_version=request.base_strategy_version,
        start_date=start,
        end_date=end,
        initial_capital=Decimal(str(request.initial_capital)),
        max_iterations=request.max_iterations,
        promotion_threshold=request.promotion_threshold,
        transcript_insights=request.transcript_insights,
    )
    
    orchestrator = get_orchestrator()
    result = orchestrator.run_experiment(config)
    
    return result.model_dump(mode="json")


@router.get("/cache/status")
async def lab_cache_status():
    """Get cache status for Lab API."""
    from nexus2.domain.lab.historical_loader import get_historical_loader
    
    loader = get_historical_loader()
    cache_dir = loader.cache_dir
    cache_files = list(cache_dir.glob("*.json")) if cache_dir.exists() else []
    
    return {
        "status": "ok",
        "cache_dir": str(cache_dir),
        "cache_files": len(cache_files),
    }


@router.delete("/cache/clear")
async def clear_cache():
    """Clear all cached historical data.
    
    Use this when you need fresh data from FMP.
    """
    from nexus2.domain.lab.historical_loader import get_historical_loader
    
    loader = get_historical_loader()
    count = loader.clear_cache()
    
    return {
        "status": "cleared",
        "files_deleted": count,
    }
