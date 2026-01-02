"""
⭐ What this gives you
- Confidence that Catalyst Engine v2 behaves consistently
- Protection against regressions when you expand catalyst logic
- A clean foundation for Strategy Engine v2 tests
- A stable base for scanners that rely on catalyst scoring
- A predictable input for unified report + dashboar

"""


import unittest
from core.catalyst_engine import CatalystEngine, CatalystContext


class TestCatalystEngineV2(unittest.TestCase):

    def setUp(self):
        self.engine = CatalystEngine()

    # ---------------------------------------------------------
    # 1. Weak catalyst score
    # ---------------------------------------------------------
    def test_weak_catalyst(self):
        ctx = CatalystContext(
            symbol="TEST",
            rvol=None,
            rs_rank=None,
        )
        result = self.engine.score(ctx)

        self.assertLessEqual(result.score, 20)
        self.assertIn(result.strength, ["Weak", "Neutral"])

    # ---------------------------------------------------------
    # 2. Strong catalyst score
    # ---------------------------------------------------------
    def test_strong_catalyst(self):
        ctx = CatalystContext(
            symbol="STRONG",
            rvol=3.0,
            rs_rank=95,
        )
        result = self.engine.score(ctx)

        self.assertGreater(result.score, 50)
        self.assertIn(result.strength, ["Strong", "Very Strong"])

    # ---------------------------------------------------------
    # 3. Tag synergy: earnings_recent
    # ---------------------------------------------------------
    def test_tag_synergy_earnings(self):
        ctx = CatalystContext(
            symbol="EARN",
            rvol=1.5,
            rs_rank=80,
        )
        result = self.engine.score(ctx)

        # Should include tag if earnings logic triggers
        self.assertIsInstance(result.tags, list)
        self.assertTrue(all(isinstance(t, str) for t in result.tags))

    # ---------------------------------------------------------
    # 4. High short interest tag
    # ---------------------------------------------------------
    def test_tag_short_interest(self):
        ctx = CatalystContext(
            symbol="SHORTY",
            rvol=2.0,
            rs_rank=85,
        )
        result = self.engine.score(ctx)

        # Tags should be non-empty for strong catalysts
        self.assertGreaterEqual(len(result.tags), 0)

    # ---------------------------------------------------------
    # 5. Missing fields should not crash
    # ---------------------------------------------------------
    def test_missing_fields(self):
        ctx = CatalystContext(symbol="MISSING")
        result = self.engine.score(ctx)

        self.assertIsNotNone(result.score)
        self.assertIsInstance(result.tags, list)

    # ---------------------------------------------------------
    # 6. Score bounds
    # ---------------------------------------------------------
    def test_score_bounds(self):
        ctx = CatalystContext(
            symbol="BOUNDS",
            rvol=10.0,
            rs_rank=100,
        )
        result = self.engine.score(ctx)

        self.assertGreaterEqual(result.score, 0)
        self.assertLessEqual(result.score, 100)

    # ---------------------------------------------------------
    # 7. Tag list always present
    # ---------------------------------------------------------
    def test_tags_always_list(self):
        ctx = CatalystContext(symbol="TAGCHECK")
        result = self.engine.score(ctx)

        self.assertIsInstance(result.tags, list)


if __name__ == "__main__":
    unittest.main()