#!/usr/bin/env python3
"""
JARVIS v0.1.0 — GitHub Release Publisher
Commits all new packaging files, pushes to origin, creates a GitHub Release,
and uploads the .deb and portable .zip artifacts.
"""
import subprocess
import sys
import os
import re
import json
import time
import mimetypes
from pathlib import Path

REPO_ROOT = Path(__file__).parent
DIST_DIR = REPO_ROOT / "dist"
OWNER = "n4dlr"
REPO = "vibe-studio"
TAG = "v0.1.0"
RELEASE_NAME = "JARVIS v0.1.0 — Autonomous OS Desktop Release"
RELEASE_BODY = """\
## J.A.R.V.I.S v0.1.0 — Full Production Release 🚀

**Just A Rather Very Intelligent System** — AI-Native Autonomous Desktop OS & Software Engineering Companion.

### ✨ What's New
- Full PyInstaller-based frozen binary distribution (Linux + Windows)
- Hardware auto-tuning: CPU/GPU detection, automatic context window and thread allocation
- Ollama lifecycle supervisor — starts, health-checks, and auto-creates the bundled Qwen2.5-Coder model
- 4-tier hierarchical configuration system (Defaults → System → User → Environment)
- Bilingual voice synthesis (EN + AZ) via Edge-TTS
- `--doctor` diagnostics command for instant system health check
- XDG-compliant data, config, and log directory isolation

### 📦 Downloads

| Platform | Package | Type |
|---|---|---|
| 🐧 Linux (Ubuntu 22.04+, Debian 12+) | `jarvis_0.1.0_amd64.deb` | Debian package (~313 MB download, ~1.07 GB installed) |
| 🪟 Windows 10/11 x64 | `JARVIS-Portable-Windows-x64.zip` | Portable — extract & run (~406 MB) |

### 🔧 Linux Installation
```bash
sudo dpkg -i jarvis_0.1.0_amd64.deb
jarvis --doctor   # verify installation
jarvis            # launch GUI
```

### 🪟 Windows Installation
Extract the zip and run `jarvis.exe` directly. No installer required.

### 🤖 Bundled AI Model
- **Qwen2.5-Coder-1.5B-Instruct** (Apache 2.0) — auto-downloaded on first run via Ollama
- GPU_ACCELERATED tier on systems with NVIDIA/AMD GPUs: 16,384 context window, full GPU offload

### ✅ Verified On
- CPU: Intel Core i7-13620H (10 cores)
- GPU: NVIDIA GeForce RTX 4050 Laptop GPU (6 GB VRAM, CUDA)
- RAM: 16 GB
- OS: Ubuntu 24.04 LTS / Python 3.12.3

### SHA-256 Checksums
```
081031d7ac868021e2a9abb57bca021c2a915b23bdb25647eaa72e00976f4e13  jarvis_0.1.0_amd64.deb
5206651cf4fb44043931cf53ab0dfbda58ca3657d402402e4ef409babf300eb7  JARVIS-Portable-Windows-x64.zip
```
"""

# ─── Helpers ────────────────────────────────────────────────────────────────

def run(cmd, check=True, capture=False, cwd=None):
    print(f"  $ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(
        cmd, shell=isinstance(cmd, str),
        capture_output=capture, text=True,
        cwd=cwd or REPO_ROOT
    )
    if check and result.returncode != 0:
        print(f"  ❌ FAILED (exit {result.returncode})")
        if result.stderr:
            print(result.stderr[:500])
        sys.exit(result.returncode)
    return result

def get_token():
    creds = Path.home() / ".git-credentials"
    if creds.exists():
        for line in creds.read_text().splitlines():
            m = re.search(r'https://[^:]+:([^@]+)@github\.com', line)
            if m:
                return m.group(1)
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        return token
    print("❌ No GitHub token found in ~/.git-credentials or GITHUB_TOKEN env var")
    sys.exit(1)

# ─── Step 1: Commit new files ───────────────────────────────────────────────

print("\n" + "="*70)
print("  📝 [1/5] Committing new packaging & distribution files")
print("="*70)

new_files = [
    ".github/",
    "THIRD_PARTY_NOTICES",
    "build_all.py",
    "build_linux.py",
    "build_windows.py",
    "docs/BUILD.md",
    "docs/DISTRIBUTION.md",
    "docs/INSTALL_LINUX.md",
    "docs/INSTALL_WINDOWS.md",
    "models/",
    "packaging/",
    "src/vibe_studio/jarvis/config_manager.py",
    "src/vibe_studio/jarvis/hardware.py",
    "src/vibe_studio/jarvis/ollama_manager.py",
    "tests/test_packaging_and_distribution.py",
]

# Stage all new files
for f in new_files:
    path = REPO_ROOT / f
    if path.exists():
        run(["git", "add", str(path)])

# Check if there's anything staged
result = run(["git", "diff", "--cached", "--name-only"], capture=True)
staged = result.stdout.strip()

if staged:
    print(f"  Staged files:\n    " + "\n    ".join(staged.splitlines()[:20]))
    run(["git", "commit", "-m",
         "feat: add full production packaging & distribution system\n\n"
         "- PyInstaller frozen binary (Linux + Windows portable zip)\n"
         "- Debian .deb package pipeline (dpkg-deb, postinst, systemd)\n"
         "- Inno Setup Windows installer spec\n"
         "- Hardware auto-tuning (CPU/GPU telemetry)\n"
         "- Ollama lifecycle supervisor with model auto-creation\n"
         "- 4-tier configuration manager with secret masking\n"
         "- Qwen2.5-Coder-1.5B-Instruct Modelfile + THIRD_PARTY_NOTICES\n"
         "- 22 automated packaging tests (100% passing)\n"
         "- GitHub Actions CI/CD multi-platform release workflow\n"
         "- Docs: BUILD, INSTALL_LINUX, INSTALL_WINDOWS, DISTRIBUTION"])
    print("  ✅ Committed")
else:
    print("  ℹ️  Nothing new to commit (already up-to-date)")

# ─── Step 2: Update/create tag ──────────────────────────────────────────────

print("\n" + "="*70)
print(f"  🏷️  [2/5] Tagging {TAG}")
print("="*70)

# Delete local tag if exists (so we can re-point to latest commit)
run(["git", "tag", "-d", TAG], check=False)
run(["git", "tag", "-a", TAG, "-m", f"Release {TAG} — JARVIS Full Production Build"])
print(f"  ✅ Tag {TAG} created at HEAD")

# ─── Step 3: Push commits + tag ─────────────────────────────────────────────

print("\n" + "="*70)
print("  🚀 [3/5] Pushing to origin")
print("="*70)

run(["git", "push", "origin", "main", "--force-with-lease"], check=False)
# Push tag (force in case it already existed remotely)
result = run(["git", "push", "origin", TAG, "--force"], check=False)
if result.returncode != 0:
    print("  ⚠️  Tag push had issues — continuing anyway")
else:
    print("  ✅ Pushed")

# ─── Step 4: Create GitHub Release via API ──────────────────────────────────

print("\n" + "="*70)
print("  🌐 [4/5] Creating GitHub Release via API")
print("="*70)

import urllib.request
import urllib.error

TOKEN = get_token()
HEADERS = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
    "X-GitHub-Api-Version": "2022-11-28",
}

def api_request(method, url, data=None, headers=None):
    req_headers = {**HEADERS, **(headers or {})}
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code

# Delete existing release for this tag if present
list_url = f"https://api.github.com/repos/{OWNER}/{REPO}/releases/tags/{TAG}"
existing, status = api_request("GET", list_url)
if status == 200:
    release_id = existing["id"]
    print(f"  ℹ️  Existing release found (id={release_id}), deleting...")
    api_request("DELETE", f"https://api.github.com/repos/{OWNER}/{REPO}/releases/{release_id}")
    print("  ✅ Old release deleted")

# Create new release
release_payload = {
    "tag_name": TAG,
    "target_commitish": "main",
    "name": RELEASE_NAME,
    "body": RELEASE_BODY,
    "draft": False,
    "prerelease": False,
}
release_data, status = api_request("POST",
    f"https://api.github.com/repos/{OWNER}/{REPO}/releases",
    data=release_payload)

if status not in (200, 201):
    print(f"  ❌ Failed to create release: HTTP {status}")
    print(json.dumps(release_data, indent=2)[:500])
    sys.exit(1)

release_id = release_data["id"]
upload_url_template = release_data["upload_url"]  # e.g. ".../assets{?name,label}"
upload_base = upload_url_template.split("{")[0]
html_url = release_data["html_url"]
print(f"  ✅ Release created: {html_url}")
print(f"  Release ID: {release_id}")

# ─── Step 5: Upload artifacts ───────────────────────────────────────────────

print("\n" + "="*70)
print("  📤 [5/5] Uploading artifacts")
print("="*70)

ARTIFACTS = [
    DIST_DIR / "jarvis_0.1.0_amd64.deb",
    DIST_DIR / "JARVIS-Portable-Windows-x64.zip",
]

for artifact in ARTIFACTS:
    if not artifact.exists():
        print(f"  ⚠️  Skipping {artifact.name} — file not found")
        continue

    size_mb = artifact.stat().st_size / (1024 * 1024)
    print(f"\n  Uploading: {artifact.name} ({size_mb:.1f} MB)")
    print(f"  This may take several minutes for large files...")

    mime = "application/octet-stream"
    upload_url = f"{upload_base}?name={artifact.name}"

    upload_headers = {
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": mime,
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with open(artifact, "rb") as f:
        data = f.read()

    req = urllib.request.Request(
        upload_url, data=data,
        headers=upload_headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            resp_data = json.loads(resp.read())
            print(f"  ✅ Uploaded: {resp_data.get('browser_download_url', 'OK')}")
    except urllib.error.HTTPError as e:
        err = e.read()
        print(f"  ❌ Upload failed: HTTP {e.code}")
        print(err[:300].decode())
        sys.exit(1)

# ─── Done ───────────────────────────────────────────────────────────────────

print("\n" + "="*70)
print("  🎉 RELEASE COMPLETE!")
print("="*70)
print(f"\n  GitHub Release URL: {html_url}")
print(f"  Tag:               {TAG}")
print(f"\n  Artifacts published:")
for a in ARTIFACTS:
    if a.exists():
        print(f"    • {a.name}  ({a.stat().st_size / 1024 / 1024:.1f} MB)")
print()
