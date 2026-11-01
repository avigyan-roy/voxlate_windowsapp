"""Worker process. Protocol: one JSON object per line.

App -> worker  {"cmd": ...}
  list_devices | path_check{playback,recording} | load_models
  start{mic,cable,src,tgt,mode} | stop | mute{on} | set_mode{mode} | set_languages{src,tgt}
  enroll_start{mic} | enroll_stop | enroll_play | enroll_save | enroll_discard | profile_delete | profile_status
  shutdown
Worker -> app  {"ev": ...}
  devices | state{state,detail} | models{status,...} | level | delay | warning | muted
  path_check{ok,...} | enroll{phase,...} | profile{exists,...} | error{detail}

stdout carries only protocol lines; library prints are redirected to stderr (log file).
EOF on stdin (app gone) == shutdown, so devices are always released.
"""
import faulthandler
import json
import os
import sys
import threading
import time
import traceback

import numpy as np

from . import profile


class Worker:
    def __init__(self, emit):
        self.emit = emit
        self.models = None
        self.engine = None
        self.loaded = threading.Event()
        self.loading = False
        self.load_error = None
        self.rec = None
        self.take = None  # (audio, sr, quality) awaiting save

    # ---------------------------------------------------------------- helpers
    def _bg(self, fn, *a):
        def run():
            try:
                fn(*a)
            except BaseException as e:  # incl. SystemExit from libraries (e.g. spaCy's auto-download)
                traceback.print_exc()
                self.emit("error", detail=str(e))
        threading.Thread(target=run, daemon=True).start()

    def _profile_status(self):
        self.emit("profile", exists=profile.exists(), script=profile.SCRIPT, **{k: profile.meta().get(k) for k in ("created", "seconds", "quality")})

    # ---------------------------------------------------------------- commands
    def handle(self, msg):
        cmd = msg.get("cmd")
        fn = getattr(self, "cmd_" + str(cmd), None)
        if not fn:
            return self.emit("error", detail=f"unknown command {cmd}")
        fn(msg)

    def cmd_list_devices(self, m):
        try:
            from . import devices
            self.emit("devices", **devices.list_devices())
        except Exception as e:  # e.g. PortAudio missing: the UI must not spin forever
            traceback.print_exc()
            self.emit("devices", inputs=[], cable=None, mic_blocked=False, error=f"Audio devices unavailable: {e}")

    def cmd_profile_status(self, m):
        self._profile_status()

    def cmd_path_check(self, m):
        if self.engine and self.engine.running:
            return self.emit("path_check", ok=False, hint="Stop translation before running the audio path check.")
        if self.loading:  # model loading starves the audio threads: the check then fails as "device busy" or times out
            return self.emit("path_check", ok=False, reason="loading",
                             hint="The engine is still loading models (status \"Starting\"). Wait until it says "
                                  "\"Ready\", then press Retry.")
        def check():  # always answers with a path_check event, so the UI never stays on "Checking..."
            try:
                from . import pathcheck
                r = pathcheck.run(m["playback"], m["recording"])
            except BaseException as e:
                traceback.print_exc()
                r = {"ok": False, "reason": "error", "hint": f"Audio check failed: {type(e).__name__}: {e}"}
            print(f"[pathcheck] result {r}", file=sys.stderr, flush=True)
            self.emit("path_check", **r)
        threading.Thread(target=check, daemon=True).start()

    def cmd_load_models(self, m):
        if self.loaded.is_set() and not m.get("reload") and not self.load_error:
            return self.emit("models", status="ready", **self.models.info)
        if self.loading and not m.get("reload"):  # app asks again after mic confirm; one load at a time
            return
        self.loaded.clear()
        self.loading = True

        def load():
            from .engine import Engine
            from .models import Models
            self.emit("models", status="loading", detail="Loading local models…")
            log = lambda s: self.emit("models", status="loading", detail=s)
            try:
                t = time.monotonic()
                if self.engine:
                    self.engine.stop(quiet=True)
                self.engine = None
                if m.get("voice_only") and self.models and not self.load_error:
                    self.models.load_voice(log)
                else:  # drop the old bundle before building a new one: two never fit in 4 GB VRAM
                    self.models = None
                    import gc
                    gc.collect()
                    from .models import _torch
                    if _torch().cuda.is_available():
                        _torch().cuda.empty_cache()
                    self.models = Models(log=log)
                self.engine = Engine(self.models, self.emit)
                self.load_error = None
                print(f"[models] ready in {time.monotonic() - t:.1f} s on {self.models.device}", file=sys.stderr, flush=True)
                self.emit("models", status="ready", load_s=round(time.monotonic() - t, 1), **self.models.info)
            except BaseException as e:  # SystemExit too: a silent thread death left the UI on "Starting"
                traceback.print_exc()
                self.load_error = f"{type(e).__name__}: {e}"
                self.emit("models", status="error", detail=self.load_error)
            finally:
                self.loading = False
                self.loaded.set()
        self._bg(load)

    def cmd_start(self, m):
        def go():
            self.emit("state", state="Starting", detail="Waiting for models…")
            self.loaded.wait()
            if self.load_error:
                return self.emit("state", state="Error", detail="Models failed to load: " + self.load_error)
            try:
                self.engine.start(m["mic"], m["cable"], m["src"], m["tgt"], m.get("mode", "translated"))
            except Exception as e:
                traceback.print_exc()
                self.engine.stop(quiet=True)
                self.emit("state", state="Error", detail=f"Could not start audio: {e}")
        self._bg(go)

    def cmd_stop(self, m):
        if self.engine:
            self.engine.stop()
        else:
            self.emit("state", state="Stopped", detail="")

    def cmd_mute(self, m):
        if self.engine:
            self.engine.set_mute(bool(m.get("on")))

    def cmd_set_mode(self, m):
        if self.engine:
            self.engine.set_mode(m["mode"])

    def cmd_set_languages(self, m):
        if self.engine:
            self.engine.set_languages(m["src"], m["tgt"])

    # ---------------------------------------------------------------- enrollment
    def cmd_enroll_start(self, m):
        if self.engine and self.engine.running:
            return self.emit("enroll", phase="error", detail="Stop translation before recording your voice.")
        self.rec = profile.Recorder(m["mic"])
        self.emit("enroll", phase="recording")

        r = self.rec

        def meter():
            while self.rec is r:
                self.emit("enroll", phase="recording", level=round(r.level, 4),
                          seconds=round(time.monotonic() - r.t0, 1))
                time.sleep(0.2)
        threading.Thread(target=meter, daemon=True).start()

    def cmd_enroll_stop(self, m):
        if not self.rec:
            return
        rec, self.rec = self.rec, None
        audio = rec.stop()

        def check():  # always leaves the "recording" phase, so the page never stays on a frozen counter
            try:
                if not len(audio) or not np.abs(audio).max():
                    return self.emit("enroll", phase="error", detail=(
                        "The microphone delivered only silence. Check that it isn't muted (keyboard mic key, "
                        "Sound settings > Recording > Levels) or pick another microphone, then record again."))
                q = profile.quality(audio, rec.sr)
            except Exception as e:
                traceback.print_exc()
                return self.emit("enroll", phase="error", detail=f"Could not check the recording: {e}")
            self.take = (audio, rec.sr, q)
            self.emit("enroll", phase="review", quality=q)
        self._bg(check)

    def cmd_enroll_play(self, m):
        if self.take:
            profile.play(self.take[0], self.take[1])
        elif profile.exists():
            profile.play(*profile.load())

    def cmd_enroll_discard(self, m):
        self.take = None
        self.emit("enroll", phase="idle")

    def cmd_enroll_save(self, m):
        if not self.take:
            return
        audio, sr, q = self.take
        profile.save(audio, sr, q)
        self.take = None
        self.emit("enroll", phase="saved", quality=q)
        self._profile_status()
        self.cmd_load_models({"reload": True, "voice_only": True})  # recompute voice conditioning

    def cmd_profile_delete(self, m):
        if self.engine and self.engine.running:
            self.engine.stop()
        profile.delete()
        self._profile_status()
        self.cmd_load_models({"reload": True, "voice_only": True})

    def shutdown(self):
        if self.rec:
            self.rec.stop()
        if self.engine:
            self.engine.stop(quiet=True)


def _pipe_alive(fd: int) -> bool:
    """True if fd is a pipe whose writer (the app) is still connected."""
    if os.name != "nt":
        return False
    import ctypes
    import msvcrt
    try:
        h = msvcrt.get_osfhandle(fd)
    except OSError:
        return False
    return bool(ctypes.windll.kernel32.PeekNamedPipe(ctypes.c_void_p(h), None, 0, None, None, None))


def _commands(fd: int = 0):
    """Command lines from the app. In the app a read on the live pipe sometimes returned 0 bytes while the GPU
    was busy (worker.log: PeekNamedPipe OK, app alive), and Python's line iterator took that as EOF and the
    engine quit mid-translation. Only a pipe that is really broken (app gone) ends the loop."""
    buf, spurious = b"", 0
    while True:
        data = os.read(fd, 65536)
        if not data:
            if _pipe_alive(fd):
                spurious += 1
                if spurious in (1, 10, 100) or spurious % 1000 == 0:
                    print(f"[worker] empty read on a live command pipe (x{spurious}); still listening",
                          file=sys.stderr, flush=True)
                time.sleep(0.05)
                continue
            break
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if line.strip():
                yield line.decode("utf-8", "replace")
    if buf.strip():
        yield buf.decode("utf-8", "replace")


def main():
    # Local-only at runtime: never reach the network during a call. Models come from fetch_models.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    faulthandler.enable()  # native crashes (CUDA, PortAudio) leave a traceback in worker.log
    print(f"voxlate worker start: python {sys.version.split()[0]} at {sys.executable}, cwd {os.getcwd()}",
          file=sys.stderr, flush=True)
    proto = sys.stdout
    sys.stdout = sys.stderr
    proto.reconfigure(encoding="utf-8")
    lock = threading.Lock()

    def emit(ev, **kw):
        line = json.dumps({"ev": ev, **kw}, ensure_ascii=False, default=str)
        with lock:
            proto.write(line + "\n")
            proto.flush()

    w = Worker(emit)
    emit("hello", version=1)
    # Import the whole model stack here, before the first blocking read on the command pipe. The pipe is
    # synchronous, so it serves one operation at a time: SciPy's Fortran extensions (scipy.linalg, scipy.optimize,
    # ...) probe stdin while their DLLs initialise, and doing that in the load thread while this loop waited in
    # ReadFile hung model loading at "Loading translation" until the next command arrived. Commands sent
    # meanwhile wait in the pipe. (Swapping fd 0 for NUL also fixed it, but in the app the pipe then read as EOF.)
    t = time.monotonic()
    try:
        from .models import _torch, indic_processor
        _torch()  # first: registers torch's CUDA DLL folder, which ctranslate2 (faster_whisper) needs on the GPU
        import scipy.linalg, scipy.optimize, scipy.signal, scipy.sparse.linalg  # noqa: E401,F401
        import faster_whisper, transformers, kokoro, misaki.en, librosa, sounddevice, soxr, silero_vad  # noqa: E401,F401
        import openvoice.models  # noqa: F401
        indic_processor()
    except Exception:
        traceback.print_exc()  # the real import happens again at load time and reports properly there
    print(f"[worker] model libraries imported in {time.monotonic() - t:.1f} s", file=sys.stderr, flush=True)
    why = "command pipe closed (EOF)"
    for line in _commands(sys.stdin.fileno()):
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            emit("error", detail="bad json")
            continue
        print(f"[cmd] {msg.get('cmd')}", file=sys.stderr, flush=True)  # command names only, never content
        if msg.get("cmd") == "shutdown":
            why = "shutdown command"
            break
        try:
            w.handle(msg)
        except Exception as e:
            traceback.print_exc()
            emit("error", detail=f"{msg.get('cmd')}: {e}")
    print(f"[worker] exiting: {why}", file=sys.stderr, flush=True)
    w.shutdown()
    try:
        emit("bye")
    except OSError:  # the app may already be gone
        pass


if __name__ == "__main__":
    main()
