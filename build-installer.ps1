$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

& "$ProjectDir\build.ps1"

$MakeNsis = Get-Command makensis.exe -ErrorAction SilentlyContinue
if (-not $MakeNsis) {
    $Candidates = @(
        "$env:ProgramFiles\NSIS\makensis.exe",
        "${env:ProgramFiles(x86)}\NSIS\makensis.exe",
        "$env:LOCALAPPDATA\Programs\NSIS\makensis.exe"
    )
    $MakeNsisPath = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
} else {
    $MakeNsisPath = $MakeNsis.Source
}
if (-not $MakeNsisPath) {
    throw "NSIS non trovato. Installarlo con: winget install --id NSIS.NSIS -e"
}
& $MakeNsisPath /V2 installer.nsi
Write-Host "Installer creato in: $ProjectDir\outputs\RTSP-Snapshot-FTP-Setup.exe"
