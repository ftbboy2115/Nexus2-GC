"""
Lab Orchestrator - Coordinates the full experiment loop.

Ties together:
1. Researcher Agent → generates hypothesis
2. Coder Agent → generates strategy code
3. Backtest Runner → tests the strategy
4. Evaluator Agent → scores results, provides feedback

Loops until promotion threshold or max iterations.
"""

import logging
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
from pydantic import BaseModel, Field

from .strategy_registry import get_registry
from .researcher_agent import get_researcher_agent, ResearchContext, Hypothesis
from .coder_agent import get_coder_agent, GeneratedCode
from .backtest_runner import get_backtest_runner, BacktestResult
from .evaluator_agent import get_evaluator_agent, EvaluationResult
from .strategy_schema import StrategySpec, ScannerConfig, EngineConfig, MonitorConfig
from .lab_logger import configure_lab_logging
from nexus2.db.warrior_db import get_recent_closed_trades
import yaml


logger = logging.getLogger(__name__)


# =============================================================================
# MODELS
# =============================================================================

class ExperimentConfig(BaseModel):
    """Configuration for an experiment run."""
    
    # Base strategy
    base_strategy_name: str
    base_strategy_version: Optional[str] = None
    
    # Backtest parameters
    start_date: date
    end_date: date
    initial_capital: Decimal = Decimal("25000")
    
    # Loop control
    max_iterations: int = Field(default=10, ge=1, le=20)
    promotion_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    
    # External context
    transcript_insights: List[str] = Field(default_factory=list)
    
    class Config:
        json_encoders = {Decimal: str, date: lambda v: v.isoformat()}


class IterationResult(BaseModel):
    """Result of a single iteration."""
    
    iteration: int
    hypothesis: Dict[str, Any] = Field(default_factory=dict)
    code_valid: bool = False
    validation_errors: List[str] = Field(default_factory=list)
    backtest_ran: bool = False
    metrics: Dict[str, Any] = Field(default_factory=dict)
    evaluation: Dict[str, Any] = Field(default_factory=dict)
    recommendation: str = ""
    duration_seconds: float = 0.0


class ExperimentResult(BaseModel):
    """Result of a full experiment run."""
    
    experiment_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    # Config
    base_strategy: str
    base_version: str
    
    # Results
    iterations: List[IterationResult] = Field(default_factory=list)
    total_iterations: int = 0
    final_recommendation: str = ""
    
    # Best result
    best_iteration: Optional[int] = None
    best_score: float = 0.0
    promoted_strategy: Optional[str] = None
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


# =============================================================================
# ORCHESTRATOR
# =============================================================================

class LabOrchestrator:
    """Coordinates the full experiment loop.
    
    Flow:
    1. Load baseline strategy and run backtest
    2. Loop:
       a. Researcher generates hypothesis
       b. Coder generates code
       c. Validate code
       d. Run backtest
       e. Evaluate results
       f. If promoted threshold: stop
       g. Else: feed feedback back to researcher
    """
    
    def __init__(self):
        # Redirect all lab module logs to lab.log file
        configure_lab_logging()
        
        self.registry = get_registry()
        self.researcher = get_researcher_agent()
        self.coder = get_coder_agent()
        self.runner = get_backtest_runner()
        self.evaluator = get_evaluator_agent()
    
    def run_experiment(
        self,
        config: ExperimentConfig,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> ExperimentResult:
        """Run a full experiment loop.
        
        Args:
            config: Experiment configuration
            progress_callback: Optional callback(current_iteration, max_iterations) called after each iteration
            
        Returns:
            ExperimentResult with all iterations and final recommendation
        """
        experiment_id = str(uuid.uuid4())[:8]
        logger.info(f"[Orchestrator] Starting experiment {experiment_id}")
        
        result = ExperimentResult(
            experiment_id=experiment_id,
            base_strategy=config.base_strategy_name,
            base_version=config.base_strategy_version or "latest",
        )
        
        # Load baseline
        baseline = self.registry.load_strategy(
            config.base_strategy_name,
            config.base_strategy_version,
        )
        if not baseline:
            logger.error(f"[Orchestrator] Baseline not found: {config.base_strategy_name}")
            result.final_recommendation = "error: baseline not found"
            return result
        
        # Run baseline backtest
        logger.info(f"[Orchestrator] Running baseline backtest...")
        baseline_result = self.runner.run(
            baseline,
            config.start_date,
            config.end_date,
            config.initial_capital,
        )
        baseline_metrics = baseline_result.metrics.model_dump()
        baseline_metrics["total_return"] = baseline_result.total_return
        
        logger.info(f"[Orchestrator] Baseline: {baseline_result.metrics.total_trades} trades, "
                   f"{baseline_result.metrics.win_rate:.1f}% win rate")
        
        # Champion Evolution: Track the current best strategy
        # This gets promoted when a variant beats it
        current_champion = baseline
        champion_metrics = baseline_metrics.copy()
        champion_score = 0.0  # Baseline starts at score 0
        
        # Clean naming: lab_{base} with auto-incrementing versions
        # Strip any existing lab_ prefix to prevent nesting
        base_name = baseline.name.replace("lab_", "") if baseline.name.startswith("lab_") else baseline.name
        lab_strategy_name = f"lab_{base_name}"
        
        # Iteration loop
        evaluator_feedback: Optional[str] = None
        best_score = 0.0
        best_iteration = None
        tried_approaches: list = []  # Track what was already tried for diversity
        stagnant_count = 0  # Track how many iterations with no improvement
        last_score = 0.0
        
        # Load real trade data for Researcher analysis
        real_trades = []
        try:
            real_trades = get_recent_closed_trades(limit=30)
            logger.info(f"[Orchestrator] Loaded {len(real_trades)} real trades for analysis")
        except Exception as e:
            logger.warning(f"[Orchestrator] Could not load real trades: {e}")
        
        for iteration in range(1, config.max_iterations + 1):
            logger.info(f"[Orchestrator] === Iteration {iteration}/{config.max_iterations} ===")
            iter_start = datetime.utcnow()
            
            iter_result = IterationResult(iteration=iteration)
            
            try:
                # Detect if stuck (no improvement for 2+ iterations)
                exploration_mode = stagnant_count >= 2
                if exploration_mode:
                    logger.info(f"[Orchestrator] Exploration mode activated after {stagnant_count} stagnant iterations")
                
                # 1. Research: Generate hypothesis based on CURRENT CHAMPION (not fixed baseline)
                # Convert baseline trades to dicts for the researcher
                backtest_trades_data = [t.model_dump(mode="json") for t in baseline_result.trades]
                
                context = ResearchContext(
                    strategy_name=current_champion.name,
                    strategy_version=current_champion.version,
                    win_rate=champion_metrics.get("win_rate", 0),
                    avg_r=champion_metrics.get("avg_r", 0),
                    max_drawdown=champion_metrics.get("max_drawdown", 0),
                    total_trades=champion_metrics.get("total_trades", 0),
                    rules_summary=current_champion.description,
                    evaluator_feedback=evaluator_feedback,
                    transcript_insights=config.transcript_insights,
                    tried_approaches=tried_approaches,  # Pass history for diversity
                    exploration_mode=exploration_mode,  # Enable bold suggestions when stuck
                    real_trades=real_trades,  # Pass real trade data for analysis
                    backtest_trades=backtest_trades_data,  # Pass baseline backtest trades
                )
                
                hypothesis = self.researcher.propose(context)
                iter_result.hypothesis = hypothesis.model_dump(mode="json")
                logger.info(f"[Orchestrator] Hypothesis [{hypothesis.category}]: {hypothesis.hypothesis[:100]}...")
                
                # 2. Code: Generate strategy based on CURRENT CHAMPION
                base_config = yaml.dump(current_champion.model_dump(mode="json"), default_flow_style=False)
                
                # Clean naming: use fixed lab_strategy_name with iteration-based version
                variant_name = lab_strategy_name
                variant_version = f"0.{iteration}.0"  # Temp version; incremented on save
                
                code = self.coder.generate(
                    hypothesis=iter_result.hypothesis,
                    base_config=base_config,
                    strategy_name=variant_name,
                    strategy_version=variant_version,
                )
                
                iter_result.code_valid = code.is_valid
                iter_result.validation_errors = code.validation_errors
                
                if not code.is_valid:
                    logger.warning(f"[Orchestrator] Code validation failed: {code.validation_errors}")
                    evaluator_feedback = f"Code generation failed: {code.validation_errors}"
                    iter_result.recommendation = "iterate"
                    continue
                
                # 3. Backtest: Test the variant
                # Parse the generated config_yaml into a StrategySpec
                # Merge with current champion defaults to handle missing/None fields
                try:
                    variant_config = yaml.safe_load(code.config_yaml) or {}
                    
                    # Helper to merge config dicts, filtering out None values
                    def merge_config(base_dict: dict, variant_dict: dict) -> dict:
                        result = base_dict.copy()
                        for key, value in variant_dict.items():
                            if value is not None:  # Only override if not None
                                result[key] = value
                        return result
                    
                    # Merge each config section with CURRENT CHAMPION (not fixed baseline)
                    scanner_merged = merge_config(
                        current_champion.scanner.model_dump(), 
                        variant_config.get("scanner", {})
                    )
                    engine_merged = merge_config(
                        current_champion.engine.model_dump(), 
                        variant_config.get("engine", {})
                    )
                    monitor_merged = merge_config(
                        current_champion.monitor.model_dump(), 
                        variant_config.get("monitor", {})
                    )
                    
                    variant_strategy = StrategySpec(
                        name=variant_name,
                        version=variant_version,
                        description=hypothesis.hypothesis[:200],
                        based_on=current_champion.name,
                        based_on_version=current_champion.version,
                        scanner=ScannerConfig(**scanner_merged),
                        engine=EngineConfig(**engine_merged),
                        monitor=MonitorConfig(**monitor_merged),
                    )
                    logger.info(f"[Orchestrator] Using variant strategy: {variant_strategy.name}")
                except Exception as e:
                    logger.warning(f"[Orchestrator] Failed to parse variant config, using baseline: {e}")
                    variant_strategy = baseline
                
                variant_result = self.runner.run(
                    variant_strategy,
                    config.start_date,
                    config.end_date,
                    config.initial_capital,
                )
                
                iter_result.backtest_ran = True
                iter_result.metrics = variant_result.metrics.model_dump()
                iter_result.metrics["total_return"] = variant_result.total_return
                
                logger.info(f"[Orchestrator] Variant: {variant_result.metrics.total_trades} trades, "
                           f"{variant_result.metrics.win_rate*100:.1f}% win rate")
                
                # 4. Evaluate: Score and get feedback (compare vs original baseline for consistency)
                evaluation = self.evaluator.evaluate(baseline_metrics, iter_result.metrics)
                iter_result.evaluation = evaluation.model_dump()
                iter_result.recommendation = evaluation.recommendation
                
                logger.info(f"[Orchestrator] Evaluation: {evaluation.summary}")
                
                # Track best
                if evaluation.improvement_score > best_score:
                    best_score = evaluation.improvement_score
                    best_iteration = iteration
                
                # CHAMPION EVOLUTION: Promote variant to champion if it beats current champion
                if evaluation.improvement_score > champion_score:
                    logger.info(f"[Orchestrator] 🏆 New champion! {variant_strategy.name} beats previous with score {evaluation.improvement_score:.2f} > {champion_score:.2f}")
                    current_champion = variant_strategy
                    champion_metrics = iter_result.metrics.copy()
                    champion_score = evaluation.improvement_score
                    stagnant_count = 0  # Reset stagnation since we improved
                
                # Check final promotion threshold
                if evaluation.improvement_score >= config.promotion_threshold:
                    logger.info(f"[Orchestrator] Promotion threshold met! Score: {evaluation.improvement_score:.2f}")
                    result.promoted_strategy = variant_name
                    result.final_recommendation = "promote"
                    
                    # PERSIST the winning strategy to registry with auto-incrementing version
                    try:
                        next_version = self.registry.get_next_version(lab_strategy_name)
                        variant_strategy.name = lab_strategy_name
                        variant_strategy.version = next_version
                        
                        self.registry.save_strategy(variant_strategy)
                        logger.info(f"[Orchestrator] 💾 Saved promoted strategy: {variant_strategy.name} v{variant_strategy.version}")
                    except Exception as e:
                        logger.warning(f"[Orchestrator] Failed to save strategy: {e}")
                    
                    iter_result.duration_seconds = (datetime.utcnow() - iter_start).total_seconds()
                    result.iterations.append(iter_result)
                    break
                
                # Feed back for next iteration
                evaluator_feedback = evaluation.feedback
                
                # Track this approach for diversity
                tried_approaches.append({
                    "iteration": iteration,
                    "category": hypothesis.category,
                    "description": hypothesis.hypothesis[:100],
                })
                
                # Detect stagnation (no meaningful improvement)
                current_score = evaluation.improvement_score
                if abs(current_score - last_score) < 0.05:  # Less than 5% change
                    stagnant_count += 1
                else:
                    stagnant_count = 0  # Reset if we see change
                last_score = current_score
                
            except Exception as e:
                logger.error(f"[Orchestrator] Iteration {iteration} error: {e}")
                iter_result.recommendation = f"error: {str(e)}"
            
            iter_result.duration_seconds = (datetime.utcnow() - iter_start).total_seconds()
            result.iterations.append(iter_result)
            
            # Call progress callback
            if progress_callback:
                progress_callback(iteration, config.max_iterations)
        
        # Finalize result
        result.completed_at = datetime.utcnow()
        result.total_iterations = len(result.iterations)
        result.best_iteration = best_iteration
        result.best_score = best_score
        
        if not result.final_recommendation:
            if best_score >= 0.3:
                result.final_recommendation = "iterate"
            else:
                result.final_recommendation = "reject"
        
        # Save champion if it improved over baseline (even if didn't hit promotion threshold)
        if champion_score > 0 and current_champion != baseline:
            try:
                # Get next version number for this strategy (auto-increments)
                next_version = self.registry.get_next_version(lab_strategy_name)
                
                # Update champion with clean naming before save
                current_champion.name = lab_strategy_name
                current_champion.version = next_version
                
                self.registry.save_strategy(current_champion)
                logger.info(f"[Orchestrator] 💾 Saved best champion: {current_champion.name} v{current_champion.version} (score {champion_score:.2f})")
            except Exception as e:
                logger.warning(f"[Orchestrator] Failed to save champion: {e}")
        
        logger.info(f"[Orchestrator] Experiment complete: {result.final_recommendation}")
        return result


# Singleton
_orchestrator: Optional[LabOrchestrator] = None


def get_orchestrator() -> LabOrchestrator:
    """Get the singleton orchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = LabOrchestrator()
    return _orchestrator
