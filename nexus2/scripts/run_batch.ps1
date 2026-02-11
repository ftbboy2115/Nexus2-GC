# Run Warrior batch simulation and display formatted results
# Usage: .\nexus2\scripts\run_batch.ps1
# Usage with specific cases: .\nexus2\scripts\run_batch.ps1 -CaseIds "ross_rolr_20260114,ross_gri_20260128"

param(
    [string]$CaseIds = "",
    [string]$Host = "http://100.113.178.7:8000",
    [int]$Timeout = 900
)

if ($CaseIds) {
    $idArray = ($CaseIds -split ",") | ForEach-Object { "`"$($_.Trim())`"" }
    $body = "{`"case_ids`": [$($idArray -join ',')]}"
} else {
    $body = "{}"
}

Write-Output "Running batch simulation..."
Write-Output ""

$r = Invoke-RestMethod -Uri "$Host/warrior/sim/run_batch_concurrent" -Method Post -ContentType "application/json" -Body $body -TimeoutSec $Timeout

$r.results | ForEach-Object {
    $status = if ($_.total_pnl -gt 0) { "✅" } elseif ($_.total_pnl -lt 0) { "❌" } else { "⬜" }
    Write-Output "$status $($_.case_id): `$$($_.total_pnl) (Ross: `$$($_.ross_pnl)) [$($_.runtime_seconds)s]"
}

Write-Output ""
Write-Output "--- SUMMARY ---"
Write-Output "Total P&L: `$$($r.summary.total_pnl)"
Write-Output "Ross Total: `$$($r.summary.total_ross_pnl)"
Write-Output "Profitable: $($r.summary.cases_profitable)/$($r.summary.cases_run)"
Write-Output "Errors: $($r.summary.cases_with_errors)"
Write-Output "Runtime: $($r.summary.runtime_seconds)s"
