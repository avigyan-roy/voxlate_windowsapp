"""Owner voice profile: consented enrollment, local storage encrypted with Windows DPAPI
(bound to the logged-in Windows user), quality check, replay, delete."""
import ctypes
import io
import json
import shutil
import time
from ctypes import wintypes

import numpy as np

from . import DATA_DIR

PROFILE_DIR = DATA_DIR / "profile"
REF = PROFILE_DIR / "reference.wav.dpapi"
META = PROFILE_DIR / "meta.json"
SR = 24000  # stored reference rate
SCRIPT_VERSION = 1

# Shown to the user. English + Roman Hindi only (no Devanagari), ~45-60 s read aloud.
SCRIPT = """ENGLISH
Hello! I am recording this short sample so Voxlate can learn the sound of my voice.
Today the weather is pleasant, and I am planning to finish my work a little early.
Could you please send me the report by Thursday afternoon?
The numbers look good: twenty-five, forty-eight, and one hundred and twelve.
I don't think we need another meeting this week, but let me know if anything changes.

HINDI (Roman script)
Namaste! Main Voxlate ke liye apni awaaz record kar raha hoon (ya: kar rahi hoon).
Aaj mausam bahut achha hai, aur main apna kaam jaldi khatam karna chahta hoon (ya: chahti hoon).
Kya aap mujhe kal tak report bhej sakte hain?
Mujhe lagta hai ki yeh project bahut achha chalega.
Hum shukravaar ko teen baje phir se baat karenge. Dhanyavaad!"""


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data, len(data))
    src, dst = _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), _Blob()
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(dst)):  # 0x1 = UI_FORBIDDEN
        raise OSError("DPAPI failed: profile belongs to another Windows user or is corrupted")
    try:
        return ctypes.string_at(dst.pbData, dst.cbData)
    finally:
        kernel32.LocalFree(dst.pbData)


def _median_f0(audio: np.ndarray, sr: int, loud: np.ndarray, f: int, fmin=65.0, fmax=400.0):
    """Coarse speaking pitch (only picks a low/high base voice) by autocorrelation of loud 30 ms frames.
    Replaces librosa.yin, whose first-call JIT compile took ~30 s and left the UI frozen after Stop."""
    lo, hi = int(sr / fmax), int(sr / fmin)
    if f <= hi:
        return None
    f0s = []
    for k in np.flatnonzero(loud)[:400]:
        x = audio[k * f:(k + 1) * f]
        x = x - x.mean()
        ac = np.fft.irfft(np.abs(np.fft.rfft(x, 2 * f)) ** 2)[:hi + 1]
        if ac[0] <= 0:
            continue
        lag = lo + int(np.argmax(ac[lo:hi + 1]))
        if ac[lag] / ac[0] > 0.3:  # clearly periodic (voiced)
            f0s.append(sr / lag)
    return float(np.median(f0s)) if f0s else None


def quality(audio: np.ndarray, sr: int) -> dict:
    """Simple, explainable checks: enough voiced speech, signal-to-noise, clipping."""
    f = int(0.03 * sr)
    frames = audio[: len(audio) // f * f].reshape(-1, f)
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(1)) + 1e-9)
    floor, speech = np.percentile(db, 10), np.percentile(db, 90)
    voiced_s = float((db > floor + 10).sum() * 0.03)
    clip = float((np.abs(audio) > 0.99).mean())
    f0 = _median_f0(audio, sr, db > floor + 10, f) if len(db) else None
    q = {
        "voiced_s": round(voiced_s, 1),
        "snr_db": round(float(speech - floor), 1),
        "clipping_pct": round(100 * clip, 3),
        "median_f0": round(f0, 1) if f0 else None,
        "peak_dbfs": round(float(20 * np.log10(np.abs(audio).max() + 1e-9)), 1),
    }
    problems = []
    if voiced_s < 20:
        problems.append(f"Only {voiced_s:.0f}s of speech detected; read the full script (need 20s+).")
    if q["snr_db"] < 15:
        problems.append("Too much background noise; record in a quieter room.")
    if clip > 0.005:
        problems.append("Recording is clipping; move away from the mic or lower input volume.")
    if q["peak_dbfs"] < -30:
        problems.append("Recording is very quiet; move closer or raise mic volume.")
    q["ok"], q["problems"] = not problems, problems
    return q


def exists() -> bool:
    return REF.exists() and META.exists()


def meta() -> dict:
    return json.loads(META.read_text()) if META.exists() else {}


def save(audio: np.ndarray, sr: int, q: dict):
    import soundfile as sf
    import soxr

    a = soxr.resample(audio, sr, SR) if sr != SR else audio
    bio = io.BytesIO()
    sf.write(bio, a, SR, format="WAV", subtype="PCM_16")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    REF.write_bytes(_dpapi(bio.getvalue(), True))
    for p in PROFILE_DIR.glob("cond_*"):  # old conditioning caches are now stale
        p.unlink()
    META.write_text(json.dumps({"created": time.strftime("%Y-%m-%dT%H:%M:%S"), "consent": True,
                                "script_version": SCRIPT_VERSION, "seconds": round(len(a) / SR, 1), "quality": q}))


def load() -> tuple:
    """-> (audio float32 mono, sr)."""
    import soundfile as sf

    a, sr = sf.read(io.BytesIO(_dpapi(REF.read_bytes(), False)), dtype="float32")
    return a, sr


def delete():
    shutil.rmtree(PROFILE_DIR, ignore_errors=True)


class Recorder:
    """Records enrollment audio from the confirmed physical mic."""

    MAX_S = 90

    def __init__(self, mic_name: str):
        import sounddevice as sd

        from . import devices

        i, self.sr, _ = devices.find(mic_name, "input")
        self.blocks, self.level = [], 0.0
        self.stream = sd.InputStream(device=i, samplerate=self.sr, channels=1, dtype="float32",
                                     extra_settings=devices.wasapi_settings(), callback=self._cb)
        self.stream.start()
        self.t0 = time.monotonic()

    def _cb(self, d, frames, t, status):
        if sum(map(len, self.blocks)) < self.MAX_S * self.sr:
            self.blocks.append(d[:, 0].copy())
        self.level = float(np.sqrt(np.mean(d * d)))

    def stop(self) -> np.ndarray:
        self.stream.stop()
        self.stream.close()
        return np.concatenate(self.blocks) if self.blocks else np.zeros(0, np.float32)


def play(audio: np.ndarray, sr: int):
    """Replay on physical speakers/headphones (never the cable)."""
    import sounddevice as sd

    from . import devices

    i, _ = devices.default_output_physical()
    sd.play(audio, sr, device=i, extra_settings=devices.wasapi_settings())
