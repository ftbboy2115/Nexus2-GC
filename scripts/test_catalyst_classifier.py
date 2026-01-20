"""Test updated catalyst classifier with VERO headline - standalone version."""
import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class CatalystMatch:
    headline: str
    catalyst_type: Optional[str]
    confidence: float
    is_positive: bool

# Updated acquisition pattern (matches catalyst_classifier.py update)
acquisition_pattern = re.compile(
    r"\b(acquires?|acquisition|acquired|merger|takeover|buyout|buys?\s+\d+%|agree\s+to\s+(buy|acquire)|definitive\s+agreement|takes?\s+control|major\s+investor|activist\s+investor|significant\s+stake|controlling\s+(interest|stake)|board\s+seats?|proxy\s+(fight|battle|contest)|new\s+ownership|change\s+of\s+control)\b",
    re.IGNORECASE,
)

positive_sentiment = re.compile(
    r"\b(soars?|jumps?|surges?|spikes?|gains?|rallies|skyrockets?|explodes?)\b",
    re.IGNORECASE,
)

# Original VERO headline
headline = "Venus Concept Stock Explodes Over 500% After Major Investor Takes Control"

print(f"Headline: {headline}")
print()

# Test acquisition pattern
if acquisition_pattern.search(headline):
    print("✅ Matches ACQUISITION pattern (confidence 0.9)")
    match = acquisition_pattern.search(headline)
    print(f"   Matched: '{match.group()}'")
else:
    print("❌ No acquisition match")

# Test sentiment pattern
if positive_sentiment.search(headline):
    print("⚠️  Also matches positive_sentiment (but acquisition takes priority)")
    match = positive_sentiment.search(headline)
    print(f"   Matched: '{match.group()}'")

print()
print("=" * 60)
print("Additional Tests:")
print("=" * 60)

test_headlines = [
    "Company Shares Surge as Activist Investor Takes Board Seat",
    "Stock Jumps on News of Significant Stake Acquired by Hedge Fund",
    "XYZ Corp Soars After Change of Control Announcement",
    "Shares Rally as New Ownership Group Takes Over",
    "Stock Spikes on Proxy Fight Win by Activist",
]

for h in test_headlines:
    match = acquisition_pattern.search(h)
    if match:
        print(f"✅ acquisition (0.9) | Matched: '{match.group()}'")
    elif positive_sentiment.search(h):
        print(f"❌ sentiment  (0.5) | {h[:50]}...")
    else:
        print(f"❌ no match         | {h[:50]}...")
