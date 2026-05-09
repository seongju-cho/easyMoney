@echo off
setlocal EnableExtensions

set "VENV=.venv"
set "VPY=%VENV%\Scripts\python.exe"

if not exist "%VPY%" (
    echo .venv not found. Run run_backtest.bat once first to set up.
    exit /b 1
)

"%VPY%" -m src.analyze --config config.yaml %*
endlocal
