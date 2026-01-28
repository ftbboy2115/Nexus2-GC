#!/usr/bin/env python3
"""Test the new catalyst patterns against HIND headline - standalone."""
import re

# The new patterns we added
patterns = {
    "analyst_valuation": re.compile(
        r"\b(analyst\s+values?|price\s+target|price\s+objectiv|valuati?on\s+(of|at)|valued\s+at|worth\s+(?:\$|USD)?\s*[\d.]+\s*(?:billion|million)|rating\s+upgrade|initiates?\s+(?:buy|outperform)|upgrade[sd]?\s+to\s+(?:buy|strong\s+buy|outperform))\b",
        re.IGNORECASE,
    ),
    "clinical_advance": re.compile(
        r"\b(advance[sd]?\s+(?:into|to)\s+(?:phase|pivotal)|phase\s+(?:3|iii|three)\s+(?:study|trial|program)|pivotal\s+(?:study|trial)|phase\s+[1-3]\s+(?:initiation|enrollment|dosing|completion)|first\s+patient\s+(?:dosed|enrolled)|topline\s+(?:data|results))\b",
        re.IGNORECASE,
    ),
    "significant_value": re.compile(
        r"\b(?:\$|USD|EUR|GBP)\s*[\d.]+\s*(?:billion|bn|b)\b|\b[\d.]+\s*(?:billion|bn)\s*(?:dollar|usd|valuation|deal|agreement|contract)\b",
        re.IGNORECASE,
    ),
}

headlines = [
    "Independent Analyst Values Vyome's VT-1953 at USD 1 Billion Upon Successful Completion of Phase 3 Study",
    "Vyome (NASDAQ:HIND) versus Medline (NASDAQ:MDLN) Critical Review",
    "Vyome Holdings Shares Halted On Circuit Breaker To The Downside",
]

print("Testing new patterns against HIND headlines:\n")
for h in headlines:
    matches = []
    for name, pattern in patterns.items():
        if pattern.search(h):
            matches.append(name)
    
    status = "✅ PASS" if matches else "❌ FAIL"
    match_str = ", ".join(matches) if matches else "none"
    print(f"{status} | Matches: {match_str:30} | {h[:55]}...")
