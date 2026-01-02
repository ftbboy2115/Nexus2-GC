"""Test breakout scanner with relaxed settings."""

from nexus2.domain.scanner.breakout_scanner_service import BreakoutScannerService, BreakoutScanSettings

# Relaxed settings to see what passes
settings = BreakoutScanSettings(
    min_rs_percentile=50,      # Lowered from 70
    tightness_threshold=1.0,   # Accept any tightness
    volume_contraction=1.0,    # Accept any volume
)

scanner = BreakoutScannerService(settings)
result = scanner.scan(verbose=True)

print(f"\nFound {len(result.candidates)} candidates")
for c in result.candidates[:10]:
    print(f"  {c.symbol}: {c.status.value}, tight={float(c.tightness_score):.2f}, vol={float(c.volume_ratio):.2f}, rs={c.rs_percentile}")
