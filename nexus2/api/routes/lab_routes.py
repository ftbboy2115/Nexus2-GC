"""
Lab API Routes - Strategy management endpoints.

Provides REST API for the R&D Lab:
- List strategies
- Get strategy details
- Create new strategy versions
"""

import logging
import threading
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from nexus2.domain.lab import StrategySpec
from nexus2.domain.lab.strategy_registry import get_registry



logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lab", tags=["lab"])


# =============================================================================
# EXPERIMENT STATE TRACKING (for async experiments)
# =============================================================================

# Global dict to track running/completed experiments
_experiments: Dict[str, Dict[str, Any]] = {}
_experiments_lock = threading.Lock()


def _get_experiment(experiment_id: str) -> Optional[Dict[str, Any]]:
    """Get experiment state by ID."""
    with _experiments_lock:
        return _experiments.get(experiment_id)


def _set_experiment(experiment_id: str, state: Dict[str, Any]) -> None:
    """Set experiment state."""
    with _experiments_lock:
        _experiments[experiment_id] = state


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
    max_iterations: int = 10
    promotion_threshold: float = 0.6
    transcript_insights: list[str] = []


@router.post("/experiment")
async def run_experiment(request: ExperimentRequest):
    """Run a full experiment loop asynchronously.
    
    Returns an experiment_id immediately. Poll /experiment/{id}/status for results.
    Orchestrates: Researcher → Coder → Backtest → Evaluator
    Loops until promotion or max_iterations.
    """
    from datetime import date as dt_date
    from decimal import Decimal
    
    try:
        start = dt_date.fromisoformat(request.start_date)
        end = dt_date.fromisoformat(request.end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    
    # Generate experiment ID
    experiment_id = str(uuid.uuid4())[:8]
    
    # Store initial state
    _set_experiment(experiment_id, {
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
        "strategy": request.base_strategy_name,
        "current_iteration": 0,
        "max_iterations": request.max_iterations,
        "result": None,
        "error": None,
    })
    
    # Run experiment in background thread
    def run_in_background():
        from nexus2.domain.lab.orchestrator import get_orchestrator, ExperimentConfig
        
        try:
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
            
            # Progress callback to update current_iteration
            def on_progress(current: int, total: int):
                state = _get_experiment(experiment_id)
                if state:
                    state["current_iteration"] = current
                    _set_experiment(experiment_id, state)
            
            result = orchestrator.run_experiment(config, progress_callback=on_progress)
            
            # Update state with result
            _set_experiment(experiment_id, {
                "status": "completed",
                "started_at": _get_experiment(experiment_id)["started_at"],
                "completed_at": datetime.utcnow().isoformat(),
                "strategy": request.base_strategy_name,
                "current_iteration": request.max_iterations,
                "max_iterations": request.max_iterations,
                "result": result.model_dump(mode="json"),
                "error": None,
            })
        except Exception as e:
            logger.error(f"[Lab] Experiment {experiment_id} failed: {e}")
            _set_experiment(experiment_id, {
                "status": "failed",
                "started_at": _get_experiment(experiment_id)["started_at"],
                "completed_at": datetime.utcnow().isoformat(),
                "strategy": request.base_strategy_name,
                "current_iteration": 0,
                "max_iterations": request.max_iterations,
                "result": None,
                "error": str(e),
            })
    
    # Start background thread
    thread = threading.Thread(target=run_in_background, daemon=True)
    thread.start()
    
    # Return immediately with experiment ID
    return {
        "experiment_id": experiment_id,
        "status": "running",
        "message": f"Experiment started. Poll /lab/experiment/{experiment_id}/status for results.",
    }


@router.get("/experiment/{experiment_id}/status")
async def get_experiment_status(experiment_id: str):
    """Get the status of a running or completed experiment.
    
    Poll this endpoint until status is 'completed' or 'failed'.
    """
    state = _get_experiment(experiment_id)
    
    if not state:
        raise HTTPException(status_code=404, detail=f"Experiment not found: {experiment_id}")
    
    return state


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


# =============================================================================
# HISTORICAL BACKFILL ENDPOINT
# =============================================================================

class BackfillRequest(BaseModel):
    """Request for backfilling historical gappers."""
    days_back: int = Field(default=60, ge=7, le=180, description="Number of days to backfill")
    min_gap_percent: float = Field(default=5.0, ge=1.0, le=50.0, description="Minimum gap percentage")
    min_price: float = Field(default=1.0, ge=0.5, le=10.0, description="Minimum stock price")
    max_price: float = Field(default=20.0, ge=5.0, le=100.0, description="Maximum stock price")


@router.post("/history/backfill")
async def backfill_historical_gappers(request: BackfillRequest = None):
    """Backfill scan_history with historical gappers from FMP.
    
    Uses FMP API to find stocks that gapped significantly on past dates.
    Entries are tagged with source='backfill' to distinguish from real scans.
    
    This expands the Lab's backtest universe, allowing more meaningful experiments.
    """
    from datetime import date, timedelta
    from nexus2.domain.lab.historical_backfill import backfill_historical_gappers as do_backfill
    
    if request is None:
        request = BackfillRequest()
    
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=request.days_back)
    
    logger.info(f"[Lab] Starting backfill from {start_date} to {end_date}")
    
    try:
        stats = await do_backfill(
            start_date=start_date,
            end_date=end_date,
            min_gap_percent=request.min_gap_percent,
            min_price=request.min_price,
            max_price=request.max_price,
        )
        
        logger.info(f"[Lab] Backfill complete: {stats}")
        
        return {
            "status": "complete",
            **stats,
        }
        
    except Exception as e:
        logger.exception(f"[Lab] Backfill failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/stats")
async def get_scan_history_stats():
    """Get statistics about the scan history.
    
    Shows how many dates/symbols are available for backtesting.
    """
    from nexus2.domain.lab.scan_history_logger import get_scan_history_logger
    
    history = get_scan_history_logger()
    stats = history.get_stats()
    
    # Count by source
    backfill_count = 0
    scan_count = 0
    for date_entries in history._history.values():
        for entry in date_entries:
            source = entry.get("source", "scan")
            if source == "backfill":
                backfill_count += 1
            else:
                scan_count += 1
    
    stats["backfill_entries"] = backfill_count
    stats["scan_entries"] = scan_count
    
    return stats

