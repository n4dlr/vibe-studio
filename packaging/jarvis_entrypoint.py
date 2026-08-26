"""Packaged entrypoint and runtime bootstrap for JARVIS Desktop Application."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Ensure package root is in sys.path
_repo_root = Path(__file__).resolve().parents[1]
_src_dir = _repo_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from packaging.common.paths import JarvisPaths
from packaging.common.version import JARVIS_DISPLAY_NAME, JARVIS_VERSION, get_build_metadata
from vibe_studio.jarvis.config_manager import ConfigManager
from vibe_studio.jarvis.hardware import HardwareDetector
from vibe_studio.jarvis.ollama_manager import OllamaManager


def setup_production_logging(log_level_str: str = "INFO") -> Path:
    """Configure structured file and console logging."""
    log_dir = JarvisPaths.get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"jarvis_{datetime.now().strftime('%Y%m%d')}.log"

    level = getattr(logging, log_level_str.upper(), logging.INFO)

    # Root logger configuration
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return log_file


def run_doctor() -> int:
    """Run full diagnostic self-check and print report."""
    print("=" * 70)
    print(f"  🔍 {JARVIS_DISPLAY_NAME} v{JARVIS_VERSION} — SYSTEM DIAGNOSTICS")
    print("=" * 70)

    # 1. Build & Paths
    meta = get_build_metadata()
    print(f"\n[1] Application Metadata:")
    print(f"    • Version:        {meta.version}")
    print(f"    • Build Date:     {meta.build_date}")
    print(f"    • OS / Arch:      {meta.target_platform} ({meta.target_arch})")
    print(f"    • Frozen Binary:  {JarvisPaths.is_frozen()}")
    print(f"    • Install Dir:    {JarvisPaths.get_app_install_dir()}")
    print(f"    • User Data Dir:  {JarvisPaths.get_user_data_dir()}")
    print(f"    • Config Dir:     {JarvisPaths.get_user_config_dir()}")
    print(f"    • Log Dir:        {JarvisPaths.get_log_dir()}")

    # 2. Hardware Profile
    print(f"\n[2] Hardware Telemetry:")
    hw = HardwareDetector.detect()
    print(f"    • CPU:            {hw.cpu_model}")
    print(f"    • Physical Cores: {hw.cpu_physical_cores} (Logical: {hw.cpu_logical_cores})")
    print(f"    • Total RAM:      {hw.total_ram_gb} GB (Available: {hw.available_ram_gb} GB)")
    print(f"    • GPUs:           {len(hw.gpus)} detected")
    for idx, g in enumerate(hw.gpus):
        print(f"      - GPU {idx+1}: {g.name} ({g.vendor.upper()}) | VRAM: {g.vram_mb} MB | CUDA: {g.cuda_available}")
    rec = hw.get_recommended_runtime_config()
    print(f"    • Recommendation: {rec['recommendation_summary']}")

    # 3. Ollama AI Engine
    print(f"\n[3] Ollama AI Runtime:")
    mgr = OllamaManager()
    status = mgr.check_status()
    print(f"    • Reachable:      {'✅ YES' if status.is_running else '❌ NO'}")
    print(f"    • Version:        {status.version or 'N/A'}")
    print(f"    • Binary:         {status.executable_path or 'Not Found'}")
    print(f"    • Bundled:        {status.is_bundled}")
    print(f"    • Models ({len(status.available_models)}):  {', '.join(status.available_models) if status.available_models else 'None'}")

    # 4. Audio & Voice
    print(f"\n[4] Neural Audio & Speech:")
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devs = [d for d in devices if d.get("max_input_channels", 0) > 0]
        print(f"    • Microphones:    {len(input_devs)} input device(s) found")
    except Exception as e:
        print(f"    • Audio Input:    ⚠️ Limited ({e})")

    try:
        from vibe_studio.jarvis.voice_engine import JarvisVoiceEngine
        ve = JarvisVoiceEngine()
        info = ve.get_current_voice_info()
        print(f"    • TTS Engine:     Active ({info.get('voice')})")
    except Exception as e:
        print(f"    • TTS Engine:     ⚠️ Error ({e})")

    print("\n" + "=" * 70)
    print("  Diagnostics complete.")
    print("=" * 70)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description=f"{JARVIS_DISPLAY_NAME} — AI-Native Autonomous OS & Desktop Intelligence",
    )
    parser.add_argument("--version", action="version", version=f"{JARVIS_DISPLAY_NAME} v{JARVIS_VERSION}")
    parser.add_argument("--doctor", action="store_true", help="Run environment and AI engine diagnostics")
    parser.add_argument("--cli", action="store_true", help="Launch in interactive CLI terminal mode")
    parser.add_argument("--model", type=str, default=None, help="Override target AI model")
    parser.add_argument("--workspace", type=str, default=".", help="Active workspace root directory")
    parser.add_argument("--no-ollama-auto-start", action="store_true", help="Do not auto-start local Ollama")

    subparsers = parser.add_subparsers(dest="subcommand", help="Command to execute")
    run_parser = subparsers.add_parser("run", help="Execute single autonomous task prompt")
    run_parser.add_argument("prompt", type=str, help="Instruction or coding task")

    args = parser.parse_args(argv)

    if args.doctor:
        return run_doctor()

    # Load configuration
    cfg_mgr = ConfigManager(args.workspace)
    config = cfg_mgr.load_config()

    # Configure Logging
    log_file = setup_production_logging(config.log_level)
    logger = logging.getLogger("jarvis.boot")
    logger.info("Initializing %s v%s", JARVIS_DISPLAY_NAME, JARVIS_VERSION)
    logger.info("Log file active at: %s", log_file)

    # Detect Hardware
    hw = HardwareDetector.detect()
    runtime_tuning = hw.get_recommended_runtime_config()
    logger.info("Hardware Detected: %s %s (%s cores, %s GB RAM, %s GPUs)",
                hw.cpu_model, hw.architecture, hw.cpu_physical_cores, hw.total_ram_gb, len(hw.gpus))
    logger.info("Runtime Tuning: %s", runtime_tuning["recommendation_summary"])

    # Model and Ollama Setup
    target_model = args.model or config.model
    if not args.no_ollama_auto_start and config.auto_start_ollama:
        ollama_mgr = OllamaManager(endpoint=config.ollama_url, auto_start=True)
        logger.info("Verifying Ollama and model '%s'...", target_model)
        try:
            ready = ollama_mgr.ensure_model_ready(
                model_name=target_model,
                progress_callback=lambda msg, pct: logger.info("[Model Init %s%%] %s", round(pct), msg),
            )
            if ready:
                logger.info("Model '%s' is verified and ready.", target_model)
            else:
                logger.warning("Model '%s' could not be initialized automatically. Application will run in degraded mode.", target_model)
        except Exception as e:
            logger.error("Ollama initialization encountered error: %s", e)

    workspace_path = Path(args.workspace).resolve()

    # Headless Task Execution
    if args.subcommand == "run":
        from vibe_studio.jarvis.engine import JarvisCore
        jarvis = JarvisCore(workspace_root=workspace_path, model=target_model)
        resp = jarvis.execute_command(args.prompt)
        print(f"\n⚡ [JARVIS]: {resp.spoken_text}")
        if resp.action_taken:
            print(f"🔧 Action: {resp.action_taken}")
        return 0

    # Interactive CLI Mode
    if args.cli:
        from vibe_studio.jarvis.engine import JarvisCore
        jarvis = JarvisCore(workspace_root=workspace_path, model=target_model)
        print(f"\n⚡ {JARVIS_DISPLAY_NAME} v{JARVIS_VERSION} (CLI Mode)")
        print("Type 'exit' or 'quit' to close. Speak or enter any command:\n")
        while True:
            try:
                user_input = input("jarvis> ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "q"):
                    break
                resp = jarvis.execute_command(user_input)
                print(f"⚡ {resp.spoken_text}\n")
            except (KeyboardInterrupt, EOFError):
                break
        print("\nShutdown complete.")
        return 0

    # Standalone Cyber Cockpit GUI Mode (Default)
    from vibe_studio.app.application import launch_jarvis_standalone
    return launch_jarvis_standalone(workspace_root=workspace_path)


if __name__ == "__main__":
    sys.exit(main())
