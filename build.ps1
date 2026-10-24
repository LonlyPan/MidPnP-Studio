# MidPnP Studio Windows build script
# Output: dist\MidPnPStudio\MidPnPStudio.exe and release\MidPnPStudio-v0.1.0-win64.zip
param(
    [switch]$SkipTests,
    [switch]$SkipSmoke
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

Write-Host "==> Generate application icon" -ForegroundColor Cyan
python tools\make_icon.py
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed" }

if (-not $SkipTests) {
    Write-Host "==> Run unit tests" -ForegroundColor Cyan
    python -m unittest discover -s tests -q
    if ($LASTEXITCODE -ne 0) { throw "Unit tests failed" }
}

Write-Host "==> PyInstaller build" -ForegroundColor Cyan
$exclude = @(
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtSensors",
    "PySide6.QtSerialBus", "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtStateMachine",
    "PySide6.QtTest", "PySide6.QtSql", "PySide6.QtDBus", "PySide6.QtDesigner", "PySide6.QtHelp",
    "tkinter", "unittest"
)
$arguments = @(
    "-m", "PyInstaller",
    "--noconfirm", "--clean", "--windowed", "--onedir",
    "--name", "MidPnPStudio",
    "--icon", "assets\midpnp.ico",
    "--version-file", "assets\version_info.txt",
    "--paths", ".",
    "--hidden-import", "serial",
    "--hidden-import", "serial.tools.list_ports",
    "--add-data", "midpnp\data;midpnp\data"
)
foreach ($module in $exclude) {
    $arguments += @("--exclude-module", $module)
}
$arguments += "main.py"
& python @arguments
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

Write-Host "==> Assemble release directory" -ForegroundColor Cyan
Copy-Item -LiteralPath "README.md" -Destination "dist\MidPnPStudio\README.md" -Force
if (Test-Path "docs") {
    Copy-Item -LiteralPath "docs" -Destination "dist\MidPnPStudio\docs" -Recurse -Force
}
New-Item -ItemType Directory -Force -Path "release" | Out-Null
$zip = "release\MidPnPStudio-v0.2.0-win64.zip"
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path "dist\MidPnPStudio\*" -DestinationPath $zip -CompressionLevel Optimal

if (-not $SkipSmoke) {
    Write-Host "==> Startup smoke test" -ForegroundColor Cyan
    $smokeData = Join-Path $PSScriptRoot "build-smoke"
    if (Test-Path -LiteralPath $smokeData) { Remove-Item -LiteralPath $smokeData -Recurse -Force }
    $exe = Join-Path $PSScriptRoot "dist\MidPnPStudio\MidPnPStudio.exe"
    $process = Start-Process -FilePath $exe -ArgumentList @("--smoke-test", "--data-dir", "`"$smokeData`"") -PassThru -Wait
    if ($process.ExitCode -ne 0) { throw "Packaged app smoke test failed" }
    Write-Host "==> Smoke test passed" -ForegroundColor Green
}

Write-Host ""
Write-Host "Build complete:" -ForegroundColor Green
Write-Host "  dist\MidPnPStudio\MidPnPStudio.exe"
Write-Host "  $zip"
exit 0
