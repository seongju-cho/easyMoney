@echo off
if not exist .venv (
    echo .venv not found. Run setup.bat first.
    exit /b 1
)
call .venv\Scripts\activate.bat
python -m src.main --config config.yaml %*
