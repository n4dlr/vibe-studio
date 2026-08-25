# 🚀 Vibe Studio — Autonomous AI IDE, J.A.R.V.I.S OS, Obsidian Graph & n8n Automation Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PySide6](https://img.shields.io/badge/GUI-PySide6-green.svg)](https://wiki.qt.io/Qt_for_Python)
[![Playwright](https://img.shields.io/badge/Browser-Playwright-orange.svg)](https://playwright.dev/python/)
[![Tests Passing](https://img.shields.io/badge/Tests-628%20passed-success.svg)](#-running-tests)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Vibe Studio** is a next-generation AI-native desktop IDE that unifies:
1. **🤖 J.A.R.V.I.S Autonomous Desktop & Voice OS** (Arc Reactor HUD, Windows Aero edge snapping, bilingual Azerbaijani/English neural voice, high-speed 0.7s Speech-to-Text, multi-monitor display management, power profile control, night light, timer/scheduler daemon, YouTube direct autoplay scraper, global file finder, desktop notifications, vision analysis, and hardware telemetry).
2. **The Autonomous Execution Power of Claude Agent & Devin** (Zero-failure AST guard, smart fuzzy patcher, MoA sandboxing, specialist multi-agent swarm).
3. **The Knowledge & Physics Code Graph of Obsidian** (Interactive 2D force-directed dependency graph, true iterative PageRank, multi-language AST for Python/JS/TS/Go/Rust, bidirectional `[[WikiLinks]]`, infinite `.canvas` whiteboard).
4. **The Visual Automation & Pipeline Power of n8n** (DAG node-based workflows, AST-validated safe script sandbox, CommandSafety, Playwright web actions, SuperAgent auto-repair).
5. **Persistent Cross-Session Learning** (`AgentMemoryGraph` & ADR recorder that gets smarter with every task).

---

## ⚡ 1-Kliklə Avtomatlaşdırılmış Quraşdırma (1-Click Auto Setup)

### 🪟 Windows Üçün:
Sadəcə **`setup-windows.bat`** faylını iki dəfə klikləyin və ya CMD/PowerShell-də işə salın:
```cmd
setup-windows.bat
```
*(Avtomatik olaraq Python mühitini, səs tanıma və nitq paketlərini (`SpeechRecognition`, `sounddevice`, `edge-tts`), bütün asılılıqları, Chromium drayverini quraşdırır və J.A.R.V.I.S-i açır).*

### 🐧 Linux Üçün:
Terminalda aşağıdakı əmri icra edin:
```bash
./setup_linux.sh
# və ya
./setup_linus.sh
```
*(Sistem paketlərini, `wmctrl`, `xdotool`, `ffmpeg`, `arecord`, `portaudio`, virtual mühiti və J.A.R.V.I.S-i tam avtomatlaşdırılmış şəkildə hazırlayır).*

---

## ⚡ Tez və Rahat Başlatma Komandaları (Quick Start)

### 1. 🤖 J.A.R.V.I.S Standalone Cockpit (Birbaşa J.A.R.V.I.S Pəncərəsini Açmaq)
```bash
# Modul kimi (Ən rahat və birbaşa yol):
python3 -m vibe_studio --jarvis

# Və ya CLI vasitəsilə:
vibe-studio jarvis
# və ya
vibe-studio --jarvis
```

### 2. 🌌 Vibe Studio IDE (Əsas Proqramlaşdırma Mühitini Açmaq)
```bash
# Modul kimi:
python3 -m vibe_studio

# Və ya CLI vasitəsilə:
vibe-studio gui
```

### 3. 🌐 Web UI & REST API Serveri
```bash
vibe-studio server --port 8000
```

---

## 🌟 The 5 Core Powerhouses of Vibe Studio

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                 VIBE STUDIO TITAN PLATFORM                              │
├───────────────────────────────┬───────────────────────────────┬─────────────────────────┤
│       J.A.R.V.I.S COCKPIT     │       OBSIDIAN SYSTEM         │         N8N ENGINE      │
│  - Holographic Arc Reactor    │  - Interactive Physics Graph  │  - Node-Based Pipelines │
│  - Windows Aero Edge Snapping │  - True Iterative PageRank    │  - AST Script Sandbox   │
│  - Ultra-Fast STT (0.7s)      │  - Multi-Language AST Graph   │  - CommandSafety Runner │
│  - Neural Voices (Banu/Babək) │  - Bidirectional WikiLinks    │  - Live Variable State  │
│  - Multi-Monitor & Power Mode │  - Markdown Whiteboard Canvas │  - Specialist Swarm     │
│  - Direct YouTube Autoplay    │  - ADR & Code Architecture    │  - Visual Node Studio   │
└───────────────────────────────┴───────────────────────────────┴─────────────────────────┘
```

---

## 🤖 1. J.A.R.V.I.S Autonomous Desktop & Voice OS (`src/vibe_studio/jarvis/`)

J.A.R.V.I.S istifadəçinin bütün kompüterini və proqramlaşdırma prosesini idarə edən **tam agentik süni intellektdir**.

### 🎮 J.A.R.V.I.S Tam Əmr Bələdçisi (Səslə və ya Mətnlə):

| Kateqoriya | Nümunə Əmrlər | Nəticə |
|---|---|---|
| **🎤 İkidilli Səs Tanıma (STT)** | Mikrofona basıb danışın | 0.7s ərzində Azərbaycan və İngilis dilində səsi dəqiq mətnə çevirir |
| **🔊 Təbii Qız/Kişi Səsi (TTS)** | `qadın səsinə keç` / `kişi səsinə keç` | `az-AZ-BanuNeural` və `az-AZ-BabekNeural` HD neyron səslərinə keçid edir |
| **👂 Daimi Wake-Word** | `"Hey Jarvis"`, `"Salam Jarvis"`, `"Friday"` | Düyməsiz, arxa fonda daimi dinləyir və oyanır |
| **🎵 YouTube Birbaşa Mahnı** | `inna caliente musiqisini ac` / `play first one` | Birbaşa video ID-sini tapıb mahnını ilk saniyədən oxudur (`autoplay=1`) |
| **🖥️ Çoxlu Monitor İdarəsi** | `monitorları göstər` / `pəncərəni 2-ci monitora keçir` | Bütün qoşulmuş ekranları aşkar edir və pəncərələri daşıyır |
| **⚡ Performans və Güc Rejimi** | `performans rejimi` / `qənaət rejimi` / `balans rejimi` | CPU və sistem güc profilini (`performance`, `power-saver`, `balanced`) tənzimləyir |
| **🔋 Batareya Telemetriyası** | `batareya vəziyyəti` / `zaryadka neçə faizdir` | Batareya faizini və AC cərəyan vəziyyətini bildirir |
| **🌙 Gecə İşığı (Night Light)** | `gecə işığını yandır` / `gecə işığını söndür` | Gözü qoruyan isti rəng temperaturu filtrini aktiv/deaktiv edir |
| **🖱️ Siçan & Sürüşdürmə** | `aşağı sürüşdür` / `yuxarı sürüşdür` / `scroll down` | Siçanın təkərini yuxarı/aşağı sürüşdürür |
| **🌐 Aktiv Tabı Oxuma** | `bu səhifəni oxu` / `read active tab` | Açıq olan brauzer səhifəsinin başlığını və kontekstini oxuyur |
| **🎯 OCR Vizual Klikləyici** | `Daxil ol düyməsini bas` / `click Login button` | Ekrandakı mətni OCR ilə tapıb siçanla klikləyir |
| **📶 Wi-Fi və Bluetooth** | `wifi axtar`, `wifi yandır`, `bluetooth söndür` | Simsiz şəbəkələri skan edir və idarə edir |
| **⏰ Taymer və Xatırlatmalar** | `10 dəqiqə sonra çayı xatırlat` / `set timer for 5 minutes` | Asinxron fonda taymer qurur, vaxt tamam olduqda səsli və bildirişlə xəbər verir |
| **🔔 Zəngli Saat (Alarm)** | `saat 15:30-da zəng qur` / `set alarm for 09:00` | Təyin olunmuş vaxtda zəng vurur |
| **🔍 Bütün Diskdə Fayl Axtarışı** | `bütün kompüterdə report.pdf tap` / `find all pdf files` | Bütün diski axtarıb faylları tapır |
| **📨 Stolüstü Bildirişlər** | `bildiriş göndər İş tamamlandı` / `send notification Hello` | OS masaüstü pop-up bildiriş kartı çıxarır |
| **👁️ Ekran və Vizual Analiz** | `ekranı analiz et` / `what is on my screen` | Ekranın şəklini çəkib vizual olaraq analiz edir |
| **📷 Veb-Kamera Çəkilişi** | `veb-kamera ilə şəkil çək` / `take photo with webcam` | Kameradan canlı kadr götürür |
| **📦 Çoxplatformalı Paket Meneceri** | `install htop`, `git yüklə`, `pip install fastapi` | Linux (apt/dnf/pacman), Windows (winget/choco), Mac (brew) ilə avtomatik quraşdırır |
| **🧠 Real Hardware Telemetriyası** | `how many ram i have?`, `ram nə qədərdir?`, `what is my cpu` | Kernel səviyyəsində dəqiq RAM, CPU, GPU, Disk vəziyyətini oxuyur |
| **🔒 Cihaz Təhlükəsizliyi** | `cihazı kilidlə` / `lock screen` | Linux/Windows sessiyasını dərhal kilidləyir |
| **🪟 Pəncərə və Klaviatura** | `tam ekran et`, `pəncərəni kiçilt`, `pəncərəni bağla` | Pəncərələri böyüdür/kiçildir və klaviatura əmrlərini simulyasiya edir |
| **☀️ Canlı Hava** | `hava necədir`, `Bakıda hava` | Real-vaxt hava temperaturunu deyir |
| **💡 Ekran Parlaqlığı** | `ekran parlaqlığını 80 faiz et`, `set brightness to 70` | Ekran parlaqlığını dərhal tənzimləyir |
| **🚀 İnternet Sürət Testi** | `open browser and test internet speed test on fast.com` | Fast.com-u açır və internet sürətini yoxlayır |
| **💻 Ağıllı Dil Şablonları & Kodlama** | `create simple nodejs file in desktop`, `create python file` | Düzgün fayl adı (`app.js`, `main.py`) və işlək kodla masaüstündə layihə yaradır |

### 🧠 Tövsiyə Olunan Agentik & Kodlaşdırma Modelləri (<= 7B):

J.A.R.V.I.S və quraşdırma skriptləri xüsusi olaraq **4GB–8GB VRAM və 6GB–16GB RAM** üçün ən güclü agentik və kod modelləri ilə inteqrasiya edilib:

| Model | Həcm | VRAM/RAM | Sürət | İxtisaslaşma & Güclü Tərəfi |
|---|---|---|---|---|
| **`qwen2.5-coder:3b`** *(Default)* | ~1.9 GB | 4GB - 6GB | ⚡ **65+ tok/s** | ⭐ **Ən balanslı seçim**: Sürət, dəqiq agentik alət çağırma və kod yazma |
| **`qwen2.5-coder:7b`** | ~4.7 GB | 6GB - 8GB | 🚀 **35+ tok/s** | 🏆 **<= 7B üzrə dünya 1-cisi**: Full-stack proqramlaşdırma və mürəkkəb refaktorinq |
| **`deepseek-coder:6.7b`** | ~3.8 GB | 6GB - 8GB | 🚀 **35+ tok/s** | 🛠️ Dərin layihə arxitekturası, bug hunting və repo analizi |
| **`deepseek-r1:7b`** | ~4.7 GB | 6GB - 8GB | 🧠 **30+ tok/s** | 💡 Chain-of-Thought (düşünərək cavab vermə) və alqoritm həlli |
| **`qwen2.5-coder:1.5b`** | ~980 MB | 2GB - 4GB | ⚡ **120+ tok/s** | 💨 Ultra-sürətli kodlaşdırma və sürətli cavablar |
| **`deepseek-r1:1.5b`** | ~1.1 GB | 2GB - 4GB | ⚡ **90+ tok/s** | 🧠 Yüngül düşünmə modeli |
| **`gemma3:4b`** | ~3.1 GB | 4GB - 6GB | ⚡ **45+ tok/s** | 🌐 Google-un təbii ünsiyyət və kod modeli |
| **`starcoder2:3b`** | ~1.8 GB | 4GB - 6GB | ⚡ **60+ tok/s** | 💻 Çoxdilli (Python, JS, C++, Go, Rust) kod tamamlama |
| **`codellama:7b`** | ~3.8 GB | 6GB - 8GB | 🚀 **35+ tok/s** | 🐍 Meta-nın Python və backend modeli |

---

## 🕸️ 2. Obsidian-Grade Knowledge & Physics Code Graph (`src/vibe_studio/knowledge/graph_engine.py`)
- **Multi-Language AST Dependency Graphing**: Scans classes, functions, modules, and imports across **Python, TypeScript, JavaScript, Rust, and Go**.
- **True Iterative PageRank ($d = 0.85$)**: Mathematically identifies the most critical architectural hubs in your codebase.
- **Obsidian `[[WikiLinks]]`**: Bidirectional backlinks between Markdown architecture docs and source code.
- **Interactive Force-Directed Canvas (`KnowledgeGraphPanel`)**: Real-time Coulomb-Hooke physics simulation with glowing hub nodes, search filters, zoom/pan, and double-click to navigate in the editor.

---

## ⚡ 3. n8n-Grade Visual Workflow & Pipeline Engine (`src/vibe_studio/workflow/`)
- **DAG Node-Based Pipelines**: Connect Manual Triggers, Safe Python Scripts, Shell Commands, SuperAgent Actions, and Playwright Web automation.
- **AST-Validated Script Sandbox**: Python script execution sandbox strictly blocks dangerous imports (`subprocess`, `shutil`, `socket`) and exposes safe builtins (`math`, `json`, `re`, `datetime`).
- **CommandSafety Verification**: Commands validated against absolute safety rules and workspace boundary isolation.

---

## 🛡️ 4. Sandboxed Multi-Agent Execution & Policy Authorization
- **Mixture of Agents (MoA) Isolation**: Parallel candidate proposals execute inside ephemeral isolated sandbox directories (`tempfile.TemporaryDirectory`). Only the winning proposal is applied cleanly to the workspace once.
- **PermissionBroker Policy Gate**: Active authorization gate in `ToolRegistry.execute()` blocking unauthorized filesystem breakouts and critical command execution.

---

## 🧪 Running Tests

Repository-də **628 unit və inteqrasiya testi** 100% keçir:

```bash
# Bütün testləri işə salmaq:
python3 -m pytest tests/ -q

# J.A.R.V.I.S Super-Suite testləri:
python3 -m pytest tests/test_jarvis_super_suite.py -v

# Arxitektur bərkitmə testləri:
python3 -m pytest tests/test_architectural_hardening.py -v
```