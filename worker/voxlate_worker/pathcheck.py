"""Audio path check: play a chirp into the cable playback side, record the cable
recording side (what Meet will hear), and confirm the chirp arrives.

Also checks the cable is silent beforehand, i.e. nothing else (system sounds,
another app, Windows default-device routing) is leaking into the meeting mic.
"""
import sys
import threading
import time

import numpy as np


def chirp(sr: int, dur=0.6, f0=500.0, f1=4000.0) -> np.ndarray:
    t = np.arange(int(sr * dur)) / sr
    x = 0.5 * np.sin(2 * np.pi * (f0 * t + (f1 - f0) * t * t / (2 * dur)))
    ramp = int(0.01 * sr)
    x[:ramp] *= np.linspace(0, 1, ramp)
    x[-ramp:] *= np.linspace(1, 0, ramp)
    return x.astype(np.float32)


def detect(ref: np.ndarray, rec: np.ndarray, sr: int, threshold=0.5) -> dict:
    """Normalized cross-correlation of the reference inside the recording."""
    if len(rec) < len(ref):
        return {"ok": False, "score": 0.0, "delay_ms": None}
    n = 1 << int(np.ceil(np.log2(len(rec) + len(ref))))
    corr = np.fft.irfft(np.fft.rfft(rec, n) * np.conj(np.fft.rfft(ref, n)), n)[: len(rec) - len(ref) + 1]
    k = int(np.argmax(corr))
    seg = rec[k:k + len(ref)]
    score = float(corr[k] / (np.linalg.norm(ref) * np.linalg.norm(seg) + 1e-12))
    return {"ok": score >= threshold, "score": round(score, 3), "delay_ms": round(1000 * k / sr, 1)}


def dbfs(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(x * x)) + 1e-9))


def run(playback_name: str, recording_name: str) -> dict:
    """Always returns within ~6 s. On failure: ok=False, reason in
    mic_blocked | cable_not_found | device_busy | no_signal | leak, and a user-facing hint.
    Shared-mode WASAPI (auto_convert) at each device's own default rate; the sweep is resampled."""
    import sounddevice as sd
    import soxr

    from . import devices

    res = {"ok": False, "playback": playback_name, "recording": recording_name}
    devices.log_devices()
    if devices.mic_blocked():  # capture would just return silence
        return {**res, "reason": "mic_blocked", "hint": devices.MIC_PRIVACY_FIX}
    try:
        out_i, out_sr, out_ch = devices.find(playback_name, "output")
        in_i, in_sr, _ = devices.find(recording_name, "input")
    except LookupError:  # names changed since the UI listed them: re-detect once
        cab = devices.list_devices()["cable"]
        if not cab:
            return {**res, "reason": "cable_not_found",
                    "hint": "VB-CABLE was not found (no 'CABLE Input' / 'CABLE Output' device). "
                            "Install it from vb-audio.com/Cable, reboot, then press Retry."}
        res.update(playback=cab["playback"], recording=cab["recording"])
        out_i, out_sr, out_ch = devices.find(cab["playback"], "output")
        in_i, in_sr, _ = devices.find(cab["recording"], "input")
    print(f"[pathcheck] play '{res['playback']}' @ {out_sr} Hz x{min(2, out_ch)}, "
          f"record '{res['recording']}' @ {in_sr} Hz", file=sys.stderr, flush=True)

    ws = devices.wasapi_settings()
    lead = 0.4
    sig = np.concatenate([np.zeros(int(out_sr * lead), np.float32), chirp(out_sr), np.zeros(int(out_sr * 0.6), np.float32)])
    blocks, pos, played = [], [0], threading.Event()

    def out_cb(outdata, frames, t, status):
        chunk = sig[pos[0]:pos[0] + frames]
        outdata[:len(chunk)] = chunk[:, None]
        outdata[len(chunk):] = 0
        pos[0] += frames
        if pos[0] >= len(sig):
            played.set()

    try:
        with sd.InputStream(device=in_i, samplerate=in_sr, channels=1, dtype="float32", extra_settings=ws,
                            callback=lambda d, f, t, s: blocks.append(d[:, 0].copy())):
            time.sleep(0.3)
            with sd.OutputStream(device=out_i, samplerate=out_sr, channels=min(2, out_ch), dtype="float32",
                                 extra_settings=ws, callback=out_cb):
                finished = played.wait(len(sig) / out_sr + 3)
            time.sleep(0.3)
    except sd.PortAudioError as e:
        return {**res, "reason": "device_busy",
                "hint": f"Could not open the virtual cable ({e}). Another app may hold it in exclusive mode: "
                        "close other audio apps, or in Sound settings > CABLE Input/Output > Properties > Advanced "
                        "untick 'Allow applications to take exclusive control', then press Retry."}
    if not finished:
        return {**res, "reason": "device_busy",
                "hint": "'CABLE Input' stopped accepting audio (device busy or disabled). Close other audio apps and press Retry."}
    if not blocks:
        return {**res, "reason": "no_signal",
                "hint": "'CABLE Output' delivered no audio at all. Check it is enabled in Sound settings > Recording, then press Retry."}

    rec = np.concatenate(blocks)
    if in_sr != out_sr:
        rec = soxr.resample(rec, in_sr, out_sr)
    floor = dbfs(rec[: int(out_sr * 0.25)]) if len(rec) else 0.0
    res.update(detect(chirp(out_sr), rec, out_sr))
    res["silence_dbfs"] = round(floor, 1)
    res["silent_before"] = floor < -50.0
    if not res["ok"]:
        res["reason"] = "no_signal"
        res["hint"] = ("The test tone did not arrive on 'CABLE Output'. In Sound settings make sure CABLE Input and "
                       "CABLE Output are enabled and not muted, then press Retry. Reinstall VB-CABLE and reboot if it persists.")
    elif not res["silent_before"]:
        res["reason"] = "leak"
        res["hint"] = ("Other audio is reaching the virtual microphone. Make sure 'CABLE Input' is NOT your "
                       "Windows default playback device and no other app plays into it.")
    res["ok"] = bool(res["ok"] and res["silent_before"])
    return res
