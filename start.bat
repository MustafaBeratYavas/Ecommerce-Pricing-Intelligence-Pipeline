@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

:: Bootstrap the local Windows environment and run the scraping pipeline.
echo [INFO] Starting E-Commerce Pricing Intelligence Pipeline setup and execution...

:: Verify Python is available before creating the project environment.
if not defined PYTHON_BIN set "PYTHON_BIN=python"
"%PYTHON_BIN%" --version >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not added to PATH.
    echo Please install Python 3.11+ and try again.
    pause
    exit /b 1
)

"%PYTHON_BIN%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Python 3.11+ is required.
    echo Please install Python 3.11+ and try again.
    pause
    exit /b 1
)

:: Create the virtual environment once and reuse it across runs.
if not exist ".venv" (
    echo [SETUP] Virtual environment not found. Creating...
    "%PYTHON_BIN%" -m venv .venv
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: Activate the isolated interpreter before installing or running modules.
echo [SETUP] Activating virtual environment...
call .venv\Scripts\activate.bat
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)

:: Install the project and runtime dependencies from pyproject.toml.
echo [SETUP] Checking and installing dependencies...
python -m pip install --upgrade pip >nul
python -m pip install .
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Failed to install project dependencies from pyproject.toml.
    echo Check your internet connection and pyproject.toml dependency declarations.
    pause
    exit /b 1
)

:: Initialize a persistent browser profile for repeatable scraper sessions.
echo [SETUP] Ensuring Chrome profile exists...
python -m src.tasks.create_profile
if !ERRORLEVEL! neq 0 (
    echo [ERROR] Failed to initialize browser profile.
    pause
    exit /b 1
)

:: Seed the queue from product_codes.txt before starting the batch processor.
if not defined SEED_FILE set "SEED_FILE=product_codes.txt"
if not exist "%SEED_FILE%" (
    echo [WARNING] Seed file '%SEED_FILE%' not found. Creating an empty one...
    type nul > "%SEED_FILE%"
    echo [WARNING] Please add product codes to '%SEED_FILE%' before the next run.
    pause
    exit /b 1
) else (
    echo [SETUP] Seeding database with targets from '%SEED_FILE%'...
    python -m src.tasks.seed_targets --file "%SEED_FILE%"
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to seed target products.
        pause
        exit /b 1
    )
)

:: Run the main scraping application after setup completes.
echo.
echo [SUCCESS] Setup completed successfully.
echo [INFO] Starting E-Commerce Pricing Intelligence Pipeline...
echo ======================================================================
python -m src.main
set APP_EXIT_CODE=!ERRORLEVEL!
echo ======================================================================

if !APP_EXIT_CODE! neq 0 (
    echo [ERROR] Application exited with an error code ^(!APP_EXIT_CODE!^).
) else (
    echo [SUCCESS] Application completed successfully.
)

pause
exit /b !APP_EXIT_CODE!
