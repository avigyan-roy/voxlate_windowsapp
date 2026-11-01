"""Pipeline logic tests: no models, no audio devices. Run on Windows:
    .venv\\Scripts\\python -m unittest discover -s tests -v
Covers: phrase commits, cancellation, buffer overflow, mic unplug, stop/mute, no-original-leak.
"""
import sys
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voxlate_worker import pathcheck  # noqa: E402
from voxlate_worker.core import LocalAgreement, OutputMixer, PhraseScheduler, Segment, Unit  # noqa: E402
from voxlate_worker.engine import Engine  # noqa: E402


def W(*texts, t0=0.0, step=0.3):
    return [(t, t0 + i * step, t0 + i * step + 0.25) for i, t in enumerate(texts)]


class TestCommits(unittest.TestCase):
    def test_local_agreement_commits_only_stable_prefix(self):
        la = LocalAgreement()
        self.assertEqual(la.update(W("मैं", "कल")), [])
        c = la.update(W("मैं", "कल", "रिपोर्ट"))
        self.assertEqual([w[0] for w in c], ["मैं", "कल"])
        self.assertEqual(la.update(W("भेज")), [])  # 'रिपोर्ट' revised away -> not committed

    def test_hindi_waits_for_verb(self):
        s = PhraseScheduler("hi")
        self.assertEqual(s.add(W("मैं", "कल", "रिपोर्ट")), [])  # no verb yet -> WAIT
        u = s.add(W("भेज", "दूँगा।", t0=1.0))
        self.assertEqual(len(u), 1)
        self.assertEqual(u[0].text, "मैं कल रिपोर्ट भेज दूँगा।")
        self.assertFalse(u[0].forced)

    def test_hindi_negation_kept_with_verb(self):
        s = PhraseScheduler("hi")
        u = s.add(W("मुझे", "नहीं", "लगता", "कि"))
        self.assertEqual([x.text for x in u], ["मुझे नहीं लगता"])  # clause before 'कि', negation intact
        u = s.add(W("यह", "ठीक", "है", t0=2.0))
        self.assertEqual([x.text for x in u], ["कि यह ठीक है"])

    def test_english_conjunction_split(self):
        s = PhraseScheduler("en")
        u = s.add(W("I", "will", "send", "it", "and", "then", "call"))
        self.assertEqual([x.text for x in u], ["I will send it"])

    def test_max_wait_forces_flush(self):
        s = PhraseScheduler("en", max_span=2.0)
        u = s.add(W(*["word"] * 10, step=0.3))
        self.assertTrue(u and u[0].forced)

    def test_end_of_speech_flushes(self):
        s = PhraseScheduler("en")
        s.add(W("yes"))
        self.assertEqual([x.text for x in s.end_of_speech()], ["yes"])


def seg(mixer, n=480, val=0.5, **kw):
    return Segment(np.full(n, val, np.float32), kw.get("epoch", mixer.epoch), 1, 0.0, 0.0)


class TestMixer(unittest.TestCase):
    def test_translated_mode_never_leaks_original(self):
        m = OutputMixer(48000)
        m.push_original(np.ones(480, np.float32))
        self.assertEqual(np.abs(m.render(480, 0)).max(), 0.0)
        m.push_segment(seg(m, val=0.25))
        m.push_original(np.ones(480, np.float32))
        out = m.render(480, 0)
        self.assertTrue(np.allclose(out, 0.25))

    def test_both_mode_mixes(self):
        m = OutputMixer(48000)
        m.set_mode("both")
        m.push_original(np.full(480, 0.1, np.float32))
        m.push_segment(seg(m, val=0.25))
        self.assertTrue(np.allclose(m.render(480, 0), 0.35))

    def test_mute_silences_everything(self):
        m = OutputMixer(48000)
        m.set_mode("both")
        m.push_segment(seg(m))
        m.push_original(np.ones(480, np.float32))
        m.muted = True
        self.assertEqual(np.abs(m.render(480, 0)).max(), 0.0)

    def test_cancel_drops_queued_and_stale(self):
        m = OutputMixer(48000)
        old = seg(m)
        m.push_segment(old)
        m.cancel()
        self.assertEqual(m.render(480, 0).max(), 0.0)
        self.assertEqual(m.push_segment(old), "stale")

    def test_backlog_bound(self):
        m = OutputMixer(1000, max_backlog_s=1.0)
        self.assertEqual(m.push_segment(seg(m, n=800)), "ok")
        self.assertEqual(m.push_segment(seg(m, n=800)), "full")

    def test_failed_is_silent(self):
        m = OutputMixer(48000)
        m.push_segment(seg(m))
        m.failed = True
        self.assertEqual(m.render(480, 0).max(), 0.0)

    def test_first_play_time_recorded(self):
        m = OutputMixer(1000)
        m.push_segment(seg(m, n=10))
        m.render(5, 100.0)
        self.assertEqual(m.started[0][1], 100.0)


class FakeVAD:
    """Speech whenever the chunk is loud."""
    def __init__(self):
        self.on = False

    def __call__(self, c):
        loud = np.abs(c).max() > 0.1
        if loud and not self.on:
            self.on = True
            return "start"
        if not loud and self.on:
            self.on = False
            return "end"

    def reset(self):
        self.on = False


class FakeASR:
    def __init__(self):
        self.calls = 0

    def words(self, audio, lang, prompt=""):
        self.calls += 1
        return [("hello", 0.0, 0.3), ("world.", 0.3, 0.6)]


class FakeModels:
    def __init__(self):
        self.asr = FakeASR()
        self.vad_factory = FakeVAD
        self.mt = lambda text, s, t: f"[{t}] {text}"
        self.tts = lambda text, lang: (np.full(2400, 0.2, np.float32), 24000)


class TestEngine(unittest.TestCase):
    def make(self):
        ev = []
        e = Engine(FakeModels(), lambda n, **kw: ev.append((n, kw)))
        e.src, e.tgt, e.vad = "en", "hi", FakeVAD()
        e._reset_ingest()
        return e, ev

    def test_speech_to_segment(self):
        e, _ = self.make()
        e.ingest(np.full(16000, 0.5, np.float32), 10.0)
        e.ingest(np.zeros(1024, np.float32), 11.0)
        u = e.unit_q.get_nowait()
        self.assertEqual(u.text, "hello world.")
        e.synthesize(u)
        self.assertEqual(len(e.mixer.segs), 1)

    def test_epoch_cancels_inflight_unit(self):
        e, _ = self.make()
        u = Unit("hi there", 0, 1, False, "en", "hi", e.epoch)
        e.set_mute(True)
        e.synthesize(u)
        self.assertEqual(len(e.mixer.segs), 0)

    def test_unit_queue_overflow_is_visible_skip(self):
        e, ev = self.make()
        for _ in range(e.unit_q.maxsize):
            e.unit_q.put_nowait(Unit("x", 0, 0, False))
        e._commit(W("a", "b", "c."), final=True)
        self.assertEqual(e.stats["backlog_skips"], 1)
        self.assertIn("warning", [n for n, _ in ev])

    def test_mic_unplug_watchdog_fails_closed(self):
        e, ev = self.make()
        e.running = True
        e._last_in, e._last_out = time.monotonic() - 5, time.monotonic()
        e._stop.clear()
        e._status_loop()
        self.assertTrue(e.mixer.failed)
        self.assertIn(("state", {"state": "Error", "detail": "Microphone stopped delivering audio (unplugged or taken by another app)."}), ev)

    def test_stop_silences(self):
        e, _ = self.make()
        e.mixer.push_segment(seg(e.mixer))
        e.stop()
        self.assertEqual(e.mixer.render(480, 0).max(), 0.0)


class TestPathCheck(unittest.TestCase):
    def test_detects_delayed_chirp_in_noise(self):
        sr = 48000
        ref = pathcheck.chirp(sr)
        rec = np.random.default_rng(0).normal(0, 0.01, sr * 2).astype(np.float32)
        rec[12000:12000 + len(ref)] += ref * 0.8
        r = pathcheck.detect(ref, rec, sr)
        self.assertTrue(r["ok"])
        self.assertAlmostEqual(r["delay_ms"], 250.0, delta=1)

    def test_rejects_noise(self):
        sr = 48000
        rec = np.random.default_rng(1).normal(0, 0.1, sr * 2).astype(np.float32)
        self.assertFalse(pathcheck.detect(pathcheck.chirp(sr), rec, sr)["ok"])


if __name__ == "__main__":
    unittest.main()
