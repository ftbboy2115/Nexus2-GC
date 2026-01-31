"""
Catalyst Search Service

Search cached headlines for keywords.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class CatalystSearchResult:
    """Single search result."""
    symbol: str
    headline: str
    source: Optional[str] = None
    timestamp: Optional[str] = None
    catalyst_type: Optional[str] = None
    match_score: float = 0.0


class CatalystSearchService:
    """Search catalyst headlines from cache."""
    
    def __init__(self, data_dir: Path = None):
        # Path: nexus2/domain/automation/catalyst_search_service.py
        # Data is at repo root: Nexus2/data/ (4 levels up from this file)
        self.data_dir = data_dir or Path(__file__).parent.parent.parent.parent / "data"
        self.headline_cache_path = self.data_dir / "headline_cache.json"
        self._cache: Dict[str, List[dict]] = {}
        self._cache_loaded_at: Optional[datetime] = None
    
    def _load_cache(self, force: bool = False) -> Dict[str, List[dict]]:
        """Load headline cache from disk."""
        # Reload if file was modified or forced
        if not force and self._cache:
            return self._cache
        
        if not self.headline_cache_path.exists():
            logger.warning(f"Headline cache not found: {self.headline_cache_path}")
            return {}
        
        try:
            with open(self.headline_cache_path, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
            self._cache_loaded_at = datetime.now()
            logger.info(f"Loaded headline cache: {len(self._cache)} symbols")
            return self._cache
        except Exception as e:
            logger.error(f"Failed to load headline cache: {e}")
            return {}
    
    def search(
        self,
        query: str,
        symbols: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[CatalystSearchResult]:
        """
        Search headlines for a query string.
        
        Args:
            query: Search term (case-insensitive)
            symbols: Optional list of symbols to filter
            limit: Max results to return
            
        Returns:
            List of matching headlines
        """
        cache = self._load_cache()
        if not cache:
            return []
        
        results = []
        query_lower = query.lower()
        query_pattern = re.compile(re.escape(query), re.IGNORECASE)
        
        for symbol, headlines in cache.items():
            # Filter by symbols if specified
            if symbols and symbol not in symbols:
                continue
            
            for headline_obj in headlines:
                text = headline_obj.get("text", "")
                if not text:
                    continue
                
                # Check for match
                if query_pattern.search(text):
                    # Calculate basic match score (higher = better)
                    # Exact word match scores higher than substring
                    word_match = bool(re.search(rf"\b{re.escape(query)}\b", text, re.IGNORECASE))
                    score = 1.0 if word_match else 0.5
                    
                    results.append(CatalystSearchResult(
                        symbol=symbol,
                        headline=text,
                        source=headline_obj.get("source"),
                        timestamp=headline_obj.get("timestamp"),
                        catalyst_type=headline_obj.get("catalyst_type"),
                        match_score=score,
                    ))
        
        # Sort by score descending, then by symbol
        results.sort(key=lambda x: (-x.match_score, x.symbol))
        
        return results[:limit]
    
    def get_symbols_with_catalyst_type(self, catalyst_type: str) -> List[str]:
        """Get all symbols that have a specific catalyst type."""
        cache = self._load_cache()
        symbols = []
        
        for symbol, headlines in cache.items():
            for headline_obj in headlines:
                if headline_obj.get("catalyst_type") == catalyst_type:
                    symbols.append(symbol)
                    break
        
        return sorted(set(symbols))
    
    def get_recent_catalysts(self, limit: int = 20) -> List[CatalystSearchResult]:
        """Get most recent catalysts from cache."""
        cache = self._load_cache()
        results = []
        
        for symbol, headlines in cache.items():
            for headline_obj in headlines:
                text = headline_obj.get("text", "")
                if text:
                    results.append(CatalystSearchResult(
                        symbol=symbol,
                        headline=text,
                        source=headline_obj.get("source"),
                        timestamp=headline_obj.get("timestamp"),
                        catalyst_type=headline_obj.get("catalyst_type"),
                    ))
        
        # Sort by timestamp if available
        results.sort(key=lambda x: x.timestamp or "", reverse=True)
        return results[:limit]
    
    def get_stats(self) -> Dict:
        """Get stats about the catalyst cache."""
        cache = self._load_cache()
        
        total_headlines = sum(len(h) for h in cache.values())
        
        # Count catalyst types
        type_counts: Dict[str, int] = {}
        for headlines in cache.values():
            for h in headlines:
                cat_type = h.get("catalyst_type", "unknown")
                type_counts[cat_type] = type_counts.get(cat_type, 0) + 1
        
        return {
            "total_symbols": len(cache),
            "total_headlines": total_headlines,
            "catalyst_types": type_counts,
            "cache_loaded_at": self._cache_loaded_at.isoformat() if self._cache_loaded_at else None,
        }


# Singleton instance
_service: Optional[CatalystSearchService] = None


def get_catalyst_search_service() -> CatalystSearchService:
    """Get or create singleton service."""
    global _service
    if _service is None:
        _service = CatalystSearchService()
    return _service
