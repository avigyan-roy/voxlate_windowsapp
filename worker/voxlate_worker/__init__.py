"""Voxlate local translation worker (Windows). Driven by the Qt app over stdin/stdout JSON lines."""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "Voxlate"
DATA_DIR.mkdir(parents=True, exist_ok=True)
# All model weights live in one per-user folder, separate from app source.
MODELS_DIR = DATA_DIR / "models"
os.environ.setdefault("HF_HOME", str(MODELS_DIR / "hf"))
COMPLETE = ".voxlate_complete"  # written by fetch_models after a repo downloaded fully


def model_dir(repo: str) -> Path:
    """Plain-file copy of a HF repo (snapshot_download local_dir: no symlinks, no Developer Mode)."""
    return MODELS_DIR / repo.split("/")[-1]
