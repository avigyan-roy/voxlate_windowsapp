"""Streaming translation engine.

  mic InputStream (20 ms blocks, timestamped)
     -> in_q (bounded)  -> ASR thread: resample 16k, Silero VAD, Whisper passes,
                                       LocalAgreement commits, PhraseScheduler units
     -> unit_q (bounded) -> synth thread: translate -> TTS/voice -> resample
     -> OutputMixer (epoch-checked, bounded backlog) -> cable OutputStream

Cancellation: every unit/segment carries the epoch it was created in. Mute, language
change, stop, backlog overflow and failure bump the epoch; stale work is dropped.
Fail closed: any pipeline/device error silences the cable and stops streams.
"""
import queue
import threading
import time
from collections import deque

import numpy as np

from .core import LocalAgreement, OutputMixer, PhraseScheduler, Segment, Unit, percentile

ASR_HOP_S = 0.6           # run a Whisper pass after this much new speech
MAX_BUF_S = 12.0          # hard cap on unresolved ASR audio
PREROLL_CHUNKS = 10       # ~0.3 s kept before VAD start so onsets are not clipped
WATCHDOG_S = 1.5          # no device callbacks for this long => device lost
DELAYED_BACKLOG_S = 4.0   # report "delayed" above this much queued translated audio


class Engine:
    def __init__(self, models, emit):
        self.m, self.emit = models, emit
        self.mixer = OutputMixer(48000)
        self.in_q: queue.Queue = queue.Queue(maxsize=150)   # ~3 s of 20 ms blocks
        self.unit_q: queue.Queue = queue.Queue(maxsize=6)
        self.src, self.tgt = "hi", "en"
        self.running = False
        self.delays = deque(maxlen=30)
        self.stats = {"in_overflow": 0, "backlog_skips": 0, "segments": 0}
        self._stop = threading.Event()
        self._threads = []
        self._streams = []
        self._seg_id = 0
        self._last_in = self._last_out = 0.0
        self._in_rms = 0.0
        self.vad = None
        self._reset_ingest()

    # ------------------------------------------------------------ control
    @property
    def epoch(self):
        return self.mixer.epoch

    def start(self, mic: str, cable: str, src: str, tgt: str, mode: str):
        import sounddevice as sd
        import soxr

        from . import devices

        self.stop(quiet=True)
        in_i, self.in_sr, _ = devices.find(mic, "input")
        out_i, out_sr, out_ch = devices.find(cable, "output")
        self.mixer = OutputMixer(out_sr)
        self.mixer.set_mode(mode)
        self.src, self.tgt = src, tgt
        self.vad = self.m.vad_factory()
        self._reset_ingest()
        self._orig_rs = soxr.ResampleStream(self.in_sr, out_sr, 1, dtype="float32") if self.in_sr != out_sr else None
        self._stop.clear()
        ws = devices.wasapi_settings()
        self._out_ch = min(2, out_ch)
        self._streams = [
            sd.OutputStream(device=out_i, samplerate=out_sr, channels=self._out_ch, dtype="float32",
                            blocksize=int(out_sr * 0.02), latency="low", extra_settings=ws, callback=self._out_cb),
            sd.InputStream(device=in_i, samplerate=self.in_sr, channels=1, dtype="float32",
                           blocksize=int(self.in_sr * 0.02), latency="low", extra_settings=ws, callback=self._in_cb),
        ]
        self._out_lat = self._streams[0].latency
        self._in_lat = self._streams[1].latency
        now = time.monotonic()
        self._last_in = self._last_out = now
        for s in self._streams:
            s.start()
        self.running = True
        self._threads = [threading.Thread(target=f, daemon=True) for f in (self._asr_loop, self._synth_loop, self._status_loop)]
        for t in self._threads:
            t.start()
        self.emit("state", state="Translating", detail=self._label())

    def stop(self, quiet=False):
        self.running = False
        self._stop.set()
        self.mixer.cancel()
        if self._streams:
            from . import devices
            devices.com_init()  # stop() runs on worker threads too
        for s in self._streams:
            try:
                s.stop()
                s.close()
            except Exception:
                pass
        self._streams = []
        for t in self._threads:
            if t is not threading.current_thread():
                t.join(timeout=2)
        self._threads = []
        self._drain()
        if not quiet:
            self.emit("state", state="Stopped", detail="")

    def set_mute(self, on: bool):
        self.mixer.muted = on
        self.mixer.cancel()  # queued translated speech is discarded, not delayed
        self.emit("muted", on=on)

    def set_mode(self, mode: str):
        self.mixer.set_mode(mode)
        if self.running:
            self.emit("state", state="Translating", detail=self._label())

    def set_languages(self, src: str, tgt: str):
        assert {src, tgt} == {"hi", "en"}
        self.src, self.tgt = src, tgt
        self.mixer.cancel()
        if self.running:
            self.emit("state", state="Translating", detail=self._label())

    def _label(self):
        names = {"hi": "Hindi", "en": "English"}
        return f"{names[self.src]} → {names[self.tgt]} · {self.mixer.mode}"

    def _fail(self, msg: str):
        """Fail closed: silence the cable immediately, then tear down off the audio thread."""
        if not self.running:
            return
        self.mixer.failed = True
        self.mixer.cancel()
        self.running = False
        self.emit("state", state="Error", detail=msg)
        threading.Thread(target=self.stop, kwargs={"quiet": True}, daemon=True).start()

    def _drain(self):
        for q in (self.in_q, self.unit_q):
            while True:
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

    # ------------------------------------------------------------ audio callbacks (no blocking work here)
    def _in_cb(self, indata, frames, tinfo, status):
        now = time.monotonic()
        self._last_in = now
        x = indata[:, 0].copy()
        self._in_rms = float(np.sqrt(np.mean(x * x)))
        if self.mixer.muted or self.mixer.failed:
            return
        if self.mixer.mode != "translated":
            self.mixer.push_original(self._orig_rs.resample_chunk(x) if self._orig_rs else x)
        if self.mixer.mode != "original":
            try:
                self.in_q.put_nowait((x, now - self._in_lat - frames / self.in_sr, self.epoch))
            except queue.Full:
                self.stats["in_overflow"] += 1
                self._overflowed = True

    def _out_cb(self, outdata, frames, tinfo, status):
        self._last_out = time.monotonic()
        outdata[:] = self.mixer.render(frames, self._last_out + self._out_lat)[:, None]

    # ------------------------------------------------------------ ASR side
    def _reset_ingest(self):
        self._pend = np.zeros(0, np.float32)
        self._pend_t = None
        self._preroll = deque(maxlen=PREROLL_CHUNKS)
        self._in_speech = False
        self._buf = np.zeros(0, np.float32)
        self._buf_t0 = 0.0
        self._since_asr = 0
        self._committed_text = ""
        self._agree = LocalAgreement()
        self._sched = PhraseScheduler(self.src)
        self._ingest_epoch = self.epoch
        self._overflowed = False
        if self.vad:
            self.vad.reset()

    def _asr_loop(self):
        import soxr

        rs = soxr.ResampleStream(self.in_sr, 16000, 1, dtype="float32")
        while not self._stop.is_set():
            try:
                x, t, ep = self.in_q.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if ep != self.epoch:
                    continue
                if ep != self._ingest_epoch or self._overflowed:  # new epoch or discontinuity: start clean
                    self._reset_ingest()
                self.ingest(rs.resample_chunk(x), t)
            except Exception as e:
                self._fail(f"Speech recognition failed: {e}")

    def ingest(self, y: np.ndarray, t: float):
        """y: 16 kHz mono block whose first sample was captured at monotonic time t."""
        if self._pend_t is None or not len(self._pend):
            self._pend_t = t
        self._pend = np.concatenate([self._pend, y])
        while len(self._pend) >= 512:
            chunk, self._pend = self._pend[:512], self._pend[512:]
            tc = self._pend_t
            self._pend_t += 512 / 16000
            ev = self.vad(chunk)
            if not self._in_speech:
                self._preroll.append((chunk, tc))
                if ev == "start":
                    self._in_speech = True
                    self._buf_t0 = self._preroll[0][1]
                    self._buf = np.concatenate([c for c, _ in self._preroll])
                    self._preroll.clear()
                    self._since_asr = 0
                continue
            self._buf = np.concatenate([self._buf, chunk])
            self._since_asr += 512
            if ev == "end":
                self._finish_utterance()
            elif self._since_asr >= ASR_HOP_S * 16000:
                self._asr_pass()

    def _words(self):
        ws = self.m.asr.words(self._buf, self.src, self._committed_text[-200:])
        return [(w, self._buf_t0 + s, self._buf_t0 + e) for w, s, e in ws]

    def _asr_pass(self):
        self._since_asr = 0
        words = self._words()
        commit = self._agree.update(words)
        if len(self._buf) > MAX_BUF_S * 16000 and not commit:  # never resolves: commit what we have
            commit, self._agree.prev = words, []
        if commit:
            self._commit(commit)
            cut = int((commit[-1][2] - self._buf_t0) * 16000)
            cut = max(0, min(cut, len(self._buf)))
            self._buf = self._buf[cut:]
            self._buf_t0 += cut / 16000

    def _finish_utterance(self):
        words = self._words() if len(self._buf) > 0.2 * 16000 else []
        self._agree.reset()
        self._commit(words, final=True)
        self._in_speech = False
        self._buf = np.zeros(0, np.float32)

    def _commit(self, words, final=False):
        if words:
            self._committed_text += " " + " ".join(w[0] for w in words)
        units = self._sched.add(words) + (self._sched.end_of_speech() if final else [])
        for u in units:
            u.src, u.tgt, u.epoch = self.src, self.tgt, self._ingest_epoch
            try:
                self.unit_q.put_nowait(u)
            except queue.Full:
                self._skip_backlog()

    def _skip_backlog(self):
        """Explicit, visible cancellation instead of unbounded lag."""
        self.stats["backlog_skips"] += 1
        self.mixer.cancel()
        self.emit("warning", detail="Translation fell behind; queued speech was skipped.")

    # ------------------------------------------------------------ synthesis side
    def _synth_loop(self):
        while not self._stop.is_set():
            try:
                u = self.unit_q.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self.synthesize(u)
            except Exception as e:
                self._fail(f"Translation/voice failed: {e}")

    def synthesize(self, u: Unit):
        import soxr

        if u.epoch != self.epoch:
            return
        text = self.m.mt(u.text, u.src, u.tgt)
        if not text or u.epoch != self.epoch:
            return
        audio, sr = self.m.tts(text, u.tgt)
        if not len(audio) or u.epoch != self.epoch:
            return
        if sr != self.mixer.rate:
            audio = soxr.resample(audio, sr, self.mixer.rate)
        self._seg_id += 1
        seg = Segment(audio.astype(np.float32), u.epoch, self._seg_id, u.t_start, u.t_end, ready=time.monotonic())
        r = self.mixer.push_segment(seg)
        if r == "full":
            self._skip_backlog()
        elif r == "ok":
            self.stats["segments"] += 1

    # ------------------------------------------------------------ status / watchdog
    def _status_loop(self):
        while not self._stop.wait(0.25):
            now = time.monotonic()
            if now - self._last_in > WATCHDOG_S:
                self._fail("Microphone stopped delivering audio (unplugged or taken by another app).")
                return
            if now - self._last_out > WATCHDOG_S:
                self._fail("Virtual cable output stopped (device removed or disabled).")
                return
            while self.mixer.started:
                seg, played = self.mixer.started.popleft()
                self.delays.append(played - seg.src_start)
            backlog = self.mixer.backlog_samples() / self.mixer.rate
            self.emit("level", mic=round(self._in_rms, 4), out=round(self.mixer.last_rms, 4),
                      backlog_s=round(backlog, 2), delayed=backlog > DELAYED_BACKLOG_S)
            if self.delays:
                self.emit("delay", last=round(self.delays[-1], 2), p50=round(percentile(self.delays, 50), 2),
                          p95=round(percentile(self.delays, 95), 2), n=len(self.delays))
