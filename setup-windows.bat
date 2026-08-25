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
    pip install PySide6 httpx requests pytest pytest-anyio fastapi uvicorn websockets cryptography psutil edge-tts SpeechRecognition sounddevice
    pip install -e .

)
echo [OK] Dependencies installed successfully.
echo.

:: 6. Install Playwright Browsers
echo [*] Installing Playwright Chromium browser driver...
python -m playwright install chromium
echo [OK] Playwright browser driver ready.
echo.

:: 7. Setup Ollama AI Engine & Interactive Model Tier Selector
echo [*] Checking local Ollama AI Engine...
where ollama >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] Ollama is installed.
    echo.
    echo ---------------------------------------------------------------------------------------------
    echo              🤖 TOP AGENTIC ^& CODING AI MODEL ROSTER (OPTIMIZED FOR ^<= 7B)
    echo ---------------------------------------------------------------------------------------------
    echo ⚡ ULTRA-LIGHTWEIGHT ^& FAST (2GB - 4GB RAM/VRAM):
    echo   [1] Qwen 2.5 Coder 1.5B     (~980 MB  ^| ⚡ 120+ tok/s ^| Fast Coding ^& Tool Use)
    echo   [2] DeepSeek-R1 1.5B        (~1.1 GB  ^| 🧠 90+ tok/s  ^| Lightweight Chain-of-Thought)
    echo.
    echo ⭐ BALANCED SWEETSPOT (4GB - 6GB VRAM) [RECOMMENDED]:
    echo   [3] Qwen 2.5 Coder 3B       (~1.9 GB  ^| ⭐ 65+ tok/s  ^| Excellent Balance of IQ ^& Speed)
    echo   [4] StarCoder2 3B           (~1.8 GB  ^| 💻 60+ tok/s  ^| Multi-Language Repo Specialist)
    echo   [5] Gemma 3 4B              (~3.1 GB  ^| 🌐 45+ tok/s  ^| Google Multimodal ^& Context)
    echo.
    echo 🏆 TOP-TIER TITANS (6GB - 8GB VRAM / Max IQ ^<= 7B):
    echo   [6] Qwen 2.5 Coder 7B       (~4.7 GB  ^| 🏆 35+ tok/s  ^| #1 Coding/Agent Benchmark King)
    echo   [7] DeepSeek Coder 6.7B     (~3.8 GB  ^| 🛠️ 35+ tok/s  ^| Deep Architectural ^& Bug Hunter)
    echo   [8] DeepSeek-R1 7B          (~4.7 GB  ^| 🧠 30+ tok/s  ^| Advanced Math ^& Logic Reasoner)
    echo   [9] CodeLlama 7B            (~3.8 GB  ^| 🐍 35+ tok/s  ^| Meta Python ^& Full-Stack Model)
    echo.
    echo   [A] Download ALL Recommended Models (1, 3, 6)
    echo   [0] Skip model download (Configure later)
    echo ---------------------------------------------------------------------------------------------
    echo Format options: single ('3'), contiguous ('136'), separated ('1 3 6' or '1, 3, 6'), or 'A'
    set /p MCHOICE="Enter choice(s) [Default: 3]: "
    if "!MCHOICE!"=="" set MCHOICE=3

    if /i "!MCHOICE!"=="A" set MCHOICE=136

    echo !MCHOICE! | findstr "1" >nul && (echo [*] Pulling qwen2.5-coder:1.5b... & ollama pull qwen2.5-coder:1.5b)
    echo !MCHOICE! | findstr "2" >nul && (echo [*] Pulling deepseek-r1:1.5b... & ollama pull deepseek-r1:1.5b)
    echo !MCHOICE! | findstr "3" >nul && (echo [*] Pulling qwen2.5-coder:3b... & ollama pull qwen2.5-coder:3b)
    echo !MCHOICE! | findstr "4" >nul && (echo [*] Pulling starcoder2:3b... & ollama pull starcoder2:3b)
    echo !MCHOICE! | findstr "5" >nul && (echo [*] Pulling gemma3:4b... & ollama pull gemma3:4b)
    echo !MCHOICE! | findstr "6" >nul && (echo [*] Pulling qwen2.5-coder:7b... & ollama pull qwen2.5-coder:7b)
    echo !MCHOICE! | findstr "7" >nul && (echo [*] Pulling deepseek-coder:6.7b... & ollama pull deepseek-coder:6.7b)
    echo !MCHOICE! | findstr "8" >nul && (echo [*] Pulling deepseek-r1:7b... & ollama pull deepseek-r1:7b)
    echo !MCHOICE! | findstr "9" >nul && (echo [*] Pulling codellama:7b... & ollama pull codellama:7b)
    echo [OK] Selected model(s) downloaded and ready!
) else (
    echo [!] Ollama not detected in PATH.
    echo     To download local AI models, install Ollama from:
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
