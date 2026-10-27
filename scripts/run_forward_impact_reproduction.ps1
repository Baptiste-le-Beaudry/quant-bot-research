$ErrorActionPreference = "Stop"

$outputDir = "docs/forward_paper/impact_reproduction"
$symbols = @(
    "BTCETH", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
    "LINKUSDT", "LTCUSDT", "SOLUSDT_TRANSFER"
)

foreach ($symbol in $symbols) {
    python scripts/reproduce_adopted_portfolio.py `
        --symbol $symbol `
        --max-folds 999 `
        --out-dir $outputDir
    if ($LASTEXITCODE -ne 0) {
        throw "Reproduction failed for $symbol with exit code $LASTEXITCODE"
    }
}
