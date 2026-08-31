$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    $PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PythonLauncher) {
        & $PythonLauncher.Source -3.11 -m venv .venv
    } else {
        $PythonExe = Get-Command python -ErrorAction Stop
        & $PythonExe.Source -m venv .venv
    }
}
& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "RTSP-Snapshot-FTP" `
    --icon "assets\camera-icon.ico" `
    --add-data "assets\camera-icon.ico;assets" `
    --collect-all cv2 `
    rtsp_ftp_app.py

Write-Host "EXE creato in: $ProjectDir\dist\RTSP-Snapshot-FTP.exe"
