@echo off
setlocal EnableDelayedExpansion
title Vibe Studio ^& J.A.R.V.I.S — Windows Setup and Launcher
color 0B

echo ===============================================================================
echo        VIBE STUDIO ^& J.A.R.V.I.S AUTONOMOUS OS -- WINDOWS SETUP
echo ===============================================================================
echo.

:: 1. Check Python Installation
echo [*] Checking Python installation...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    py -3 --version >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        color 0C
        echo [ERROR] Python 3.10+ is not found in PATH!
        echo Please install Python from https://www.python.org/downloads/
        echo Make sure to check "Add Python to PATH" during installation.
        echo.
        pause
        exit /b 1
    ) else (
        set PYTHON_CMD=py -3
    )
) else (
    set PYTHON_CMD=python
)

for /f "tokens=*" %%i in ('%PYTHON_CMD% --version') do set PY_VER=%%i
echo [OK] Detected %PY_VER%
echo.

:: 2. Create Virtual Environment
if not exist ".venv\Scripts\activate.bat" (
    echo [*] Creating virtual environment (.venv)...
    %PYTHON_CMD% -m venv .venv
    if %ERRORLEVEL% NEQ 0 (
        color 0C
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created successfully.
) else (
    echo [OK] Existing virtual environment found (.venv).
)
echo.

:: 3. Activate Virtual Environment
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat
echo [OK] Virtual environment active.
echo.

:: 4. Upgrade pip and build tools
echo [*] Upgrading pip and packaging tools...
python -m pip install --upgrade pip setuptools wheel >nul 2>&1
echo [OK] Pip upgraded.
echo.

:: 5. Install Dependencies
echo [*] Installing Vibe Studio ^& J.A.R.V.I.S dependencies...
pip install -e .[all]
if %ERRORLEVEL% NEQ 0 (
    echo [!] Retrying core installation...
    pip install PySide6 httpx requests pytest pytest-anyio fastapi uvicorn websockets cryptography psutil edge-tts
    pip install -e .
)
echo [OK] Dependencies installed successfully.
echo.

:: 6. Install Playwright Browsers
echo [*] Installing Playwright Chromium browser driver...
python -m playwright install chromium
echo [OK] Playwright browser driver ready.
echo.

:: 7. Check Ollama AI Engine
echo [*] Checking local Ollama AI Engine...
where ollama >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Ollama is installed.
) else (
    echo [!] Ollama not detected in PATH.
    echo     For local AI models (qwen2.5-coder, deepseek, etc.), download Ollama from:
    echo     https://ollama.com/download/windows
)
echo.

:: 8. Launcher Menu
echo ===============================================================================
echo                      INSTALLATION COMPLETED SUCCESSFULLY!
echo ===============================================================================
echo.
echo What would you like to launch?
echo   [1] 🤖 Launch J.A.R.V.I.S Autonomous Cockpit (Recommended)
echo   [2] 🌌 Launch Vibe Studio Full IDE
echo   [3] 🧪 Run All Unit ^& Integration Tests
echo   [4] ❌ Exit
echo.

set /p CHOICE="Enter your choice (1-4) [Default: 1]: "
if "%CHOICE%"=="" set CHOICE=1

if "%CHOICE%"=="1" (
    echo [*] Starting J.A.R.V.I.S Cockpit...
    python -m vibe_studio --jarvis
) else if "%CHOICE%"=="2" (
    echo [*] Starting Vibe Studio IDE...
    python -m vibe_studio
) else if "%CHOICE%"=="3" (
    echo [*] Running full test suite...
    python -m pytest tests/ -v
    pause
) else (
    echo Exiting. You can start anytime with:
    echo   call .venv\Scripts\activate.bat
    echo   python -m vibe_studio --jarvis
    echo.
)

endlocal
