"""
Researcher Agent - LLM-powered hypothesis generation.

Analyzes trade forensics and transcript insights to propose
strategy improvements for testing.
"""

import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


# =============================================================================
# MODELS
# =============================================================================

class Hypothesis(BaseModel):
    """Strategy improvement hypothesis from Researcher Agent."""
    
    hypothesis: str = Field(..., description="Specific change description")
    rationale: str = Field(..., description="Why this should improve performance")
    parameter_changes: Dict[str, Any] = Field(default_factory=dict, description="Proposed changes")
    expected_impact: str = Field(default="", description="Expected improvement")
    risk: str = Field(default="", description="What could go wrong")
    confidence: float = Field(default=0.5, description="Agent confidence 0-1")
    category: str = Field(default="unknown", description="Change category for diversity tracking")
    
    # Metadata
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    source: str = Field(default="researcher_agent", description="Origin of hypothesis")


class ResearchContext(BaseModel):
    """Context data for the Researcher Agent."""
    
    # Strategy info
    strategy_name: str
    strategy_version: str
    
    # Performance metrics
    win_rate: float = Field(default=0.0)
    avg_r: float = Field(default=0.0)
    max_drawdown: float = Field(default=0.0)
    total_trades: int = Field(default=0)
    
    # Trade patterns
    trade_summary: str = Field(default="")
    losing_patterns: List[str] = Field(default_factory=list)
    winning_patterns: List[str] = Field(default_factory=list)
    
    # External insights
    transcript_insights: List[str] = Field(default_factory=list)
    evaluator_feedback: Optional[str] = Field(default=None)
    
    # Strategy rules summary
    rules_summary: str = Field(default="")
    
    # Diversity tracking - what was already tried
    tried_approaches: List[Dict[str, Any]] = Field(default_factory=list)
    exploration_mode: bool = Field(default=False)


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

RESEARCHER_SYSTEM_PROMPT = """You are a trading strategy researcher for short-term equity trading.
You work with the Nexus 2 automated trading platform.

CONTEXT:
- Asset class: US equities (NYSE, NASDAQ, AMEX, ARCA - NO OTC/Pink Sheets)
- Timeframe: Intraday to multi-day (primary focus: 9:30 AM - 4:00 PM ET)
- Open to any strategy type that fits the platform's capabilities
- Known methodologies for reference: Ross Cameron (Warrior), Kristjan Kullamägi (KK)
- NOT limited to momentum - may explore mean reversion, news-based, statistical, etc.

YOUR ROLE:
- Analyze trade history and identify patterns in wins/losses
- Study transcript insights from successful traders
- Propose specific, testable improvements to existing strategies
- Always explain your rationale and potential risks

DIVERSITY REQUIREMENT:
When previous attempts are listed, you MUST propose a DIFFERENT category of change.
Change categories (rotate through these):
1. entry_criteria - Entry triggers, breakout thresholds, confirmation requirements
2. exit_logic - Profit targets, trailing stops, time-based exits
3. stop_placement - Stop distance, ATR multiples, technical levels
4. position_sizing - Risk per trade, scaling rules, max position
5. time_filters - Time-of-day restrictions, session focus
6. symbol_filters - Volume, price, float, sector requirements

OUTPUT FORMAT:
Always respond with valid JSON matching this schema:
{
  "hypothesis": "specific change description",
  "rationale": "why this should improve performance",
  "parameter_changes": {"param_name": "new_value"},
  "expected_impact": "+X% win rate or +Y avg R",
  "risk": "what could go wrong",
  "confidence": 0.0-1.0,
  "category": "one of: entry_criteria, exit_logic, stop_placement, position_sizing, time_filters, symbol_filters"
}"""


def build_researcher_prompt(context: ResearchContext) -> str:
    """Build the full prompt for the Researcher Agent."""
    
    prompt_parts = [
        f"CURRENT STRATEGY: {context.strategy_name} v{context.strategy_version}",
        "",
        "PERFORMANCE METRICS:",
        f"- Win Rate: {context.win_rate:.1f}%",
        f"- Average R: {context.avg_r:.2f}",
        f"- Max Drawdown: {context.max_drawdown:.1f}%",
        f"- Total Trades: {context.total_trades}",
        "",
    ]
    
    if context.rules_summary:
        prompt_parts.extend([
            "CURRENT RULES:",
            context.rules_summary,
            "",
        ])
    
    if context.trade_summary:
        prompt_parts.extend([
            "TRADE ANALYSIS:",
            context.trade_summary,
            "",
        ])
    
    if context.losing_patterns:
        prompt_parts.extend([
            "LOSING PATTERNS (fix these):",
            *[f"- {p}" for p in context.losing_patterns],
            "",
        ])
    
    if context.winning_patterns:
        prompt_parts.extend([
            "WINNING PATTERNS (reinforce these):",
            *[f"- {p}" for p in context.winning_patterns],
            "",
        ])
    
    if context.transcript_insights:
        prompt_parts.extend([
            "TRANSCRIPT INSIGHTS (from expert traders):",
            *[f"- {t}" for t in context.transcript_insights],
            "",
        ])
    
    if context.evaluator_feedback:
        prompt_parts.extend([
            "PREVIOUS ITERATION FEEDBACK:",
            context.evaluator_feedback,
            "",
        ])
    
    # Diversity enforcement - show what was already tried
    if context.tried_approaches:
        tried_categories = [t.get("category", "unknown") for t in context.tried_approaches]
        prompt_parts.extend([
            "⚠️ ALREADY TRIED (you MUST choose a DIFFERENT category):",
            *[f"- Iter {t.get('iteration', '?')}: [{t.get('category', 'unknown')}] {t.get('description', '')[:80]}" 
              for t in context.tried_approaches],
            "",
            f"Categories already used: {', '.join(set(tried_categories))}",
            "Pick from UNUSED categories: entry_criteria, exit_logic, stop_placement, position_sizing, time_filters, symbol_filters",
            "",
        ])
    
    # Exploration mode - when stuck, encourage bold changes
    if context.exploration_mode:
        prompt_parts.extend([
            "🔬 EXPLORATION MODE ACTIVATED:",
            "Previous approaches haven't worked. Try a FUNDAMENTALLY DIFFERENT approach.",
            "Consider: different entry type, different exit strategy, time-based rules, or structural changes.",
            "",
        ])
    
    prompt_parts.extend([
        "TASK:",
        "Propose ONE specific, testable hypothesis to improve this strategy.",
        "Focus on the most impactful change based on the data above.",
        "",
        "Respond with valid JSON only."
    ])
    
    return "\n".join(prompt_parts)


# =============================================================================
# RESEARCHER AGENT
# =============================================================================

class ResearcherAgent:
    """LLM-powered strategy research agent.
    
    Uses Gemini to analyze trade data and propose improvements.
    """
    
    def __init__(self):
        self._client = None
    
    def _get_client(self):
        """Lazy-load Gemini client.
        
        Uses GEMINI_LAB_KEY if available, falls back to GEMINI_API_KEY.
        """
        if self._client is None:
            try:
                from dotenv import load_dotenv
                load_dotenv()
                import os
                from google import genai
                
                # Prefer dedicated lab key, fall back to shared key
                api_key = os.environ.get("GEMINI_LAB_KEY") or os.environ.get("GEMINI_API_KEY")
                if not api_key:
                    raise ValueError("GEMINI_LAB_KEY or GEMINI_API_KEY not set")
                
                # Add timeout to prevent hanging requests (60 seconds)
                from google.genai import types
                self._client = genai.Client(
                    api_key=api_key,
                    http_options=types.HttpOptions(timeout=60000)  # 60 second timeout
                )
                logger.info(f"[ResearcherAgent] Using {'GEMINI_LAB_KEY' if os.environ.get('GEMINI_LAB_KEY') else 'GEMINI_API_KEY'}")
            except Exception as e:
                logger.error(f"[ResearcherAgent] Failed to init Gemini client: {e}")
                raise
        return self._client
    
    def propose(self, context: ResearchContext) -> Hypothesis:
        """Generate a hypothesis for strategy improvement.
        
        Args:
            context: Research context with strategy info and trade data
            
        Returns:
            Hypothesis with proposed changes
        """
        logger.info(f"[ResearcherAgent] Generating hypothesis for {context.strategy_name}")
        
        user_prompt = build_researcher_prompt(context)
        
        try:
            client = self._get_client()
            
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    {"role": "user", "parts": [{"text": RESEARCHER_SYSTEM_PROMPT}]},
                    {"role": "model", "parts": [{"text": "I understand. I will analyze trading strategies and propose specific, testable improvements. I will respond with valid JSON only."}]},
                    {"role": "user", "parts": [{"text": user_prompt}]},
                ],
            )
            
            # Parse JSON response
            response_text = response.text.strip()
            
            # Handle markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])
            
            data = json.loads(response_text)
            
            return Hypothesis(
                hypothesis=data.get("hypothesis", ""),
                rationale=data.get("rationale", ""),
                parameter_changes=data.get("parameter_changes", {}),
                expected_impact=data.get("expected_impact", ""),
                risk=data.get("risk", ""),
                confidence=data.get("confidence", 0.5),
                category=data.get("category", "unknown"),
                source="gemini-2.0-flash",
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"[ResearcherAgent] Failed to parse response: {e}")
            return Hypothesis(
                hypothesis="Parse error - invalid JSON response",
                rationale=f"Raw response: {response_text[:200]}",
                risk="Agent response was not valid JSON",
                confidence=0.0,
            )
        except Exception as e:
            logger.error(f"[ResearcherAgent] Error: {e}")
            return Hypothesis(
                hypothesis=f"Error: {str(e)}",
                rationale="Agent failed to generate hypothesis",
                risk="Unknown error",
                confidence=0.0,
            )
    
    def propose_from_feedback(
        self,
        strategy_name: str,
        strategy_version: str,
        backtest_result: Dict[str, Any],
        feedback: str,
    ) -> Hypothesis:
        """Generate hypothesis from backtest feedback.
        
        Convenience method for the iterative loop.
        """
        context = ResearchContext(
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            win_rate=backtest_result.get("metrics", {}).get("win_rate", 0),
            avg_r=backtest_result.get("metrics", {}).get("avg_r", 0),
            max_drawdown=backtest_result.get("metrics", {}).get("max_drawdown", 0),
            total_trades=backtest_result.get("metrics", {}).get("total_trades", 0),
            evaluator_feedback=feedback,
        )
        return self.propose(context)


# Singleton
_agent: Optional[ResearcherAgent] = None


def get_researcher_agent() -> ResearcherAgent:
    """Get the singleton researcher agent."""
    global _agent
    if _agent is None:
        _agent = ResearcherAgent()
    return _agent
