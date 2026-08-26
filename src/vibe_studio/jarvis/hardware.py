"""Hardware detection and automatic runtime/model tuning engine for JARVIS.

Detects:
- Operating System & Architecture
- CPU Model, Cores, Threads
- Total & Available RAM
- GPU Vendor, VRAM, NVIDIA CUDA, AMD ROCm, Intel / Integrated GPU
- Generates optimal runtime parameters (num_ctx, num_threads, gpu_layers, batch size)
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class GPUInfo:
    vendor: str  # "nvidia", "amd", "intel", "apple", "unknown"
    name: str = "Unknown GPU"
    vram_mb: int = 0
    cuda_available: bool = False
    cuda_compute_capability: str | None = None
    driver_version: str | None = None
    is_integrated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "name": self.name,
            "vram_mb": self.vram_mb,
            "cuda_available": self.cuda_available,
            "cuda_compute_capability": self.cuda_compute_capability,
            "driver_version": self.driver_version,
            "is_integrated": self.is_integrated,
        }


@dataclass
class HardwareProfile:
    os_name: str
    os_version: str
    architecture: str
    cpu_model: str
    cpu_physical_cores: int
    cpu_logical_cores: int
    total_ram_mb: int
    available_ram_mb: int
    gpus: list[GPUInfo] = field(default_factory=list)
    has_discrete_gpu: bool = False
    has_cuda: bool = False

    @property
    def total_ram_gb(self) -> float:
        return round(self.total_ram_mb / 1024.0, 2)

    @property
    def available_ram_gb(self) -> float:
        return round(self.available_ram_mb / 1024.0, 2)

    @property
    def primary_gpu(self) -> GPUInfo | None:
        return self.gpus[0] if self.gpus else None

    def get_recommended_runtime_config(self) -> dict[str, Any]:
        """Compute sensible runtime parameters based on detected system hardware."""
        # 1. Thread tuning: default to physical cores - 1 (or logical // 2), minimum 2
        threads = max(2, self.cpu_physical_cores)
        if threads > 16:
            threads = 16  # Cap to prevent cache thrashing

        # 2. Memory Tier:
        # LOW RAM: < 6GB Total or < 3GB Available
        # MID RAM: 6GB - 16GB Total
        # HIGH RAM: > 16GB Total
        is_low_ram = (self.total_ram_mb < 6000) or (self.available_ram_mb < 3000)
        is_high_ram = (self.total_ram_mb >= 16000)

        # 3. GPU acceleration
        vram_mb = 0
        if self.gpus:
            vram_mb = max((g.vram_mb for g in self.gpus), default=0)

        if self.has_cuda and vram_mb >= 4000:
            tier = "GPU_ACCELERATED"
            num_ctx = 16384 if vram_mb < 8000 else 32768
            gpu_layers = 99  # Offload all layers to GPU
            batch_size = 512
        elif self.has_cuda and vram_mb >= 2000:
            tier = "GPU_HYBRID"
            num_ctx = 8192
            gpu_layers = 20  # Partial offload
            batch_size = 256
        elif is_low_ram:
            tier = "LOW_RAM_CPU"
            num_ctx = 2048
            gpu_layers = 0
            batch_size = 128
        elif is_high_ram:
            tier = "HIGH_RAM_CPU"
            num_ctx = 8192
            gpu_layers = 0
            batch_size = 256
        else:
            tier = "STANDARD_CPU"
            num_ctx = 4096
            gpu_layers = 0
            batch_size = 256

        return {
            "tier": tier,
            "num_ctx": num_ctx,
            "num_thread": threads,
            "gpu_layers": gpu_layers,
            "batch_size": batch_size,
            "f16_kv": (self.total_ram_mb > 8000),
            "recommendation_summary": (
                f"Tier: {tier} | Context: {num_ctx} tokens | Threads: {threads} | "
                f"GPU Layers: {gpu_layers} | RAM: {self.total_ram_gb} GB"
            ),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "os": f"{self.os_name} {self.os_version}",
            "arch": self.architecture,
            "cpu_model": self.cpu_model,
            "cores_physical": self.cpu_physical_cores,
            "cores_logical": self.cpu_logical_cores,
            "total_ram_mb": self.total_ram_mb,
            "available_ram_mb": self.available_ram_mb,
            "has_discrete_gpu": self.has_discrete_gpu,
            "has_cuda": self.has_cuda,
            "gpus": [g.as_dict() for g in self.gpus],
            "runtime_config": self.get_recommended_runtime_config(),
        }


class HardwareDetector:
    """Safe, non-crashing system hardware analyzer."""

    @classmethod
    def detect(cls) -> HardwareProfile:
        """Scan system hardware and return structured profile."""
        os_name = platform.system()
        os_ver = platform.release()
        arch = platform.machine()

        # 1. CPU
        cpu_model, phys_cores, log_cores = cls._detect_cpu()

        # 2. RAM
        total_ram, avail_ram = cls._detect_ram()

        # 3. GPUs
        gpus = cls._detect_gpus()
        has_cuda = any(g.cuda_available for g in gpus)
        has_discrete = any(not g.is_integrated and g.vram_mb > 1024 for g in gpus)

        return HardwareProfile(
            os_name=os_name,
            os_version=os_ver,
            architecture=arch,
            cpu_model=cpu_model,
            cpu_physical_cores=phys_cores,
            cpu_logical_cores=log_cores,
            total_ram_mb=total_ram,
            available_ram_mb=avail_ram,
            gpus=gpus,
            has_discrete_gpu=has_discrete,
            has_cuda=has_cuda,
        )

    @classmethod
    def _detect_cpu(cls) -> tuple[str, int, int]:
        model = platform.processor() or "Unknown CPU"
        log_cores = os.cpu_count() or 4
        phys_cores = max(1, log_cores // 2)

        try:
            import psutil
            phys = psutil.cpu_count(logical=False)
            if phys:
                phys_cores = phys
            log = psutil.cpu_count(logical=True)
            if log:
                log_cores = log
        except Exception:
            pass

        # Linux /proc/cpuinfo enrichment
        if sys.platform.startswith("linux") and os.path.exists("/proc/cpuinfo"):
            try:
                with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "model name" in line:
                            model = line.split(":", 1)[1].strip()
                            break
            except Exception:
                pass

        return model, phys_cores, log_cores

    @classmethod
    def _detect_ram(cls) -> tuple[int, int]:
        """Return (total_mb, available_mb)."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            return int(mem.total / (1024 * 1024)), int(mem.available / (1024 * 1024))
        except Exception:
            pass

        # Linux /proc/meminfo fallback
        if sys.platform.startswith("linux") and os.path.exists("/proc/meminfo"):
            try:
                total, avail = 0, 0
                with open("/proc/meminfo", "r", encoding="utf-8") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            total = int(line.split()[1]) // 1024
                        elif line.startswith("MemAvailable:"):
                            avail = int(line.split()[1]) // 1024
                if total > 0:
                    return total, avail or (total // 2)
            except Exception:
                pass

        # Safe defaults
        return 8192, 4096

    @classmethod
    def _detect_gpus(cls) -> list[GPUInfo]:
        gpus: list[GPUInfo] = []

        # 1. Check NVIDIA via nvidia-smi
        nvidia_gpu = cls._detect_nvidia_smi()
        if nvidia_gpu:
            gpus.append(nvidia_gpu)

        # 2. Check PyTorch CUDA if available and nvidia-smi didn't populate
        if not gpus:
            torch_gpu = cls._detect_torch_cuda()
            if torch_gpu:
                gpus.append(torch_gpu)

        # 3. Check Linux lshw / lspci for AMD / Intel / Vulkan
        if not gpus and sys.platform.startswith("linux"):
            pci_gpus = cls._detect_linux_pci_gpus()
            gpus.extend(pci_gpus)

        # 4. Check Windows WMIC / DirectX fallback
        if not gpus and sys.platform == "win32":
            win_gpus = cls._detect_windows_gpus()
            gpus.extend(win_gpus)

        # 5. Default fallback if nothing detected
        if not gpus:
            gpus.append(GPUInfo(vendor="unknown", name="Generic System Graphics", is_integrated=True))

        return gpus

    @classmethod
    def _detect_nvidia_smi(cls) -> GPUInfo | None:
        if not shutil.which("nvidia-smi"):
            return None
        try:
            cmd = ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=2.5, text=True).strip()
            if out:
                first_line = out.splitlines()[0]
                parts = [p.strip() for p in first_line.split(",")]
                name = parts[0] if len(parts) > 0 else "NVIDIA GPU"
                vram = int(float(parts[1])) if len(parts) > 1 and parts[1].replace(".", "", 1).isdigit() else 0
                driver = parts[2] if len(parts) > 2 else None
                return GPUInfo(
                    vendor="nvidia",
                    name=name,
                    vram_mb=vram,
                    cuda_available=True,
                    driver_version=driver,
                    is_integrated=False,
                )
        except Exception:
            pass
        return None

    @classmethod
    def _detect_torch_cuda(cls) -> GPUInfo | None:
        try:
            import torch
            if torch.cuda.is_available():
                name = torch.cuda.get_device_name(0)
                vram_b = torch.cuda.get_device_properties(0).total_memory
                vram_mb = int(vram_b / (1024 * 1024))
                cap = f"{torch.cuda.get_device_capability(0)[0]}.{torch.cuda.get_device_capability(0)[1]}"
                return GPUInfo(
                    vendor="nvidia",
                    name=name,
                    vram_mb=vram_mb,
                    cuda_available=True,
                    cuda_compute_capability=cap,
                    is_integrated=False,
                )
        except Exception:
            pass
        return None

    @classmethod
    def _detect_linux_pci_gpus(cls) -> list[GPUInfo]:
        results: list[GPUInfo] = []
        if shutil.which("lspci"):
            try:
                out = subprocess.check_output(["lspci"], stderr=subprocess.DEVNULL, timeout=2.0, text=True)
                for line in out.splitlines():
                    if "VGA compatible controller" in line or "3D controller" in line:
                        lower = line.lower()
                        if "nvidia" in lower:
                            results.append(GPUInfo(vendor="nvidia", name=line.split(":", 2)[-1].strip()))
                        elif "amd" in lower or "radeon" in lower or "advanced micro devices" in lower:
                            results.append(GPUInfo(vendor="amd", name=line.split(":", 2)[-1].strip()))
                        elif "intel" in lower:
                            results.append(GPUInfo(vendor="intel", name=line.split(":", 2)[-1].strip(), is_integrated=True))
            except Exception:
                pass
        return results

    @classmethod
    def _detect_windows_gpus(cls) -> list[GPUInfo]:
        results: list[GPUInfo] = []
        try:
            cmd = ["wmic", "path", "win32_VideoController", "get", "name,adapterram", "/format:csv"]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=3.0, text=True)
            for line in out.splitlines():
                parts = [p.strip() for p in line.split(",") if p.strip()]
                if len(parts) >= 2 and parts[0] != "Node":
                    ram_b = int(parts[0]) if parts[0].isdigit() else 0
                    name = parts[1]
                    vram_mb = ram_b // (1024 * 1024)
                    lower = name.lower()
                    vendor = "nvidia" if "nvidia" in lower else ("amd" if "amd" in lower or "radeon" in lower else "intel")
                    results.append(GPUInfo(
                        vendor=vendor,
                        name=name,
                        vram_mb=vram_mb,
                        is_integrated=("intel" in lower or "uhd" in lower or "iris" in lower),
                    ))
        except Exception:
            pass
        return results
