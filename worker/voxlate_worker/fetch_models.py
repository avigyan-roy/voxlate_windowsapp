"""Download model weights once (setup time) and record exact resolved revisions.

  python -m voxlate_worker.fetch_models            # default commercial-clean path
  python -m voxlate_worker.fetch_models --nllb     # + NLLB comparison (non-commercial)
  python -m voxlate_worker.fetch_models --xtts     # + XTTS-v2 comparison (non-commercial, asks to accept CPML)

Each repo goes to %LOCALAPPDATA%\\Voxlate\\models\\<name> as plain files (no symlinks, so no
Developer Mode). Finished repos are skipped on re-run; partial ones resume.
Writes %LOCALAPPDATA%\\Voxlate\\models\\manifest.json.
"""
import argparse
import json
import os
import threading
import time

from . import COMPLETE, MODELS_DIR, model_dir

# Gated repos come first so a missing token / unaccepted terms fails before GBs of other downloads.
# Keep in sync with $gated in setup_worker.ps1.
GATED = {
    "ai4bharat/indictrans2-indic-en-dist-200M": "MIT",
    "ai4bharat/indictrans2-en-indic-dist-200M": "MIT",
}
BASE = {
    **GATED,
    "Systran/faster-whisper-small": "MIT",
    "dropbox-dash/faster-whisper-large-v3-turbo": "MIT",  # formerly mobiuslabsgmbh/ (renamed on the Hub)
    "hexgrad/Kokoro-82M": "Apache-2.0",
    "myshell-ai/OpenVoiceV2": "MIT",
}
NLLB = {"facebook/nllb-200-distilled-600M": "CC-BY-NC-4.0 (non-commercial)"}
PATTERNS = {"myshell-ai/OpenVoiceV2": ["converter/*"],
            "hexgrad/Kokoro-82M": ["config.json", "kokoro-v1_0.pth", "voices/*"]}  # what models.py loads
TRIES = 3


def classify(e: Exception, repo: str) -> tuple:
    """-> (retryable, hint) for a download failure."""
    from huggingface_hub.utils import RepositoryNotFoundError

    status = getattr(getattr(e, "response", None), "status_code", None)
    if isinstance(e, RepositoryNotFoundError) or status in (401, 403):  # GatedRepoError is a subclass
        return False, (f"Access denied (HTTP {status or '401/403'}). Set HF_TOKEN to a valid Hugging Face Read token "
                       f"and accept the model terms at https://huggingface.co/{repo} while logged in.")
    if getattr(e, "winerror", None) == 1314:
        return False, ("WinError 1314: Windows refused to create a symlink (privilege not held). "
                       "This downloader writes plain files; delete the half-done model folder and run Repair setup.")
    if getattr(e, "winerror", None) == 112 or getattr(e, "errno", None) == 28:
        return False, "Disk full. Free space on the drive holding %LOCALAPPDATA% and run Repair setup."
    return True, "Network or server problem (connection dropped, timeout or Hub hiccup)."


def _size_gb(d) -> float:
    total = 0
    for root, _, files in os.walk(d):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / 2**30


def fetch(repo: str) -> str:
    """Download one repo into its local folder with retries. -> resolved commit sha."""
    from huggingface_hub import HfApi, snapshot_download

    d = model_dir(repo)
    done = threading.Event()

    def heartbeat():  # HF progress bars are off (they garble the setup log); report bytes on disk instead
        while not done.wait(20):
            print(f"    ... {repo}: {_size_gb(d):.2f} GB on disk", flush=True)

    threading.Thread(target=heartbeat, daemon=True).start()
    try:
        for attempt in range(1, TRIES + 1):
            try:
                sha = HfApi().model_info(repo).sha
                snapshot_download(repo, revision=sha, local_dir=d, allow_patterns=PATTERNS.get(repo))
                return sha
            except Exception as e:
                retry, hint = classify(e, repo)
                print(f"  attempt {attempt}/{TRIES} failed: {type(e).__name__}: {e}", flush=True)
                if not retry or attempt == TRIES:
                    raise SystemExit(f"FAILED {repo}\n  {type(e).__name__}: {e}\n  Hint: {hint}")
                wait = 10 * attempt
                print(f"  {hint} Retrying in {wait} s ...", flush=True)
                time.sleep(wait)
    finally:
        done.set()


def main():
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "60")       # read when huggingface_hub is imported
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    ap = argparse.ArgumentParser()
    ap.add_argument("--nllb", action="store_true")
    ap.add_argument("--xtts", action="store_true")
    a = ap.parse_args()
    repos = {**BASE, **(NLLB if a.nllb else {})}
    out = MODELS_DIR / "manifest.json"
    manifest = json.loads(out.read_text()) if out.exists() else {"models": {}}
    manifest["fetched"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    for repo, lic in repos.items():
        marker = model_dir(repo) / COMPLETE
        if marker.exists():
            print(f"OK (already downloaded) {repo}", flush=True)
            sha = marker.read_text().strip()
        else:
            print(f"Downloading {repo} ({lic}) ...", flush=True)
            t = time.monotonic()
            sha = fetch(repo)
            marker.write_text(sha)
            print(f"OK {repo} ({_size_gb(model_dir(repo)):.2f} GB, {time.monotonic() - t:.0f} s)", flush=True)
        manifest["models"][repo] = {"license": lic, "revision": sha, "path": str(model_dir(repo))}
    if a.xtts:
        print("XTTS-v2 is licensed under the Coqui Public Model License: NON-COMMERCIAL use only, "
              "including its outputs. See https://coqui.ai/cpml")
        print("Type AGREE to accept and download:", flush=True)
        if input().strip() != "AGREE":
            raise SystemExit("XTTS skipped.")
        os.environ["COQUI_TOS_AGREED"] = "1"
        from TTS.utils.manage import ModelManager
        ModelManager().download_model("tts_models/multilingual/multi-dataset/xtts_v2")
        manifest["models"]["coqui/XTTS-v2"] = {"license": "CPML (non-commercial)", "revision": "coqui-tts default"}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2))
    print(f"OK. Manifest: {out}")


if __name__ == "__main__":
    main()
