@echo off
setlocal
set "GRECIS_ROOT=%~dp0"

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

echo [GRECIS] Starting the Python corpus API...
start "GRECIS Python Corpus API" cmd /k "cd /d ""%GRECIS_ROOT%"" && uv run grecis-web"

echo [GRECIS] Starting the reading dashboard...
start "GRECIS Reading Dashboard" cmd /k "cd /d ""%GRECIS_ROOT%dashboard"" && if not exist node_modules npm ci && npm run dev"

echo [GRECIS] Waiting for both local services...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$deadline = (Get-Date).AddSeconds(90);" ^
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
  echo [GRECIS] Startup timed out. Check the two service terminals for details.
  pause
  exit /b 1
)

echo [GRECIS] Ready. Opening http://localhost:3000/
start "" "http://localhost:3000/"
exit /b 0
