@echo off
setlocal EnableExtensions

REM ---- Self-bootstrapping one-shot runner (Windows) ----
REM Usage:  run_backtest.bat [--refresh] [--config other.yaml] [--clean]

set "VENV=.venv"
set "VPY=%VENV%\Scripts\python.exe"

REM --clean: nuke venv and rebuild
if /I "%~1"=="--clean" (
    echo [setup] Removing existing venv...
    if exist "%VENV%" rmdir /S /Q "%VENV%"
    shift
)

REM 1) Pick a Python to bootstrap with. Prefer py launcher (3.13 -> 3.12 -> 3.11 -> 3.10 -> any 3.x)
set "PY="
where py >nul 2>nul
if %errorlevel%==0 (
    for %%V in (3.13 3.12 3.11 3.10) do (
        if not defined PY (
            py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
        )
    )
    if not defined PY set "PY=py -3"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python not found. Install Python 3.10-3.13 from https://www.python.org/downloads/
        exit /b 1
    )
    set "PY=python"
)

echo [setup] Bootstrap Python: %PY%
%PY% -c "import sys; print('         version:', sys.version.split()[0])"

REM 2) Create venv if missing
if not exist "%VPY%" (
    echo [setup] Creating venv at %VENV% ...
    %PY% -m venv "%VENV%"
    if errorlevel 1 (
        echo [ERROR] venv creation failed.
        exit /b 1
    )
)

REM 3) Verify deps; install if any missing. Use venv python DIRECTLY (no activate).
"%VPY%" -c "import pandas, numpy, requests, yaml, matplotlib, tabulate" 2>nul
if errorlevel 1 (
    echo [setup] Installing requirements into venv...
    "%VPY%" -m pip install --upgrade pip
    "%VPY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ERROR] pip install failed.
        echo   Tip: if you are on Python 3.14+, some packages may not have wheels yet.
        echo   Install Python 3.13 from https://www.python.org/downloads/ and rerun:
        echo       run_backtest.bat --clean
        exit /b 1
    )
    "%VPY%" -c "import pandas, numpy, requests, yaml, matplotlib, tabulate" 2>nul
    if errorlevel 1 (
        echo.
        echo [ERROR] Dependencies still missing after install.
        echo   Try: run_backtest.bat --clean
        exit /b 1
    )
)

REM 4) Run the backtest with venv python
"%VPY%" -m src.main --config config.yaml %*
endlocal
