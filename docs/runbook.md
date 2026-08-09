# Vibe Studio IDE Operational Runbook & Architecture Reference

## Overview
This runbook describes the operational lifecycle, resource management, health monitoring, security sandboxing, and troubleshooting protocols for Vibe Studio.

---

## 1. Core Architecture & Execution Pipeline

```
UI (MainWindow)
     │
     ▼
AgentWorker (QThread) ──► ChatService ──► AutonomousAgent (FSM)
                                                │
                 ┌──────────────────────────────┴──────────────────────────────┐
                 ▼                                                             ▼
     LLM Provider (Ollama / OpenAI)                                     Tool Registry
   (Circuit Breaker + Retries)                                   (Sanitizer & Safety Checks)
                 │                                                             │
                 ▼                                                             ▼
         Streaming Output                                             Terminal / Subprocess
                                                                   (ResourceManager / process tree)
```

---

## 2. Resource Management & Process Isolation
- **ResourceManager**: Tracks every subprocess, thread, and open file handle tied to a unique `execution_id` (UUID).
- **Process Cleanup**: Upon task completion or cancellation, `ResourceManager.cleanup_execution(execution_id)` triggers process tree termination (`os.killpg` on Posix, `taskkill` on Windows).
- **Leak Prevention**: Periodic leak detection removes orphan references upon task completion.

---

## 3. Resilience & Fault Tolerance
- **Circuit Breaker**: Protected LLM providers transition to `OPEN` state after 5 consecutive failures, blocking calls for 60s before entering `HALF_OPEN` testing mode.
- **Retry Manager**: Transient network and 5xx HTTP errors automatically trigger exponential backoff retries (max 3 retries, base delay 1s).
- **Checkpoint System**: Rolling N-step execution checkpoints are written to `.vibe_studio/checkpoints/` after every step to allow crash recovery.

---

## 4. Security Sandboxing
- **Input Sanitizer**: Blocks destructive command patterns (`rm -rf /`, `del /f`, `sudo`, `chmod 777`) and path traversal attempts (`../`).
- **Path Security**: All file operations are strictly constrained within the active workspace root.
- **Audit Logging**: Structured security event records are appended to `~/.vibe_studio/audit/audit.jsonl`.

---

## 5. Troubleshooting & Diagnostics

| Symptom | Cause | Solution |
|---------|-------|----------|
| Provider returns 5xx repeatedly | LLM server down or overloaded | Check local Ollama daemon or OpenAI API key; Circuit Breaker will enter `OPEN` state to prevent hang. |
| Agent stuck in loop | Model repeatedly generating identical tool calls | Agent detects duplicate call signatures and injects system redirect after 2 repeated attempts. |
| Subprocess not terminating | Child process detached from parent | Pressing **Stop** immediately triggers `ResourceManager.cleanup_execution()` which kills process group PGID. |
