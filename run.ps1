# MidPnP Studio launcher
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# 优先使用项目内虚拟环境（存在时），避免污染全局 Python
$venv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venv) {
    $exe = $venv
} else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Write-Error "Python not found. Install Python 3.10+ and add it to PATH, or create .venv first."
    }
    $exe = $python.Source
}

if (-not (Test-Path -LiteralPath "midpnp")) {
    Write-Error "midpnp package not found. Run this script from the project root."
}

& $exe -m midpnp @args
exit $LASTEXITCODE
