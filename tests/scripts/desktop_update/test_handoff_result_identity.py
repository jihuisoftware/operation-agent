"""Real PowerShell producer/heartbeat/result contract (portable, not native UI proof)."""
from __future__ import annotations

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[3]
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


