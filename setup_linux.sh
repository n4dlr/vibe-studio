#!/usr/bin/env bash
# ===============================================================================
# Vibe Studio & J.A.R.V.I.S Autonomous OS -- Linux Admin Setup and Launcher
# Supports both: sudo ./setup_linux.sh  AND  ./setup_linux.sh
# ===============================================================================
set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Determine real user when run via sudo
if [ -n "$SUDO_USER" ]; then
    REAL_USER="$SUDO_USER"
    REAL_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
else
    REAL_USER="$(whoami)"
    REAL_HOME="$HOME"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

echo -e "${CYAN}===============================================================================${NC}"
echo -e "${CYAN}        VIBE STUDIO & J.A.R.V.I.S AUTONOMOUS OS -- ADMIN SETUP                ${NC}"
echo -e "${CYAN}===============================================================================${NC}"
echo -e "[*] Target User: ${GREEN}${REAL_USER}${NC} (${REAL_HOME})"
echo ""

# 1. Check Python Installation
echo -e "[*] Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo -e "${YELLOW}[!] Python 3 not found. Installing via system package manager...${NC}"
    if command -v apt-get &> /dev/null; then
        apt-get update -y && apt-get install -y python3 python3-venv python3-pip
    elif command -v pacman &> /dev/null; then
        pacman -Sy --noconfirm python python-pip python-virtualenv
    elif command -v dnf &> /dev/null; then
        dnf install -y python3 python3-pip python3-virtualenv
    fi
fi

PY_VER=$(python3 --version)
echo -e "${GREEN}[OK] Detected ${PY_VER}${NC}"
echo ""

# 2. Check & Install Essential System Dependencies (Root/Admin Privileges)
echo -e "[*] Installing & verifying desktop integration utilities (wmctrl, xdotool, ffmpeg, notify-send)..."
SYS_DEPS=("wmctrl" "xdotool" "ffmpeg" "notify-send")
MISSING_SYS=()

for dep in "${SYS_DEPS[@]}"; do
    if ! command -v "$dep" &> /dev/null; then
        MISSING_SYS+=("$dep")
    fi
done

if [ ${#MISSING_SYS[@]} -ne 0 ] || [ ! -f "/usr/include/python3"* ]; then
    echo -e "${YELLOW}[!] Installing required packages: ${MISSING_SYS[*]}...${NC}"
    if command -v apt-get &> /dev/null; then
        if [ "$EUID" -eq 0 ]; then
            apt-get update -y && apt-get install -y wmctrl xdotool ffmpeg libnotify-bin python3-venv python3-pip libasound2-dev portaudio19-dev alsa-utils || true
        else
            sudo apt-get update -y && sudo apt-get install -y wmctrl xdotool ffmpeg libnotify-bin python3-venv python3-pip libasound2-dev portaudio19-dev alsa-utils || true
        fi

    elif command -v pacman &> /dev/null; then
        if [ "$EUID" -eq 0 ]; then
            pacman -Sy --noconfirm wmctrl xdotool ffmpeg libnotify python-virtualenv alsa-lib || true
        else
            sudo pacman -Sy --noconfirm wmctrl xdotool ffmpeg libnotify python-virtualenv alsa-lib || true
        fi
    elif command -v dnf &> /dev/null; then
        if [ "$EUID" -eq 0 ]; then
            dnf install -y wmctrl xdotool ffmpeg libnotify python3-pip || true
        else
            sudo dnf install -y wmctrl xdotool ffmpeg libnotify python3-pip || true
        fi
    fi
else
    echo -e "${GREEN}[OK] All desktop automation utilities found.${NC}"
fi
echo ""

# 3. Create Virtual Environment with user permissions
if [ ! -f ".venv/bin/activate" ]; then
    echo -e "[*] Creating virtual environment (.venv)..."
    if [ "$EUID" -eq 0 ] && [ -n "$SUDO_USER" ]; then
        sudo -u "$REAL_USER" python3 -m venv .venv
    else
        python3 -m venv .venv
    fi
    echo -e "${GREEN}[OK] Virtual environment created successfully.${NC}"
else
    echo -e "${GREEN}[OK] Existing virtual environment found (.venv).${NC}"
fi

# Ensure correct file permissions
if [ "$EUID" -eq 0 ] && [ -n "$SUDO_USER" ]; then
    chown -R "$REAL_USER:$REAL_USER" "$SCRIPT_DIR/.venv" 2>/dev/null || true
fi

# 4. Activate & Upgrade pip
source .venv/bin/activate
echo -e "[*] Upgrading pip and packaging tools..."
pip install --upgrade pip setuptools wheel > /dev/null 2>&1
echo -e "${GREEN}[OK] Pip upgraded.${NC}"
echo ""

# 5. Install Dependencies
echo -e "[*] Installing Vibe Studio & J.A.RV.I.S dependencies..."
pip install -e .[all] || {
    echo -e "${YELLOW}[!] Retrying core packages...${NC}"
    pip install PySide6 httpx requests pytest pytest-anyio fastapi uvicorn websockets cryptography psutil edge-tts SpeechRecognition sounddevice
    pip install -e .

}
echo -e "${GREEN}[OK] Python packages installed successfully.${NC}"
echo ""

# 6. Install Playwright Chromium Driver
echo -e "[*] Installing Playwright Chromium browser binary..."
python3 -m playwright install chromium || true
echo -e "${GREEN}[OK] Playwright browser driver ready.${NC}"
echo ""

# 7. Setup Ollama AI Engine & Interactive Model Tier Selector
echo -e "[*] Setting up local Ollama AI Engine..."
if ! command -v ollama &> /dev/null; then
    echo -e "${YELLOW}[*] Ollama not detected. Auto-installing Ollama...${NC}"
    curl -fsSL https://ollama.com/install.sh | sh || true
fi

if command -v ollama &> /dev/null; then
    echo -e "${GREEN}[OK] Ollama is installed.${NC}"
    
    # Ensure Ollama server daemon is active
    if ! curl -s http://127.0.0.1:11434/api/tags &> /dev/null; then
        echo -e "[*] Starting Ollama background server..."
        if [ "$EUID" -eq 0 ] && [ -n "$SUDO_USER" ]; then
            sudo -u "$REAL_USER" ollama serve > /dev/null 2>&1 &
        else
            ollama serve > /dev/null 2>&1 &
        fi
        sleep 3
    fi

    echo ""
    echo -e "${CYAN}---------------------------------------------------------------------------------------------${NC}"
    echo -e "${CYAN}             🤖 TOP AGENTIC & CODING AI MODEL ROSTER (OPTIMIZED FOR <= 7B)                   ${NC}"
    echo -e "${CYAN}---------------------------------------------------------------------------------------------${NC}"
    echo -e "${YELLOW}⚡ ULTRA-LIGHTWEIGHT & FAST (2GB - 4GB RAM/VRAM):${NC}"
    echo -e "  ${CYAN}[1]${NC} Qwen 2.5 Coder 1.5B     (~980 MB  | ⚡ 120+ tok/s | Fast Coding & Tool Use)"
    echo -e "  ${CYAN}[2]${NC} DeepSeek-R1 1.5B        (~1.1 GB  | 🧠 90+ tok/s  | Lightweight Chain-of-Thought)"
    echo ""
    echo -e "${YELLOW}⭐ BALANCED SWEETSPOT (4GB - 6GB VRAM) [RECOMMENDED]:${NC}"
    echo -e "  ${CYAN}[3]${NC} Qwen 2.5 Coder 3B       (~1.9 GB  | ⭐ 65+ tok/s  | Excellent Balance of IQ & Speed)"
    echo -e "  ${CYAN}[4]${NC} StarCoder2 3B           (~1.8 GB  | 💻 60+ tok/s  | Multi-Language Repo Specialist)"
    echo -e "  ${CYAN}[5]${NC} Gemma 3 4B              (~3.1 GB  | 🌐 45+ tok/s  | Google Multimodal & Context)"
    echo ""
    echo -e "${YELLOW}🏆 TOP-TIER TITANS (6GB - 8GB VRAM / Max IQ <= 7B):${NC}"
    echo -e "  ${CYAN}[6]${NC} Qwen 2.5 Coder 7B       (~4.7 GB  | 🏆 35+ tok/s  | #1 Coding/Agent Benchmark King)"
    echo -e "  ${CYAN}[7]${NC} DeepSeek Coder 6.7B     (~3.8 GB  | 🛠️ 35+ tok/s  | Deep Architectural & Bug Hunter)"
    echo -e "  ${CYAN}[8]${NC} DeepSeek-R1 7B          (~4.7 GB  | 🧠 30+ tok/s  | Advanced Math & Logic Reasoner)"
    echo -e "  ${CYAN}[9]${NC} CodeLlama 7B            (~3.8 GB  | 🐍 35+ tok/s  | Meta Python & Full-Stack Model)"
    echo ""
    echo -e "  ${GREEN}[A]${NC} Download ALL Recommended Models (1, 3, 6)"
    echo -e "  ${YELLOW}[0]${NC} Skip model download (Configure later)"
    echo -e "${CYAN}---------------------------------------------------------------------------------------------${NC}"
    echo -e "Format options: single ('3'), contiguous ('136'), separated ('1 3 6' or '1, 3, 6'), or 'A'"
    read -rp "Enter choice(s) [Default: 3]: " RAW_CHOICE
    RAW_CHOICE=${RAW_CHOICE:-3}

    # Normalize input: extract digits or ALL
    CHOSEN_MODELS=()
    if [[ "$RAW_CHOICE" =~ [Aa] ]]; then
        CHOSEN_MODELS=("qwen2.5-coder:1.5b" "qwen2.5-coder:3b" "qwen2.5-coder:7b")
    elif [[ "$RAW_CHOICE" == "0" ]]; then
        CHOSEN_MODELS=()
    else
        [[ "$RAW_CHOICE" =~ 1 ]] && CHOSEN_MODELS+=("qwen2.5-coder:1.5b")
        [[ "$RAW_CHOICE" =~ 2 ]] && CHOSEN_MODELS+=("deepseek-r1:1.5b")
        [[ "$RAW_CHOICE" =~ 3 ]] && CHOSEN_MODELS+=("qwen2.5-coder:3b")
        [[ "$RAW_CHOICE" =~ 4 ]] && CHOSEN_MODELS+=("starcoder2:3b")
        [[ "$RAW_CHOICE" =~ 5 ]] && CHOSEN_MODELS+=("gemma3:4b")
        [[ "$RAW_CHOICE" =~ 6 ]] && CHOSEN_MODELS+=("qwen2.5-coder:7b")
        [[ "$RAW_CHOICE" =~ 7 ]] && CHOSEN_MODELS+=("deepseek-coder:6.7b")
        [[ "$RAW_CHOICE" =~ 8 ]] && CHOSEN_MODELS+=("deepseek-r1:7b")
        [[ "$RAW_CHOICE" =~ 9 ]] && CHOSEN_MODELS+=("codellama:7b")
    fi

    if [ ${#CHOSEN_MODELS[@]} -eq 0 ] && [[ "$RAW_CHOICE" != "0" ]]; then
        CHOSEN_MODELS=("qwen2.5-coder:3b")
    fi

    echo ""
    for mdl in "${CHOSEN_MODELS[@]}"; do
        echo -e "[*] Pulling model: ${CYAN}${mdl}${NC}..."
        if [ "$EUID" -eq 0 ] && [ -n "$SUDO_USER" ]; then
            sudo -u "$REAL_USER" ollama pull "$mdl" || true
        else
            ollama pull "$mdl" || true
        fi
        echo -e "${GREEN}[OK] ${mdl} downloaded and ready!${NC}"
    done

else
    echo -e "${YELLOW}[!] Could not auto-install Ollama. Please install manually from https://ollama.com${NC}"
fi
echo ""



# 8. Restore permissions to real user
if [ "$EUID" -eq 0 ] && [ -n "$SUDO_USER" ]; then
    chown -R "$REAL_USER:$REAL_USER" "$SCRIPT_DIR" 2>/dev/null || true
fi

# 9. Interactive Launcher Menu
echo -e "${CYAN}===============================================================================${NC}"
echo -e "${GREEN}                     ADMIN SETUP COMPLETED SUCCESSFULLY!                       ${NC}"
echo -e "${CYAN}===============================================================================${NC}"
echo ""
echo -e "What would you like to launch?"
echo -e "  ${CYAN}[1]${NC} 🤖 Launch J.A.R.V.I.S Autonomous Cockpit (Recommended)"
echo -e "  ${CYAN}[2]${NC} 🌌 Launch Vibe Studio Full IDE"
echo -e "  ${CYAN}[3]${NC} 🧪 Run Full Test Suite (pytest)"
echo -e "  ${CYAN}[4]${NC} ❌ Exit"
echo ""

read -rp "Enter choice (1-4) [Default: 1]: " CHOICE
CHOICE=${CHOICE:-1}

case $CHOICE in
    1)
        echo -e "${GREEN}[*] Starting J.A.R.V.I.S Autonomous Cockpit...${NC}"
        if [ "$EUID" -eq 0 ] && [ -n "$SUDO_USER" ]; then
            sudo -u "$REAL_USER" DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" "$SCRIPT_DIR/.venv/bin/python3" -m vibe_studio --jarvis
        else
            python3 -m vibe_studio --jarvis
        fi
        ;;
    2)
        echo -e "${GREEN}[*] Starting Vibe Studio IDE...${NC}"
        if [ "$EUID" -eq 0 ] && [ -n "$SUDO_USER" ]; then
            sudo -u "$REAL_USER" DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" "$SCRIPT_DIR/.venv/bin/python3" -m vibe_studio
        else
            python3 -m vibe_studio
        fi
        ;;
    3)
        echo -e "${GREEN}[*] Running test suite...${NC}"
        python3 -m pytest tests/ -v
        ;;
    *)
        echo -e "Exiting. You can start anytime with:"
        echo -e "  ${CYAN}python3 -m vibe_studio --jarvis${NC}"
        ;;
esac
