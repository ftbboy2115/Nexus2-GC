"""
Trade Analysis Service

AI-powered analysis of completed trades for post-trade review.
Uses Gemini to analyze trade timeline from Trade Event Log.
"""

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from nexus2.db.database import get_session
from nexus2.db.models import TradeEventModel

logger = logging.getLogger(__name__)


# =============================================================================
# AI ANALYSIS RESULT
# =============================================================================

@dataclass
class TradeAnalysis:
    """Result of AI trade analysis."""
    position_id: str
    strategy: str  # NAC or WARRIOR
    symbol: str
    
    # Grades (A/B/C/D/F)
    entry_grade: str
    exit_grade: str
    management_grade: str
    overall_grade: str
    
    # Narrative
    summary: str
    what_went_well: List[str]
    lessons_learned: List[str]
    
    # Market context summary
    market_conditions: str
    
    # Metadata
    analyzed_at: datetime
    event_count: int
    
    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "strategy": self.strategy,
            "symbol": self.symbol,
            "grades": {
                "entry": self.entry_grade,
                "exit": self.exit_grade,
                "management": self.management_grade,
                "overall": self.overall_grade,
            },
            "summary": self.summary,
            "what_went_well": self.what_went_well,
            "lessons_learned": self.lessons_learned,
            "market_conditions": self.market_conditions,
            "analyzed_at": self.analyzed_at.isoformat(),
            "event_count": self.event_count,
        }


# =============================================================================
# ANALYSIS PROMPTS
# =============================================================================

WARRIOR_SYSTEM_PROMPT = """You are a trading coach analyzing a completed day trade using Ross Cameron's Warrior Trading methodology.

WARRIOR TRADING CRITERIA:
- Entry: Should be on ORB breakout, flag breakout, or ABCD pattern
- Stop: Mental stop (opening range low or flag low), technical stop (trailing)
- Target: 2:1 R minimum for first partial, let runners run
- Partials: Take 50% at 2R, move stop to breakeven, trail remainder
- Time: Avoid trading after 11am unless strong setup

MARKET CONTEXT FACTORS:
- SPY direction affects momentum stocks
- VIX > 20 = choppy conditions, tighter stops
- SPY down > 1% = risk-off, be selective

GRADING SCALE:
- A: Followed methodology perfectly
- B: Minor deviations, still profitable approach
- C: Some rule violations but understandable
- D: Significant rule violations
- F: Complete methodology failure

Analyze the trade timeline and provide honest, actionable feedback."""

NAC_SYSTEM_PROMPT = """You are a trading coach analyzing a completed swing trade using Kristjan Kullamägi (Qullamaggie) methodology.

KK-STYLE CRITERIA:
- Entry: Episodic Pivot (EP), breakout from tight consolidation, or High-Tight Flag (HTF)
- Stop: ATR-based (≤1.0 ATR), below consolidation low
- Target: 3-5R or let it run based on setup strength
- Partials: Day 3-5 rule for taking initial profits
- Hold time: Days to weeks for strong setups

MARKET CONTEXT FACTORS:
- Market trend alignment is critical
- Relative strength vs SPY matters
- VIX > 25 = challenging environment

GRADING SCALE:
- A: Followed methodology perfectly
- B: Minor deviations, still profitable approach
- C: Some rule violations but understandable
- D: Significant rule violations
- F: Complete methodology failure

Analyze the trade timeline and provide honest, actionable feedback."""

ANALYSIS_USER_PROMPT = """Analyze this {strategy} trade:

## TRADE TIMELINE
{timeline}

## TRADE SUMMARY
- Symbol: {symbol}
- Entry: ${entry_price} on {entry_date}
- Exit: ${exit_price} on {exit_date}
- P&L: ${pnl}
- Duration: {duration}

## MARKET CONDITIONS
{market_conditions}

---

Respond in this EXACT JSON format:
{{
  "entry_grade": "A/B/C/D/F",
  "exit_grade": "A/B/C/D/F",
  "management_grade": "A/B/C/D/F",
  "overall_grade": "A/B/C/D/F",
  "summary": "2-3 sentence overall assessment",
  "what_went_well": ["point 1", "point 2"],
  "lessons_learned": ["lesson 1", "lesson 2"],
  "market_conditions_impact": "How market conditions affected this trade"
}}"""


# =============================================================================
# TRADE ANALYSIS SERVICE
# =============================================================================

class TradeAnalysisService:
    """Service for AI-powered trade analysis."""
    
    def __init__(self, api_key: Optional[str] = None):
        import os
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self._client = None
        self._model = "gemini-2.5-flash-lite"  # Fast enough for analysis
    
    def _get_client(self):
        """Lazy initialization of Gemini client."""
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except ImportError:
                logger.error("google-genai package not installed")
                raise
        return self._client
    
    def _get_events_for_position(self, position_id: str) -> List[Dict]:
        """Fetch all trade events for a position."""
        with get_session() as db:
            events = (
                db.query(TradeEventModel)
                .filter(TradeEventModel.position_id == position_id)
                .order_by(TradeEventModel.created_at)
                .all()
            )
            return [e.to_dict() for e in events]
    
    def _build_timeline(self, events: List[Dict]) -> str:
        """Convert events to human-readable timeline."""
        lines = []
        for event in events:
            time_str = event["created_at"][:16] if event["created_at"] else "?"
            event_type = event["event_type"]
            reason = event.get("reason", "")
            
            # Format based on event type
            if "ENTRY" in event_type:
                lines.append(f"[{time_str}] ENTRY: {reason}")
            elif "STOP" in event_type:
                old = event.get("old_value", "?")
                new = event.get("new_value", "?")
                lines.append(f"[{time_str}] STOP MOVED: ${old} → ${new} ({reason})")
            elif "PARTIAL" in event_type:
                lines.append(f"[{time_str}] PARTIAL EXIT: {reason}")
            elif "BREAKEVEN" in event_type:
                lines.append(f"[{time_str}] BREAKEVEN: Stop moved to entry")
            elif "EXIT" in event_type:
                lines.append(f"[{time_str}] EXIT: {reason}")
            elif "SCALE" in event_type:
                lines.append(f"[{time_str}] SCALE IN: {reason}")
            else:
                lines.append(f"[{time_str}] {event_type}: {reason}")
        
        return "\n".join(lines)
    
    def _extract_market_context(self, events: List[Dict]) -> str:
        """Extract market context from event metadata."""
        contexts = []
        
        for event in events:
            metadata = event.get("metadata", {})
            if not metadata:
                continue
            
            spy_price = metadata.get("spy_price")
            spy_change = metadata.get("spy_change_pct")
            vix = metadata.get("vix")
            
            if spy_price or spy_change or vix:
                event_type = event.get("event_type", "?")
                parts = []
                if spy_change is not None:
                    parts.append(f"SPY {spy_change:+.1f}%")
                if vix:
                    parts.append(f"VIX={vix:.1f}")
                if parts:
                    contexts.append(f"At {event_type}: {', '.join(parts)}")
        
        return "\n".join(contexts) if contexts else "No market context recorded"
    
    def _extract_trade_summary(self, events: List[Dict]) -> Dict:
        """Extract summary info from events."""
        summary = {
            "symbol": events[0].get("symbol", "?") if events else "?",
            "strategy": events[0].get("strategy", "?") if events else "?",
            "entry_price": "?",
            "exit_price": "?",
            "entry_date": "?",
            "exit_date": "?",
            "pnl": "?",
        }
        
        for event in events:
            event_type = event.get("event_type", "")
            metadata = event.get("metadata", {})
            
            if "ENTRY" in event_type:
                summary["entry_price"] = metadata.get("entry_price", event.get("new_value", "?"))
                summary["entry_date"] = event.get("created_at", "?")[:10]
            
            if "EXIT" in event_type and "PARTIAL" not in event_type:
                summary["exit_price"] = metadata.get("exit_price", event.get("new_value", "?"))
                summary["exit_date"] = event.get("created_at", "?")[:10]
                summary["pnl"] = metadata.get("pnl", "?")
        
        return summary
    
    def analyze_trade(self, position_id: str) -> Optional[TradeAnalysis]:
        """Analyze a completed trade using AI."""
        
        # 1. Fetch events
        events = self._get_events_for_position(position_id)
        if not events:
            logger.warning(f"No events found for position {position_id}")
            return None
        
        # 2. Build context
        strategy = events[0].get("strategy", "WARRIOR")
        timeline = self._build_timeline(events)
        market_context = self._extract_market_context(events)
        summary = self._extract_trade_summary(events)
        
        # Calculate duration
        if summary["entry_date"] != "?" and summary["exit_date"] != "?":
            try:
                entry_dt = datetime.fromisoformat(summary["entry_date"])
                exit_dt = datetime.fromisoformat(summary["exit_date"])
                duration = f"{(exit_dt - entry_dt).days} days"
            except:
                duration = "?"
        else:
            duration = "?"
        
        # 3. Build prompt
        system_prompt = WARRIOR_SYSTEM_PROMPT if strategy == "WARRIOR" else NAC_SYSTEM_PROMPT
        user_prompt = ANALYSIS_USER_PROMPT.format(
            strategy=strategy,
            timeline=timeline,
            symbol=summary["symbol"],
            entry_price=summary["entry_price"],
            entry_date=summary["entry_date"],
            exit_price=summary["exit_price"],
            exit_date=summary["exit_date"],
            pnl=summary["pnl"],
            duration=duration,
            market_conditions=market_context,
        )
        
        # 4. Call AI
        try:
            client = self._get_client()
            
            response = client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config={
                    "system_instruction": system_prompt,
                    "temperature": 0.3,  # Some creativity for insights
                    "max_output_tokens": 500,
                },
            )
            
            raw = response.text.strip() if response.text else ""
            
            # 5. Parse response
            # Extract JSON from response (may have markdown wrapper)
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0].strip()
            
            result = json.loads(raw)
            
            return TradeAnalysis(
                position_id=position_id,
                strategy=strategy,
                symbol=summary["symbol"],
                entry_grade=result.get("entry_grade", "?"),
                exit_grade=result.get("exit_grade", "?"),
                management_grade=result.get("management_grade", "?"),
                overall_grade=result.get("overall_grade", "?"),
                summary=result.get("summary", ""),
                what_went_well=result.get("what_went_well", []),
                lessons_learned=result.get("lessons_learned", []),
                market_conditions=result.get("market_conditions_impact", ""),
                analyzed_at=datetime.utcnow(),
                event_count=len(events),
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response: {e}")
            return None
        except Exception as e:
            logger.error(f"Trade analysis failed: {e}")
            return None


# =============================================================================
# SINGLETON
# =============================================================================

_analysis_service: Optional[TradeAnalysisService] = None


def get_trade_analysis_service() -> TradeAnalysisService:
    """Get or create singleton analysis service."""
    global _analysis_service
    if _analysis_service is None:
        _analysis_service = TradeAnalysisService()
    return _analysis_service
