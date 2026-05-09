@echo off
REM Create venv and install dependencies (Windows)
where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install Python 3.10+ from https://www.python.org/downloads/
    exit /b 1
)

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Activating venv and installing requirements...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Setup complete. Run backtest with: run_backtest.bat
