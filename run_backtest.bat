@echo off
setlocal

REM ---- Self-bootstrapping one-shot runner (Windows) ----
REM Usage:  run_backtest.bat [--refresh] [--config other.yaml]

where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python not found. Install Python 3.10+ from https://www.python.org/downloads/
        exit /b 1
    )
    set "PY=python"
)

if not exist .venv (
    echo [setup] Creating virtual environment...
    %PY% -m venv .venv || ( echo [ERROR] venv creation failed & exit /b 1 )
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip >nul
    echo [setup] Installing requirements...
    pip install -r requirements.txt || ( echo [ERROR] pip install failed & exit /b 1 )
) else (
    call .venv\Scripts\activate.bat
    REM cheap sentinel: install only if pandas import fails
    python -c "import pandas, numpy, requests, yaml, matplotlib, tabulate" >nul 2>nul
    if errorlevel 1 (
        echo [setup] Repairing missing dependencies...
        pip install -r requirements.txt || ( echo [ERROR] pip install failed & exit /b 1 )
    )
)

python -m src.main --config config.yaml %*
endlocal
