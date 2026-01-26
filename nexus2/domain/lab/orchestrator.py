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
    max_iterations: int = Field(default=5, ge=1, le=20)
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
        
        # Iteration loop
        evaluator_feedback: Optional[str] = None
        best_score = 0.0
        best_iteration = None
        tried_approaches: list = []  # Track what was already tried for diversity
        stagnant_count = 0  # Track how many iterations with no improvement
        last_score = 0.0
        
        for iteration in range(1, config.max_iterations + 1):
            logger.info(f"[Orchestrator] === Iteration {iteration}/{config.max_iterations} ===")
            iter_start = datetime.utcnow()
            
            iter_result = IterationResult(iteration=iteration)
            
            try:
                # Detect if stuck (no improvement for 2+ iterations)
                exploration_mode = stagnant_count >= 2
                if exploration_mode:
                    logger.info(f"[Orchestrator] Exploration mode activated after {stagnant_count} stagnant iterations")
                
                # 1. Research: Generate hypothesis
                context = ResearchContext(
                    strategy_name=baseline.name,
                    strategy_version=baseline.version,
                    win_rate=baseline_result.metrics.win_rate,
                    avg_r=baseline_result.metrics.avg_r,
                    max_drawdown=baseline_result.metrics.max_drawdown,
                    total_trades=baseline_result.metrics.total_trades,
                    rules_summary=baseline.description,
                    evaluator_feedback=evaluator_feedback,
                    transcript_insights=config.transcript_insights,
                    tried_approaches=tried_approaches,  # Pass history for diversity
                    exploration_mode=exploration_mode,  # Enable bold suggestions when stuck
                )
                
                hypothesis = self.researcher.propose(context)
                iter_result.hypothesis = hypothesis.model_dump(mode="json")
                logger.info(f"[Orchestrator] Hypothesis [{hypothesis.category}]: {hypothesis.hypothesis[:100]}...")
                
                # 2. Code: Generate strategy
                base_config = yaml.dump(baseline.model_dump(mode="json"), default_flow_style=False)
                
                variant_name = f"lab_{baseline.name}_v{iteration}"
                variant_version = f"{iteration}.0.0"
                
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
                # Merge with baseline defaults to handle missing/None fields
                try:
                    variant_config = yaml.safe_load(code.config_yaml) or {}
                    
                    # Helper to merge config dicts, filtering out None values
                    def merge_config(base_dict: dict, variant_dict: dict) -> dict:
                        result = base_dict.copy()
                        for key, value in variant_dict.items():
                            if value is not None:  # Only override if not None
                                result[key] = value
                        return result
                    
                    # Merge each config section with baseline
                    scanner_merged = merge_config(
                        baseline.scanner.model_dump(), 
                        variant_config.get("scanner", {})
                    )
                    engine_merged = merge_config(
                        baseline.engine.model_dump(), 
                        variant_config.get("engine", {})
                    )
                    monitor_merged = merge_config(
                        baseline.monitor.model_dump(), 
                        variant_config.get("monitor", {})
                    )
                    
                    variant_strategy = StrategySpec(
                        name=variant_name,
                        version=variant_version,
                        description=hypothesis.hypothesis[:200],
                        based_on=baseline.name,
                        based_on_version=baseline.version,
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
                           f"{variant_result.metrics.win_rate:.1f}% win rate")
                
                # 4. Evaluate: Score and get feedback
                evaluation = self.evaluator.evaluate(baseline_metrics, iter_result.metrics)
                iter_result.evaluation = evaluation.model_dump()
                iter_result.recommendation = evaluation.recommendation
                
                logger.info(f"[Orchestrator] Evaluation: {evaluation.summary}")
                
                # Track best
                if evaluation.improvement_score > best_score:
                    best_score = evaluation.improvement_score
                    best_iteration = iteration
                
                # Check promotion
                if evaluation.improvement_score >= config.promotion_threshold:
                    logger.info(f"[Orchestrator] Promotion threshold met! Score: {evaluation.improvement_score:.2f}")
                    result.promoted_strategy = variant_name
                    result.final_recommendation = "promote"
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
