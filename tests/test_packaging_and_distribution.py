"""Comprehensive tests for JARVIS Packaging, Distribution, Hardware Detection, and Runtime Lifecycle."""
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root is on path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packaging.common.paths import JarvisPaths
from packaging.common.version import JARVIS_NAME, JARVIS_VERSION, get_build_metadata
from vibe_studio.jarvis.config_manager import ConfigManager, JarvisConfig
from vibe_studio.jarvis.hardware import HardwareDetector, HardwareProfile, GPUInfo
from vibe_studio.jarvis.ollama_manager import OllamaManager, OllamaStatus
from vibe_studio.security.permission_broker import PermissionBroker
from vibe_studio.tools.tool_registry import ToolRegistry


class TestPackagingMetadata:
    """Test single source of truth for versioning and metadata."""

    def test_version_constants(self):
        assert JARVIS_NAME == "JARVIS"
        assert isinstance(JARVIS_VERSION, str)
        assert len(JARVIS_VERSION.split(".")) >= 3

    def test_build_metadata(self):
        meta = get_build_metadata()
        assert meta.version == JARVIS_VERSION
        assert meta.target_platform != ""
        assert meta.target_arch != ""
        d = meta.as_dict()
        assert d["name"] == "JARVIS"
        assert d["version"] == JARVIS_VERSION


class TestPathResolver:
    """Test cross-platform path abstraction."""

    def test_user_directories_creation(self):
        user_data = JarvisPaths.get_user_data_dir()
        user_config = JarvisPaths.get_user_config_dir()
        log_dir = JarvisPaths.get_log_dir()
        cache_dir = JarvisPaths.get_cache_dir()

        assert user_data.exists()
        assert user_config.exists()
        assert log_dir.exists()
        assert cache_dir.exists()

    def test_models_directory(self):
        models_dir = JarvisPaths.get_models_dir()
        assert models_dir.exists()
        assert "models" in str(models_dir)

    def test_frozen_detection(self):
        # In test environment, sys.frozen is not set
        assert not JarvisPaths.is_frozen()


class TestHardwareDetector:
    """Test non-crashing hardware telemetry and auto-tuning."""

    def test_detect_runs_without_crashing(self):
        hw = HardwareDetector.detect()
        assert isinstance(hw, HardwareProfile)
        assert hw.cpu_physical_cores >= 1
        assert hw.total_ram_mb > 0
        assert hw.available_ram_mb > 0
        assert isinstance(hw.gpus, list)

    def test_recommended_runtime_config_generation(self):
        hw = HardwareDetector.detect()
        rec = hw.get_recommended_runtime_config()
        assert "tier" in rec
        assert "num_ctx" in rec
        assert "num_thread" in rec
        assert "gpu_layers" in rec
        assert rec["num_ctx"] in (2048, 4096, 8192, 16384, 32768)
        assert rec["num_thread"] >= 2

    def test_gpu_info_serialization(self):
        gpu = GPUInfo(vendor="nvidia", name="RTX 4090", vram_mb=24576, cuda_available=True)
        d = gpu.as_dict()
        assert d["vendor"] == "nvidia"
        assert d["vram_mb"] == 24576
        assert d["cuda_available"] is True


class TestConfigManager:
    """Test 4-tier configuration hierarchy and secret masking."""

    def test_default_config_loading(self, tmp_path):
        mgr = ConfigManager(workspace_root=tmp_path)
        cfg = mgr.load_config()
        assert isinstance(cfg, JarvisConfig)
        assert cfg.model == "jarvis-qwen"
        assert cfg.provider == "ollama"
        assert cfg.auto_start_ollama is True

    def test_environment_variable_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JARVIS_MODEL", "qwen2.5-coder:7b")
        monkeypatch.setenv("JARVIS_CONTEXT_SIZE", "8192")
        monkeypatch.setenv("JARVIS_VOICE_GENDER", "female")

        mgr = ConfigManager(workspace_root=tmp_path)
        cfg = mgr.load_config()
        assert cfg.model == "qwen2.5-coder:7b"
        assert cfg.context_size == 8192
        assert cfg.voice_gender == "female"

    def test_secret_masking(self):
        cfg = JarvisConfig()
        cfg.custom["api_key"] = "sk-live-1234567890abcdef"
        cfg.custom["db_password"] = "SuperSecretPass123"

        safe = cfg.as_safe_dict()
        assert safe["custom"]["api_key"] == "sk-...def"
        assert safe["custom"]["db_password"] == "Sup...123"


class TestOllamaManager:
    """Test Ollama supervisor and model creation logic."""

    def test_find_executable_fallback(self):
        mgr = OllamaManager()
        exe, is_bundled = mgr.find_ollama_executable()
        # On system where ollama is in PATH or absent, function must return tuple safely
        assert isinstance(is_bundled, bool)

    def test_status_inspection(self):
        mgr = OllamaManager(endpoint="http://127.0.0.1:11434")
        status = mgr.check_status()
        assert isinstance(status, OllamaStatus)
        assert status.endpoint == "http://127.0.0.1:11434"

    def test_resolve_modelfile(self):
        mgr = OllamaManager()
        mf = mgr._resolve_modelfile(None, "jarvis-qwen")
        assert mf is not None
        assert mf.exists()
        assert mf.name == "Modelfile"


class TestModelDefinitionsAndLicenses:
    """Test Modelfile, licenses, and third-party notices."""

    def test_modelfile_contents(self):
        modelfile_path = REPO_ROOT / "models" / "jarvis-qwen" / "Modelfile"
        assert modelfile_path.exists()
        content = modelfile_path.read_text(encoding="utf-8")
        assert "FROM qwen2.5-coder:1.5b" in content
        assert "PARAMETER temperature 0.2" in content
        assert "SYSTEM" in content
        assert "Azərbaycan" in content

    def test_third_party_notices(self):
        notices = REPO_ROOT / "THIRD_PARTY_NOTICES"
        assert notices.exists()
        text = notices.read_text(encoding="utf-8")
        assert "Qwen" in text
        assert "Apache License" in text
        assert "Ollama" in text
        assert "MIT License" in text


class TestPackagingSpecifications:
    """Validate Debian, Windows Inno Setup, and PyInstaller spec files."""

    def test_debian_control_file(self):
        control_path = REPO_ROOT / "packaging" / "linux" / "debian" / "control"
        assert control_path.exists()
        content = control_path.read_text(encoding="utf-8")
        assert "Package: jarvis" in content
        assert "Architecture: amd64" in content
        assert "Maintainer:" in content

    def test_debian_desktop_file(self):
        desktop_path = REPO_ROOT / "packaging" / "linux" / "jarvis.desktop"
        assert desktop_path.exists()
        content = desktop_path.read_text(encoding="utf-8")
        assert "[Desktop Entry]" in content
        assert "Exec=/opt/jarvis/jarvis" in content

    def test_inno_setup_file(self):
        iss_path = REPO_ROOT / "packaging" / "windows" / "installer" / "jarvis_installer.iss"
        assert iss_path.exists()
        content = iss_path.read_text(encoding="utf-8")
        assert 'MyAppName "JARVIS"' in content
        assert "JARVIS-Setup-x64" in content

    def test_pyinstaller_spec_file(self):
        spec_path = REPO_ROOT / "packaging" / "jarvis.spec"
        assert spec_path.exists()
        content = spec_path.read_text(encoding="utf-8")
        assert "jarvis_entrypoint.py" in content
        assert "hiddenimports" in content


class TestSecurityAndToolsIntegration:
    """Verify ToolRegistry and PermissionBroker under packaged structure."""

    def test_tool_registry_initialization(self, tmp_path):
        registry = ToolRegistry(workspace_root=tmp_path)
        assert registry.get("read_file") is not None
        assert registry.get("execute_command") is not None
        assert len(registry.list_tools()) > 0

    def test_permission_broker_enforcement(self, tmp_path):
        broker = PermissionBroker(workspace_root=tmp_path)
        # Inside workspace
        inside_file = "test.txt"
        assert broker.authorize_file_access(inside_file).value in ("ALLOW", "ASK")
        # Outside workspace
        outside_file = "/etc/shadow"
        assert broker.authorize_file_access(outside_file).value == "DENY"
        # Destructive command
        assert broker.authorize_command("rm -rf /").value == "DENY"
