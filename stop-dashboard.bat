@echo off
setlocal EnableDelayedExpansion
set "GRECIS_RUNTIME=%~dp0output\dashboard"

for %%N in (frontend backend) do (
  if exist "%GRECIS_RUNTIME%\%%N.pid" (
    set "GRECIS_PID="
    set /p GRECIS_PID=<"%GRECIS_RUNTIME%\%%N.pid"
    if defined GRECIS_PID taskkill /PID !GRECIS_PID! /T /F >nul 2>&1
    del /q "%GRECIS_RUNTIME%\%%N.pid" >nul 2>&1
  )
)

if /i not "%~1"=="--quiet" echo [GRECIS] Dashboard services stopped.
exit /b 0
