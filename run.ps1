# MidPnP Studio launcher
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Error "Python not found. Install Python 3.10+ and add it to PATH."
}

if (-not (Test-Path -LiteralPath "midpnp")) {
    Write-Error "midpnp package not found. Run this script from the project root."
}

& $python.Source -m midpnp @args
exit $LASTEXITCODE
