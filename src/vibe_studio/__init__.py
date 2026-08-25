"""Vibe Studio package."""
import sys
import glob
from pathlib import Path

# Auto-link local virtual environment site-packages if running from workspace
_root = Path(__file__).resolve().parents[2]
_venv_sites = glob.glob(str(_root / ".venv" / "lib" / "python3.*" / "site-packages"))
for _sp in _venv_sites:
    if _sp not in sys.path:
        sys.path.insert(0, _sp)

__all__ = ["__version__"]
__version__ = "0.1.0"

