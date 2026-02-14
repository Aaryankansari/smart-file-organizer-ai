@echo off
REM Quick Start Script for Smart File Organizer AI
REM This script helps you get started quickly

echo ============================================================
echo Smart File Organizer AI - Quick Start
echo ============================================================
echo.

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.10 or higher from https://python.org
    pause
    exit /b 1
)

echo [OK] Python is installed
echo.

REM Check if dependencies are installed
echo Checking dependencies...
pip show google-generativeai >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing dependencies...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed
) else (
    echo [OK] Dependencies already installed
)
echo.

REM Check for API key
if "%GEMINI_API_KEY%"=="" (
    echo [WARNING] GEMINI_API_KEY environment variable not set
    echo.
    echo You have two options:
    echo 1. Set GEMINI_API_KEY environment variable
    echo 2. Use local Ollama (install from https://ollama.ai/)
    echo.
    set /p choice="Do you want to set GEMINI_API_KEY now? (y/n): "
    if /i "%choice%"=="y" (
        set /p apikey="Enter your Gemini API key: "
        setx GEMINI_API_KEY "%apikey%"
        echo [OK] API key set. Please restart this script.
        pause
        exit /b 0
    )
)

echo.
echo ============================================================
echo What would you like to do?
echo ============================================================
echo 1. Test with sample file (dry run)
echo 2. Process a single file
echo 3. Process a directory (batch)
echo 4. Start web interface
echo 5. View help
echo 6. Exit
echo.

set /p option="Enter option (1-6): "

if "%option%"=="1" (
    echo.
    echo Running test with sample file...
    python smart_file_organizer.py test_document.txt --dry-run
    pause
) else if "%option%"=="2" (
    set /p filepath="Enter file path: "
    echo.
    echo Processing file...
    python smart_file_organizer.py "%filepath%" --rename --embed-metadata
    pause
) else if "%option%"=="3" (
    set /p dirpath="Enter directory path: "
    echo.
    echo Processing directory...
    python smart_file_organizer.py "%dirpath%" --batch --rename --embed-metadata
    pause
) else if "%option%"=="4" (
    echo.
    echo Starting web server...
    echo Open your browser to: http://localhost:5000
    echo Press Ctrl+C to stop the server
    python web_server.py
) else if "%option%"=="5" (
    python smart_file_organizer.py --help
    pause
) else if "%option%"=="6" (
    exit /b 0
) else (
    echo Invalid option
    pause
)

echo.
echo ============================================================
echo Done!
echo ============================================================
pause
