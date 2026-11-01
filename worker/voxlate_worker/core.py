"""Pure pipeline logic (no models, no audio devices) so it can be unit-tested.

- LocalAgreement: revisable ASR hypotheses -> immutable source commits.
- PhraseScheduler: clause-aware Hindi/English translation units with a max-wait budget.
- OutputMixer: what reaches the virtual cable. Translated/original/both, mute, epochs, backlog bound.
"""
import re
import threading
import unicodedata
from collections import deque
from dataclasses import dataclass, field

import numpy as np

Word = tuple  # (text, start_s_abs, end_s_abs)


def _norm(w: str) -> str:
    # Keep letters, combining marks and digits. Not re's \w: it drops Devanagari vowel signs (कि == की == क).
    return "".join(c for c in w.lower() if unicodedata.category(c)[0] in "LMN")


class LocalAgreement:
    """LocalAgreement-2: commit the word prefix two consecutive ASR passes agree on."""

    def __init__(self):
        self.prev: list = []

    def update(self, words: list) -> list:
        n = 0
        while n < min(len(words), len(self.prev)) and _norm(words[n][0]) == _norm(self.prev[n][0]):
            n += 1
        self.prev = words[n:]
        return words[:n]

    def reset(self):
        self.prev = []


HI_AUX = {"है", "हैं", "था", "थे", "थी", "थीं", "हूँ", "हूं", "हो", "होगा", "होगी", "होंगे"}
HI_FUTURE_SUFFIX = ("गा", "गी", "गे")
CONJ = {
    "hi": {"और", "लेकिन", "पर", "कि", "तो", "क्योंकि", "जब", "अगर", "मगर", "फिर"},
    "en": {"and", "but", "because", "so", "which", "when", "if", "or", "then"},
}
PUNCT_END = (".", "?", "!", "।", ",", ";", ":", "|")


@dataclass
class Unit:
    text: str
    t_start: float
    t_end: float
    forced: bool
    src: str = ""
    tgt: str = ""
    epoch: int = 0


class PhraseScheduler:
    """Turns committed words into translation units at safe clause boundaries.

    Hindi is verb-final, so we wait for an auxiliary/future verb ending or punctuation
    rather than translating a subject/object prefix. A unit is force-flushed when it
    spans more than max_span seconds (bounded wait, never invents content).
    """

    def __init__(self, lang: str, min_words: int = 3, max_span: float = 4.0):
        self.lang, self.min_words, self.max_span = lang, min_words, max_span
        self.pending: list = []

    def _emit(self, forced=False) -> list:
        if not self.pending:
            return []
        u = Unit(" ".join(w[0] for w in self.pending), self.pending[0][1], self.pending[-1][2], forced)
        self.pending = []
        return [u]

    def _is_boundary(self, w: str) -> bool:
        if w.endswith(PUNCT_END):
            return True
        if self.lang == "hi":
            core = w.strip("".join(PUNCT_END))
            return core in HI_AUX or core.endswith(HI_FUTURE_SUFFIX)
        return False

    def add(self, words: list) -> list:
        out = []
        for w in words:
            if _norm(w[0]) in CONJ[self.lang] and len(self.pending) >= self.min_words + (self.lang == "en"):
                out += self._emit()
            self.pending.append(w)
            if self._is_boundary(w[0]) and len(self.pending) >= self.min_words:
                out += self._emit()
        if self.pending and self.pending[-1][2] - self.pending[0][1] >= self.max_span:
            out += self._emit(forced=True)
        return out

    def end_of_speech(self) -> list:
        return self._emit()

    def reset(self):
        self.pending = []


@dataclass
class Segment:
    audio: np.ndarray  # float32 mono at the output device rate
    epoch: int
    seg_id: int
    src_start: float  # monotonic time the source speech started
    src_end: float
    ready: float = 0.0
    pos: int = field(default=0)


class OutputMixer:
    """Renders the virtual-cable signal. Called from the audio callback, so keep it short.

    Leak guarantee: original mic audio is only accepted and only mixed when mode is
    'original' or 'both'. In 'translated' mode, or when muted/failed, it is dropped.
    """

    MODES = ("translated", "original", "both")

    def __init__(self, rate: int, max_backlog_s: float = 15.0):
        self.rate = rate
        self.max_backlog = int(max_backlog_s * rate)
        # ponytail: one short lock shared with the audio callback; lock-free SPSC ring if glitches show up.
        self.lock = threading.Lock()
        self.segs: deque = deque()
        self.orig: deque = deque()
        self.orig_len = 0
        self.orig_cap = int(0.25 * rate)  # bounds mic/cable clock drift in passthrough
        self.mode = "translated"
        self.muted = False
        self.failed = False
        self.epoch = 0
        self.started: deque = deque(maxlen=256)  # (segment, monotonic first-play time)
        self.last_rms = 0.0

    def set_mode(self, mode: str):
        assert mode in self.MODES, mode
        with self.lock:
            self.mode = mode
            self.orig.clear()
            self.orig_len = 0

    def cancel(self) -> int:
        """Invalidate everything queued; returns the new epoch."""
        with self.lock:
            self.epoch += 1
            self.segs.clear()
            self.orig.clear()
            self.orig_len = 0
            return self.epoch

    def backlog_samples(self) -> int:
        with self.lock:
            return sum(len(s.audio) - s.pos for s in self.segs)

    def push_segment(self, seg: Segment) -> str:
        with self.lock:
            if seg.epoch != self.epoch:
                return "stale"
            if sum(len(s.audio) - s.pos for s in self.segs) + len(seg.audio) > self.max_backlog:
                return "full"
            self.segs.append(seg)
            return "ok"

    def push_original(self, x: np.ndarray):
        with self.lock:
            if self.mode == "translated" or self.muted or self.failed:
                return
            self.orig.append(x)
            self.orig_len += len(x)
            while self.orig_len > self.orig_cap:
                self.orig_len -= len(self.orig.popleft())

    def render(self, n: int, now: float) -> np.ndarray:
        out = np.zeros(n, np.float32)
        with self.lock:
            if self.muted or self.failed:
                self.orig.clear()
                self.orig_len = 0
                self.last_rms = 0.0
                return out
            if self.mode != "original":
                i = 0
                while i < n and self.segs:
                    s = self.segs[0]
                    if s.pos == 0:
                        self.started.append((s, now + i / self.rate))
                    k = min(n - i, len(s.audio) - s.pos)
                    out[i:i + k] += s.audio[s.pos:s.pos + k]
                    s.pos += k
                    i += k
                    if s.pos >= len(s.audio):
                        self.segs.popleft()
            if self.mode != "translated":
                i = 0
                while i < n and self.orig:
                    b = self.orig[0]
                    k = min(n - i, len(b))
                    out[i:i + k] += b[:k]
                    i += k
                    self.orig_len -= k
                    if k == len(b):
                        self.orig.popleft()
                    else:
                        self.orig[0] = b[k:]
        np.clip(out, -1.0, 1.0, out=out)
        self.last_rms = float(np.sqrt(np.mean(out * out))) if n else 0.0
        return out


def percentile(xs, p):
    return float(np.percentile(np.asarray(xs), p)) if len(xs) else None
