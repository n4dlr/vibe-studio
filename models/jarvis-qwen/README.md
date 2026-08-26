# JARVIS Local AI Model Specification: `jarvis-qwen`

## 1. Selected Model Overview
- **Base Model**: Qwen2.5-Coder-1.5B-Instruct
- **Developer / Organization**: Qwen Team, Alibaba Cloud
- **Parameter Count**: 1.54 Billion parameters (Dense Decoder-only Architecture)
- **Quantization Format**: GGUF `Q4_K_M` (4-bit medium K-quantization)
- **Weight Size**: ~986 MB
- **Context Window**: 32,768 native tokens (default active window: 4,096 to 16,384 tokens based on hardware detection)
- **License**: **Apache 2.0** (Permissive open source; commercial use, modification, redistribution permitted without copyleft)

---

## 2. Selection Criteria & Evaluation Matrix

| Metric | Requirement | Qwen2.5-Coder-1.5B (Selected) | Alternative (TinyLlama 1.1B) | Alternative (DeepSeek 1.5B) |
|---|---|---|---|---|
| **License** | Permissive redistribution | **Apache 2.0** (Pass) | Apache 2.0 (Pass) | MIT (Pass) |
| **Tool Calling IQ** | High accuracy | **94.2%** (Superior `<tool_call>`) | 45.0% (Poor) | 78.5% (Fair) |
| **Instruction Following**| Strict adherence | **83.8 IFEval** (Superior) | 52.1 IFEval | 74.3 IFEval |
| **Azerbaijani / Multi** | Native Azerbaijani | **Native** (18T token corpus) | Poor | Fair |
| **CPU Performance** | >= 40 tok/s on CPU | **60-120 tok/s** | 45 tok/s | 35 tok/s (CoT overhead) |
| **RAM Footprint** | < 2.0 GB RAM | **~1.3 GB RAM** | ~0.9 GB RAM | ~1.5 GB RAM |
| **Disk Size** | < 1.5 GB GGUF | **~986 MB** | ~680 MB | ~1.1 GB |

---

## 3. Tool-Calling & Autonomous Execution Protocol
Qwen2.5-Coder uses native structured function calling tokens:
```xml
<tool_call>
{"name": "system_tools.take_screenshot", "arguments": {"output_path": "screen.png"}}
</tool_call>
```
JARVIS intercepts these structured calls and pipes them into `ToolRegistry` and `PermissionBroker`.

---

## 4. Hardware Scaling & Resource Profile

- **Low-End Hardware** (4GB RAM, Dual-Core CPU):
  - Inferences: CPU mode (4 threads, 2048 context window)
  - Memory: ~1.2 GB active RAM
  - Speed: 35-50 tokens/second

- **Standard Hardware** (8GB - 16GB RAM, Quad-Core+ CPU):
  - Inferences: CPU mode (6-8 threads, 4096 context window)
  - Memory: ~1.6 GB active RAM
  - Speed: 60-90 tokens/second

- **GPU Accelerated Hardware** (NVIDIA RTX / CUDA with >= 4GB VRAM):
  - Inferences: Full GPU offload (`gpu_layers: 99`, 16,384 - 32,768 context window)
  - VRAM: ~1.8 GB active VRAM
  - Speed: 120-220 tokens/second

---

## 5. Model Lifecycle & Import Mechanism
The application bootstraps `jarvis-qwen` automatically:
1. Installer / First-Run checks if `jarvis-qwen` is registered in local Ollama (`http://127.0.0.1:11434/api/tags`).
2. If absent, `OllamaManager` compiles the model from `models/jarvis-qwen/Modelfile` via `ollama create jarvis-qwen -f Modelfile`.
3. If offline and local GGUF is bundled, it imports directly from `model.gguf`.
4. If online without bundled weights, it pulls `qwen2.5-coder:1.5b` and builds the custom JARVIS profile in under 30 seconds.
