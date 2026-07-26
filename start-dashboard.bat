@echo off
setlocal
set "GRECIS_ROOT=%~dp0"
set "GRECIS_RUNTIME=%~dp0output\dashboard"

where uv >nul 2>&1
if errorlevel 1 (
  echo [GRECIS] uv was not found. Install uv and try again.
  pause
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo [GRECIS] npm was not found. Install Node.js 22.13 or newer and try again.
  pause
  exit /b 1
)

if not exist "%GRECIS_ROOT%dashboard\node_modules" (
  echo [GRECIS] Installing frontend dependencies...
  pushd "%GRECIS_ROOT%dashboard"
  call npm ci
  if errorlevel 1 (
    popd
    echo [GRECIS] Frontend dependency installation failed.
    pause
    exit /b 1
  )
  popd
)

call "%GRECIS_ROOT%stop-dashboard.bat" --quiet >nul 2>&1
if not exist "%GRECIS_RUNTIME%" mkdir "%GRECIS_RUNTIME%"

echo [GRECIS] Starting both services quietly...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$root = '%GRECIS_ROOT%';" ^
  "$runtime = '%GRECIS_RUNTIME%';" ^
  "$backend = Start-Process -FilePath 'uv' -ArgumentList @('run','grecis-web') -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput ($runtime + '\backend.out.log') -RedirectStandardError ($runtime + '\backend.err.log') -PassThru;" ^
  "$backend.Id | Set-Content -Encoding ascii ($runtime + '\backend.pid');" ^
  "$frontend = Start-Process -FilePath 'npm.cmd' -ArgumentList @('run','dev') -WorkingDirectory ($root + 'dashboard') -WindowStyle Hidden -RedirectStandardOutput ($runtime + '\frontend.out.log') -RedirectStandardError ($runtime + '\frontend.err.log') -PassThru;" ^
  "$frontend.Id | Set-Content -Encoding ascii ($runtime + '\frontend.pid')"

if errorlevel 1 (
  echo [GRECIS] A service could not be started.
  pause
  exit /b 1
)

echo [GRECIS] Waiting for the corpus API and reading dashboard...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$deadline = (Get-Date).AddSeconds(120);" ^
  "$ready = $false;" ^
  "do {" ^
  "  try {" ^
  "    $api = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri 'http://127.0.0.1:8765/api/health';" ^
  "    $web = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri 'http://localhost:3000/';" ^
  "    $ready = ($api.StatusCode -eq 200 -and $web.StatusCode -eq 200);" ^
  "  } catch { Start-Sleep -Seconds 1 }" ^
  "} while (-not $ready -and (Get-Date) -lt $deadline);" ^
  "if (-not $ready) { exit 1 }"

if errorlevel 1 (
  call "%GRECIS_ROOT%stop-dashboard.bat" --quiet >nul 2>&1
  echo [GRECIS] Startup timed out. Logs are in output\dashboard.
  pause
  exit /b 1
)

if /i "%~1"=="--no-browser" (
  echo [GRECIS] Test mode ready.
  exit /b 0
)
echo [GRECIS] Ready. Opening http://localhost:3000/
start "" "http://localhost:3000/"
exit /b 0
