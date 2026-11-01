"""Gates 2-4 benchmark on Windows, no meeting needed.

  # Gate 2: both directions on sample files (or synthetic Kokoro speech if you have none yet)
  python -m voxlate_worker.bench --src hi --tgt en --synthetic
  python -m voxlate_worker.bench --src hi --tgt en --wav clips\\hi_01.wav clips\\hi_02.wav
  # Gate 4: real-time streaming replay through the actual Engine -> p50/p95 latency
  python -m voxlate_worker.bench --src hi --tgt en --wav clips\\hi_long.wav --stream
  # Compare paths: set VOXLATE_MT / VOXLATE_TTS / VOXLATE_ASR before running.

Results: bench_results\\<time>.json, a row appended to bench_results\\RESULTS.md, and output WAVs
to listen to. Source/translated text is written to the JSON so a bilingual reviewer can judge adequacy.
"""
import argparse
import json
import os
import threading
import time
from pathlib import Path

import numpy as np

SENTENCES = {
    "hi": ["मैं कल सुबह रिपोर्ट भेज दूँगा।", "मुझे नहीं लगता कि यह मीटिंग आज खत्म होगी।",
           "कृपया मुझे पच्चीस हज़ार रुपये का बिल भेज दीजिए।", "क्या आप शुक्रवार को तीन बजे फ्री हैं?"],
    "en": ["I will send the report tomorrow morning.", "I don't think this meeting will finish today.",
           "Please send me the invoice for twenty five thousand rupees.", "Are you free on Friday at three o'clock?"],
}
OUT = Path("bench_results")


def load_wav(p, sr=16000):
    import soundfile as sf
    import soxr

    a, s = sf.read(p, dtype="float32", always_2d=True)
    return soxr.resample(a.mean(1), s, sr) if s != sr else a.mean(1)


def rss_mb():
    import psutil
    return round(psutil.Process().memory_info().rss / 2**20)


def offline(m, clips, src, tgt):
    import soundfile as sf
    import soxr

    rows = []
    for name, audio in clips:
        t0 = time.perf_counter()
        words = m.asr.words(audio, src)
        t1 = time.perf_counter()
        text = " ".join(w[0] for w in words)
        tr = m.mt(text, src, tgt)
        t2 = time.perf_counter()
        wav, sr = m.tts(tr, tgt)
        t3 = time.perf_counter()
        sf.write(OUT / f"{name}_{src}2{tgt}.wav", wav, sr)
        rows.append({"clip": name, "audio_s": round(len(audio) / 16000, 2), "asr_s": round(t1 - t0, 3),
                     "mt_s": round(t2 - t1, 3), "tts_s": round(t3 - t2, 3), "out_audio_s": round(len(wav) / sr, 2),
                     "source_text": text, "translation": tr})
        print(f"{name}: ASR {t1-t0:.2f}s MT {t2-t1:.2f}s TTS {t3-t2:.2f}s")
    return rows


def stream(m, clips, src, tgt):
    """Feed audio at real-time pace through the real Engine (no devices). Latency = speech onset of a
    unit -> its translated audio being ready to play (excludes ~20-60 ms device output buffer)."""
    from .core import OutputMixer
    from .engine import Engine

    ev = []
    e = Engine(m, lambda name, **kw: ev.append((name, kw)))
    e.mixer = OutputMixer(24000, max_backlog_s=60)
    e.src, e.tgt, e.in_sr = src, tgt, 16000
    e.vad = m.vad_factory()
    e._reset_ingest()
    e.running = True
    th = threading.Thread(target=e._synth_loop, daemon=True)
    th.start()
    for _, audio in clips:
        block = 320  # 20 ms
        t_start = time.monotonic()
        for i in range(0, len(audio), block):
            target = t_start + i / 16000
            time.sleep(max(0, target - time.monotonic()))
            e.ingest(audio[i:i + block], time.monotonic())
        for _ in range(int(1.0 * 16000 / block)):  # trailing silence so VAD closes the utterance
            e.ingest(np.zeros(block, np.float32), time.monotonic())
    deadline = time.monotonic() + 30
    while e.unit_q.qsize() and time.monotonic() < deadline:
        time.sleep(0.1)
    time.sleep(3)  # let the in-flight unit finish synthesis
    e._stop.set()
    segs = list(e.mixer.segs)
    lat = [s.ready - s.src_start for s in segs]
    lat_end = [s.ready - s.src_end for s in segs]
    pct = lambda xs, p: round(float(np.percentile(xs, p)), 2) if xs else None
    res = {"segments": len(segs), "onset_to_ready_p50": pct(lat, 50), "onset_to_ready_p95": pct(lat, 95),
           "end_to_ready_p50": pct(lat_end, 50), "end_to_ready_p95": pct(lat_end, 95),
           "backlog_skips": e.stats["backlog_skips"], "warnings": [kw for n, kw in ev if n in ("warning", "state")]}
    print(json.dumps(res, indent=2, ensure_ascii=False))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", choices=["hi", "en"], required=True)
    ap.add_argument("--tgt", choices=["hi", "en"], required=True)
    ap.add_argument("--wav", nargs="*", default=[])
    ap.add_argument("--synthetic", action="store_true", help="generate source speech with Kokoro (smoke test only)")
    ap.add_argument("--stream", action="store_true")
    a = ap.parse_args()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    OUT.mkdir(exist_ok=True)
    from .models import Models

    t = time.perf_counter()
    m = Models(log=print)
    load_s = time.perf_counter() - t
    clips = [(Path(p).stem, load_wav(p)) for p in a.wav]
    if a.synthetic:
        import soxr
        for i, s in enumerate(SENTENCES[a.src]):
            clips.append((f"synthetic_{a.src}_{i}", soxr.resample(m.tts._kokoro(s, a.src) if hasattr(m.tts, "_kokoro")
                                                                     else m.tts(s, a.src)[0], 24000, 16000)))
    if not clips:
        raise SystemExit("Give --wav files or --synthetic")
    res = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "direction": f"{a.src}->{a.tgt}", "load_s": round(load_s, 1),
           **m.info, "offline": offline(m, clips, a.src, a.tgt)}
    if a.stream:
        res["stream"] = stream(m, clips, a.src, a.tgt)
    res["peak_vram_mb"], res["rss_mb"] = m.peak_vram_mb(), rss_mb()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    (OUT / f"{stamp}.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    md = OUT / "RESULTS.md"
    if not md.exists():
        md.write_text("| time | dir | device | ASR | MT | TTS | voice | ASR s (mean) | MT s | TTS s | stream onset p50/p95 | peak VRAM MB | RSS MB |\n"
                      "|---|---|---|---|---|---|---|---|---|---|---|---|---|\n", encoding="utf-8")
    o = res["offline"]
    mean = lambda k: round(sum(r[k] for r in o) / len(o), 2)
    st = res.get("stream", {})
    with md.open("a", encoding="utf-8") as f:
        f.write(f"| {res['time']} | {res['direction']} | {res['device']} | {res['asr']} | {res['mt']} | {res['tts']} | "
                f"{res['voice']} | {mean('asr_s')} | {mean('mt_s')} | {mean('tts_s')} | "
                f"{st.get('onset_to_ready_p50')}/{st.get('onset_to_ready_p95')} | {res['peak_vram_mb']} | {res['rss_mb']} |\n")
    print(f"Saved {OUT / (stamp + '.json')}")


if __name__ == "__main__":
    main()
