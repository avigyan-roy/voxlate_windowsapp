"""Windows audio endpoint discovery (WASAPI via PortAudio/sounddevice).

Devices are identified by name (stable across launches), not list index.
Virtual endpoints are excluded from the physical-mic list to prevent loops.
"""
import os
import sys

import sounddevice as sd

VIRTUAL_HINTS = ("cable", "vb-audio", "voicemeeter", "virtual")
CABLE_HINTS = ("cable", "vb-audio")
# VB-CABLE defaults (matched case-insensitively, preferred over other cable-like names); override for another product.
CABLE_PLAYBACK = os.environ.get("VOXLATE_CABLE_PLAYBACK", "CABLE Input")    # we write here
CABLE_RECORDING = os.environ.get("VOXLATE_CABLE_RECORDING", "CABLE Output")  # Meet reads here

MIC_PRIVACY_FIX = ("Windows is blocking microphone access. Open Settings > Privacy & security > Microphone, "
                   "turn on \"Microphone access\" and \"Let desktop apps access your microphone\", then press Retry.")


def com_init():
    """WASAPI needs COM on the calling thread. PortAudio initialises it only on the thread that imported
    sounddevice, so streams opened/closed from worker threads failed with PaErrorCode -9999. Idempotent."""
    if os.name == "nt":
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED; S_FALSE / RPC_E_CHANGED_MODE are fine


def _api() -> int:
    for i, a in enumerate(sd.query_hostapis()):
        if "WASAPI" in a["name"]:
            return i
    return sd.default.hostapi


def wasapi_settings():
    return sd.WasapiSettings(auto_convert=True) if "WASAPI" in sd.query_hostapis(_api())["name"] else None


def is_virtual(name: str) -> bool:
    return any(h in name.lower() for h in VIRTUAL_HINTS)


def _devs():
    com_init()  # every stream open looks its device up here first
    api = _api()
    return [(i, d) for i, d in enumerate(sd.query_devices()) if d["hostapi"] == api]


def mic_blocked() -> bool:
    """True if Windows privacy settings (or policy) deny desktop apps the microphone.
    Capture then opens fine but delivers silence, so it must be checked explicitly."""
    if os.name != "nt":
        return False
    import winreg

    base = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
    checks = [(winreg.HKEY_LOCAL_MACHINE, base, "Value", "Deny"),           # "Microphone access" (device-wide)
              (winreg.HKEY_CURRENT_USER, base, "Value", "Deny"),            # "Microphone access" (this user)
              (winreg.HKEY_CURRENT_USER, base + r"\NonPackaged", "Value", "Deny"),  # "Let desktop apps access..."
              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Policies\Microsoft\Windows\AppPrivacy", "LetAppsAccessMicrophone", 2)]
    for root, key, name, deny in checks:
        try:
            with winreg.OpenKey(root, key) as k:
                if winreg.QueryValueEx(k, name)[0] == deny:
                    return True
        except OSError:
            pass
    return False


def log_devices():
    """Every endpoint PortAudio sees, to worker.log (stderr)."""
    apis = sd.query_hostapis()
    for i, d in enumerate(sd.query_devices()):
        print(f"[devices] #{i} {apis[d['hostapi']]['name']} | {d['name']} | in={d['max_input_channels']} "
              f"out={d['max_output_channels']} sr={d['default_samplerate']:.0f}", file=sys.stderr, flush=True)


def _cable(devs, kind: str, preferred: str):
    """Best cable-like endpoint of one direction: exact VB-CABLE name first, then any 'cable'/'vb-audio' name."""
    key = f"max_{kind}_channels"
    names = [d["name"] for _, d in devs if d[key] > 0 and any(h in d["name"].lower() for h in CABLE_HINTS)]
    names.sort(key=lambda n: (preferred.lower() not in n.lower(), "virtual cable" not in n.lower(), len(n)))
    return names[0] if names else None


def list_devices() -> dict:
    log_devices()
    devs = _devs()
    inputs = [d["name"] for _, d in devs if d["max_input_channels"] > 0 and not is_virtual(d["name"])]
    play = _cable(devs, "output", CABLE_PLAYBACK)
    rec = _cable(devs, "input", CABLE_RECORDING)
    return {"inputs": inputs, "cable": {"playback": play, "recording": rec} if play and rec else None,
            "mic_blocked": mic_blocked()}


def find(name: str, kind: str) -> tuple:
    """-> (index, default_samplerate, max_channels). kind is 'input' or 'output'."""
    key = f"max_{kind}_channels"
    for i, d in _devs():
        if d["name"] == name and d[key] > 0:
            return i, int(d["default_samplerate"]), d[key]
    raise LookupError(f"Audio device not found: {name}")


def default_output_physical() -> tuple:
    """Speakers/headphones for enrollment playback; never the cable."""
    outs = [(i, d) for i, d in _devs() if d["max_output_channels"] > 0 and not is_virtual(d["name"])]
    if not outs:
        raise LookupError("No physical output device")
    default_name = sd.query_devices(sd.default.device[1])["name"] if sd.default.device[1] >= 0 else None
    i, d = next(((i, d) for i, d in outs if d["name"] == default_name), outs[0])
    return i, int(d["default_samplerate"])
