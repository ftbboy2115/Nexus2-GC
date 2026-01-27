"""
Additional News Sources

Yahoo Finance and Finviz headline fetchers for catalyst detection.
Supplements FMP and Alpaca/Benzinga in unified.py.
"""

import logging
from typing import List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def get_yahoo_headlines(symbol: str, days: int = 5) -> List[str]:
    """
    Get recent news headlines from Yahoo Finance via yfinance.
    
    Args:
        symbol: Stock symbol
        days: Days to look back (filtering done client-side)
        
    Returns:
        List of headline strings
    """
    try:
        import yfinance as yf
        
        ticker = yf.Ticker(symbol)
        news = ticker.news  # Returns list of dicts with 'title', 'publisher', 'providerPublishTime', etc.
        
        if not news:
            return []
        
        headlines = []
        cutoff_ts = (datetime.now() - timedelta(days=days)).timestamp()
        
        for item in news:
            # Filter by date if timestamp available
            publish_time = item.get("providerPublishTime", 0)
            if publish_time < cutoff_ts:
                continue
            
            title = item.get("title", "").strip()
            if title:
                headlines.append(title)
        
        logger.debug(f"[Yahoo] {symbol}: Found {len(headlines)} headlines")
        return headlines
        
    except ImportError:
        logger.warning("[Yahoo] yfinance not installed - run: pip install yfinance")
        return []
    except Exception as e:
        logger.debug(f"[Yahoo] {symbol}: Error - {e}")
        return []


def get_finviz_headlines(symbol: str, limit: int = 10) -> List[str]:
    """
    Get recent news headlines from Finviz via finvizfinance.
    
    Args:
        symbol: Stock symbol
        limit: Max headlines to return
        
    Returns:
        List of headline strings
    """
    try:
        from finvizfinance.quote import finvizfinance
        
        stock = finvizfinance(symbol)
        news_df = stock.ticker_news()
        
        if news_df is None or news_df.empty:
            return []
        
        # news_df has columns: Date, Title, Link
        headlines = news_df["Title"].head(limit).tolist()
        
        logger.debug(f"[Finviz] {symbol}: Found {len(headlines)} headlines")
        return headlines
        
    except ImportError:
        logger.warning("[Finviz] finvizfinance not installed - run: pip install finvizfinance")
        return []
    except Exception as e:
        logger.debug(f"[Finviz] {symbol}: Error - {e}")
        return []


def get_all_headlines(symbol: str, days: int = 5) -> List[str]:
    """
    Get headlines from all additional sources (Yahoo + Finviz).
    
    Returns deduplicated list of headlines.
    """
    headlines_set = set()
    headlines_list = []
    
    # Yahoo Finance
    for h in get_yahoo_headlines(symbol, days):
        normalized = h.strip().lower()
        if normalized and normalized not in headlines_set:
            headlines_set.add(normalized)
            headlines_list.append(h.strip())
    
    # Finviz
    for h in get_finviz_headlines(symbol):
        normalized = h.strip().lower()
        if normalized and normalized not in headlines_set:
            headlines_set.add(normalized)
            headlines_list.append(h.strip())
    
    return headlines_list
