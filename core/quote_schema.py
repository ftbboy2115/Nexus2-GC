"""
File: /core/quote_schema.py
Version: 1.0.0
Author: Nexus Project (Clay + Copilot)

Purpose:
    Minimal, provider‑agnostic Quote object.
    This defines the canonical data contract for all providers.
    Every provider must return a Quote instance with these fields.

    This schema matches the normalized Alpaca output exactly.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class Quote:
    symbol: str

    bid_price: float
    bid_size: int
    bid_exchange: str

    ask_price: float
    ask_size: int
    ask_exchange: str

    conditions: List[str]
    timestamp: str
    tape: str