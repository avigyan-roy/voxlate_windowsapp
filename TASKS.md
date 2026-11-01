# Voxlate Windows MVP · living task tracker

Spec: `instructions/VOXLATE_FINAL_SPEC_AND_CLAUDE_PROMPT.docx` (17 Oct 2026; overrides WINDOWS_APP.md / PIPELINE.md for MVP).
Status legend: ✅ verified with evidence · 🟡 code written, **NEEDS WINDOWS VERIFICATION** · ⬜ not started · ⛔ blocked

> Owner instruction (17 Oct 2026): *Windows app only; do not run anything on Ubuntu.* All code below was written on Ubuntu and **has not been executed**. The only automated check performed was a parse-only Python syntax check (passed). **No test, benchmark or latency number exists yet.**

## 0. Inventory (Gate 0)

| Item | State |
|---|---|
| Next.js website + Groq/Fish recorded-audio demo (`../Voxlate-Waitlist-Website`) | EXISTING · untouched, preserved |
| Native Windows app, local pipeline, virtual-mic routing, enrollment, installer | Did not exist → **TO BUILD** → now written in this folder (UNVERIFIED) |
| Hardware | Lenovo LOQ 15IAX9, i5-12450HX (12 threads), RTX 2050 4 GB, ~10 GB usable RAM, dual-boot, shared NTFS volume |
| Ubuntu 26.04 dev side | nvidia-driver-595-open installed but **not loaded** (Secure Boot on, module likely unsigned/MOK not enrolled); Python 3.14; no Qt Quick dev packages. Irrelevant now (Windows-only) |
| Windows side | Not yet inspected: Windows build, NVIDIA driver, VS/Qt toolchain unknown |

## 1. Requirements

| ID | Requirement | Where | Acceptance test | Status |
|---|---|---|---|---|
| R1 | Qt 6 C++/QML dark desktop window, CMake | `desktop/` | App builds via `build_windows.ps1`, opens dark dashboard | 🟡 |
| R2 | Manual launch only; no autostart | installer `[Icons]` has no Startup entry | After reboot Voxlate is not running | 🟡 |
| R3 | Mic prefilled from last session, must confirm every launch | `Main.qml` page `confirm`, QSettings `mic` | Relaunch → confirm page with previous mic selected; dashboard unreachable without Confirm | 🟡 |
| R4 | Physical mics only; virtual cables excluded (loop prevention) | `devices.list_devices` | CABLE devices absent from mic list | 🟡 |
| R5 | Source/target selectors + Swap (hi↔en), live switch | `Main.qml`, `Engine.set_languages` (epoch bump) | Swap during call → next phrase in the new direction, no old-direction audio afterwards | 🟡 |
| R6 | One-time voice setup 30–60 s, English + Roman Hindi script (no Devanagari in UI), consent, replay, re-record, delete | `profile.py SCRIPT`, `Main.qml enroll` | Record → quality shown → play → save; relaunch skips enrollment; delete removes `%LOCALAPPDATA%\Voxlate\profile` | 🟡 |
| R7 | Secure local profile | DPAPI CurrentUser encryption (`profile._dpapi`) | Copy `reference.wav.dpapi` to another Windows user → cannot decrypt | 🟡 |
| R8 | Audio-only UI (no transcript text) | `Main.qml` shows no text output | Visual check | 🟡 |
| R9 | Start/Stop toggle, Mute, status indicator (Ready/Starting/Translating/Stopped/Error) | `Main.qml`, header chip | Toggle works; states visible | 🟡 |
| R10 | Measured estimated delay (real timestamps) | `Engine._status_loop`: speech-onset capture time → first sample rendered to cable (+ device latency) | Delay shown after first phrase; p50/p95 | 🟡 |
| R11 | Modes: translated only (default) / original only / both | `OutputMixer` | T-leak test (below) + listen in Meet | 🟡 (unit test written) |
| R12 | X hides to tray, translation continues; tray Open/Stop-Resume/Exit | `main.cpp`, `onClosing` | Close window during call → remote still hears translation | 🟡 |
| R13 | Exit stops worker, clears buffers, releases devices | `Backend::shutdown` → `shutdown` cmd → `Engine.stop`; stdin EOF also stops | After Exit, `CABLE Output` level meter in Windows is flat; mic privacy icon disappears | 🟡 |
| R14 | Initial audio path check proves signal reaches virtual mic | `pathcheck.py` chirp + cross-correlation + idle-silence check | Pass on correct setup; fail when VB-CABLE removed or CABLE Input is default device | ✅ pass in the real app on VB-CABLE (27 Oct, after the COM fix); failure cases not yet tested |
| R15 | Fail closed, never leak original speech | `OutputMixer.failed/muted`, `Engine._fail`, worker death = streams closed | Kill `python.exe` mid-call → Meet hears silence | 🟡 |
| R16 | Pipeline: VAD → incremental ASR (hypothesis/stable commits) → clause-aware MT → voice-conditioned TTS → bounded output | `engine.py`, `core.py`, `models.py` | Bench `--stream` produces multiple segments per long utterance (not one batch) | 🟡 |
| R17 | Timestamps, segment IDs, bounded queues, cancellation epochs, backlog bound, device-loss watchdog | `core.py`, `engine.py` | Unit tests T1–T6 | 🟡 |
| R18 | Compare ≥2 model paths, record revision/rights/VRAM/RAM/quality/p50-p95 | `bench.py`, `fetch_models` manifest | `bench_results/RESULTS.md` has rows for kokoro_openvoice vs xtts and indictrans2 vs nllb | 🟡 |
| R19 | Google Meet acceptance test | Manual | Section 4 checklist | ⬜ |
| R20 | Reproducible EXE + installer + docs | `build_windows.ps1`, `installer/voxlate.iss`, README | Clean Windows VM: install → works | 🟡 |
| R21 | ₹0, no secrets, no paid APIs, non-commercial weights opt-in and labelled | `models.py` rights strings, THIRD_PARTY.md | grep: no API keys; XTTS needs typed AGREE | 🟡 |

## 2. Gates

| Gate | Deliverable | Status | Evidence / how to verify on Windows |
|---|---|---|---|
| a · Device/cable test | `pathcheck.py` + UI page | ✅ (passes in the app once Ready; a check run while models load can report `no_signal`) | Launch app → Run audio path check → expect ✔, score > 0.5, idle < −50 dBFS |
| b · Sample translation both directions | `bench.py` offline | 🟡 | `python -m voxlate_worker.bench --src hi --tgt en --synthetic` and reverse; listen to `bench_results\*.wav` |
| c · Enrollment + voice quality | `profile.py`, OpenVoice converter, XTTS comparison | 🟡 | Enroll in app; then bench with both `VOXLATE_TTS` values; owner + 1 listener rate similarity 1–5 |
| d · Streaming + latency | `Engine` + `bench --stream` | 🟡 | p50/p95 onset→ready in RESULTS.md; target 2–4 s (hypothesis, not promised) |
| e · Qt dashboard + worker lifecycle | `desktop/` | 🟡 | Build; run R3, R9, R12, R13 tests |
| f · Google Meet real call | — | ⬜ | Section 4 |
| g · EXE/installer + docs | `build_windows.ps1`, `.iss` | 🟡 | Build installer; install on second account/VM |

## 3. Automated tests (`worker/tests/test_core.py`; run: `.venv\Scripts\python -m unittest discover -s tests -v`)

| ID | Covers | Test | Status |
|---|---|---|---|
| T1 | Phrase commits | `test_local_agreement_*`, `test_hindi_waits_for_verb`, `test_hindi_negation_kept_with_verb`, `test_english_conjunction_split`, `test_max_wait_forces_flush`, `test_end_of_speech_flushes` | written, **not run** |
| T2 | Cancellation | `test_cancel_drops_queued_and_stale`, `test_epoch_cancels_inflight_unit` | written, not run |
| T3 | Buffer overflow | `test_backlog_bound`, `test_unit_queue_overflow_is_visible_skip` | written, not run |
| T4 | Mic unplug | `test_mic_unplug_watchdog_fails_closed` | written, not run |
| T5 | Stop/mute | `test_mute_silences_everything`, `test_stop_silences`, `test_failed_is_silent` | written, not run |
| T6 | No original leak in translated mode | `test_translated_mode_never_leaks_original` | written, not run |
| T7 | Path-check detector | `test_detects_delayed_chirp_in_noise`, `test_rejects_noise` | written, not run |
| T8 | End-to-end engine with fake models | `test_speech_to_segment` | written, not run |

## 4. Google Meet acceptance checklist (Gate f, manual, two devices)

1. Windows boot → start Voxlate from Start menu → confirm mic → (first run) path check ✔, enroll.
2. Hindi → English, Translated only, switch ON. Meet (Chrome) mic = `CABLE Output (VB-Audio Virtual Cable)`, headphones on.
3. Second device joins the call. Speak 10 Hindi test sentences (numbers, negation, question, a name). Remote notes: hears English? hears any raw Hindi? recognisable voice (1–5)? meaning correct?
4. Swap to English → Hindi mid-call; repeat 5 sentences.
5. Mute → remote hears silence within ~0.1 s; Unmute.
6. Original only / Both → as expected.
7. Close window (X) → translation continues; tray Stop → silence; tray Resume; tray Exit → silence, devices released.
8. Unplug USB mic (if available) mid-call → red error, remote hears silence.
9. Record the dashboard p50/p95 delay and Meet's own observed delay.

Record results in the table below.

| Date | Windows build | Chrome/Meet | Mic | Path | Direction | Raw-voice leak? | Voice similarity | Meaning ok (x/10) | Delay p50/p95 | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | not tested | — | — | — | — |

## 5. Decisions

| ID | Decision | Why |
|---|---|---|
| D1 | Audio I/O lives in the Python worker (PortAudio/WASAPI), not C++ | Removes a C++→Python PCM IPC hop and its latency/jitter; UI process stays simple. Qt app controls the worker over stdin/stdout JSON lines |
| D2 | IPC = JSON lines over stdin/stdout | Local only, no ports/firewall prompts; stdin EOF auto-stops the worker if the UI dies |
| D3 | Default MT = IndicTrans2 dist-200M (MIT), not Qwen 7B | Qwen 7B cannot fit next to ASR+TTS in 4 GB VRAM; IndicTrans2 is Hindi-specialised and small. NLLB-600M kept as a non-commercial comparison |
| D4 | Default voice = Kokoro (Hindi + English voices) → OpenVoice V2 converter; XTTS-v2 = opt-in comparison | Only commercially licensed cloning path available locally; XTTS is CPML non-commercial. Kokoro→OpenVoice Hindi quality is **unverified**: Gate c decides |
| D5 | Clause-aware scheduling: Hindi waits for auxiliary/future verb ending or punctuation; English splits before conjunctions; force flush after 4 s span | Avoids speaking verb-less Hindi prefixes and avoids whole-sentence batching |
| D6 | Fail closed by construction: original audio only enters the mixer in original/both modes; errors close streams | No-leak guarantee does not depend on error handling paths |
| D7 | VB-CABLE, user-installed, not bundled | Free, standard, but redistribution needs vendor license; no kernel driver in MVP |
| D8 | Per-user install with uv-managed Python 3.11 venv; models fetched at setup, not bundled | Avoids a 5 GB PyInstaller bundle; keeps weights separate from code for licensing |
| D9 | Profile encrypted with DPAPI (CurrentUser) | "Secure local profile" without managing keys |
| D10 | Whisper size: large-v3-turbo int8 on GPU, small on CPU | Hindi accuracy vs 4 GB VRAM; verify in Gate b/d bench |

## 6. Risks / blockers

| ID | Risk | Mitigation / next step |
|---|---|---|
| B1 | Nothing executed yet | Run section 3 tests and Gate a–d on Windows first |
| B2 | Kokoro→OpenVoice may sound poor or not like the owner in Hindi | Bench both TTS paths; if both fail, report honestly and demo best measured compromise |
| B3 | Package pins (IndicTransToolkit 1.0.3, kokoro 0.9.4, transformers 4.46.3, coqui-tts 0.24.3) may conflict on Windows | `setup_worker.ps1` fails loudly; adjust pins and commit `requirements.lock.txt` |
| B4 | IndicTrans2 HF repos might be gated | Free HF account + `huggingface-cli login` (only physical action needed) |
| B5 | 4 GB VRAM: ASR turbo + 2× IndicTrans2 + Kokoro + OpenVoice ≈ 2.5–3 GB estimated; XTTS adds ~2 GB | Bench reports peak VRAM; fall back to `VOXLATE_ASR=small` |
| B6 | Latency target 2–4 s unproven; Hindi verb-final waits add delay | Measure; tune `ASR_HOP_S`, VAD silence, `max_span` |
| B7 | Meet noise suppression may affect synthetic voice | Test with Meet noise cancellation on and off |
| B8 | Mic/cable clock drift in Both/Original modes (ring bounded at 250 ms → occasional drop) | Acceptable for demo; measure on a 30-min call |
| B9 | Ubuntu NVIDIA module not loaded (Secure Boot) | Not needed: Windows-only |

## 7. Session log

### 2026-10-17 · session 1 (Ubuntu, code only)
- Read README/WINDOWS_APP/PIPELINE/spec docx. Surveyed hardware/toolchain. Owner then instructed: Windows-only, don't run on Ubuntu. Removed the partial Ubuntu venv.
- Wrote: worker (core, engine, devices, pathcheck, profile, models, fetch_models, bench, IPC main, tests, setup script, pinned requirements), Qt app (CMake, main.cpp, Backend, Main.qml), installer, build script, README, THIRD_PARTY, this file.
- Commands run: survey only (`lspci`, `nvidia-smi`, `free`, package queries) plus a parse-only syntax check (`ast.parse`, Python 3.11 grammar) of the worker: passed. **No tests run, no measurements.**
- **Single most useful next action:** on Windows, `cd worker; setup_worker.ps1; .venv\Scripts\python -m unittest discover -s tests -v`, then `bench --src hi --tgt en --synthetic --stream` and paste the output here.

### 2026-10-27 · session 2 (Windows 11, RTX 2050, driver 617.14)
- Installer `dist\Voxlate-Setup-0.1.0.exe` had been built (20 Oct). On another account (`sbrse`) the engine setup failed with exit code 1; `vox\Voxlate` is a copy of that install. Its venv only has torch/torchaudio 2.5.1+cu124, so it stopped at (or before) the pinned-packages step. That machine's setup log has not been read.
- `setup_worker.ps1` here: stops at the gated-model check, **HTTP 401 on both IndicTrans2 repos, no HF token**. ⛔ Needs a Hugging Face account, terms accepted on both repos, Read token (owner action).
- Reproduced the remaining steps in a scratch venv (uv Python 3.11.11, **CPU** torch 2.5.1): lock-file install, requirements.txt, OpenVoice and the import check all **pass**. CUDA torch, model download and GPU check not yet run.
- Unit tests: 19/20 passed. `test_hindi_negation_kept_with_verb` failed: `core._norm` used `re` `\w`, which strips Devanagari vowel signs (कि/की/का/के → क), so `कि` never matched the conjunction set, and LocalAgreement could also commit a revised word. Fixed (`unicodedata` L/M/N categories). **20/20 pass.**
- `vox\Voxlate\worker\setup_worker.ps1` is older than `worker\setup_worker.ps1` (it doesn't write `last-error.txt` for the installer dialog). Rebuild the installer before redistributing.
- Installer repackaged with Inno Setup only (`dist\Voxlate\worker` refreshed from `worker\`; `Voxlate.exe` unchanged, since this PC has no Qt/MSVC). Added REBUILD.md; updated QUICK_INSTALL.md.
- With an HF token, **full `setup_worker.ps1` completed** on `vox\Voxlate\worker` (log `setup-20261027-155241.log`): Access OK on both repos, torch 2.5.1+cu124, `imports OK`, all 6 models downloaded with `manifest.json` written (IndicTrans2 ×2, whisper-small, whisper-large-v3-turbo, Kokoro-82M, OpenVoiceV2; about 6.2 GB), **`CUDA: True NVIDIA GeForce RTX 2050`**. Earlier attempts were interrupted (process killed; one brief pypi.org outage). Downloads resumed correctly, and the retry handled a dropped connection on OpenVoiceV2.
- Unit tests in the real CUDA venv: **20/20 OK**.
- Fresh install from `dist\Voxlate-Setup-0.1.0.exe` (16:28, token page left empty, all 6 models already complete): the installer-launched `setup_worker.ps1` reported **HTTP 401 on both IndicTrans2 repos**, although both `.voxlate_complete` markers existed (created 14:47 / 16:01). It should have skipped the gated check. **Unexplained:** the same installed script, run 2 min later via the Repair-setup command line, skipped the check correctly. `Test-ModelComplete` also returns True in fresh 64- and 32-bit powershell.exe. Inno log: per-user, non-admin, 64-bit mode. Open issue: re-test on the next fresh install with models present. Workaround: Repair setup.
- Repair setup from the installed app completed at 16:34 (fresh venv, models skipped, CUDA True). Voxlate.exe then showed `Translation engine stopped unexpectedly (code 103) ... No Python at '"...\uv\python\cpython-3.11.11...\python.exe'` on 3 starts (16:36–16:37), although that base Python existed and the venv python ran fine from a shell. From 16:39 the engine starts normally, both from a shell and via Explorer (Start-menu equivalent). Nothing was changed in between. Likely a transient first-use block (antivirus scanning the new Python?), unconfirmed. If it recurs: wait a minute and press Retry. Possible hardening: retry the worker start once on exit code 103.
- **Root cause of both "unexplained" issues above (16:44):** all setup runs today were launched from the Claude desktop app's shell, which is MSIX-packaged. Windows redirected their writes to %APPDATA%/%LOCALAPPDATA% (uv's Python 3.11.11, the 6.2 GB of models, the logs) into `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\...`, invisible to normally launched programs. So the real installer saw no models (it asked for a token), and the real Voxlate.exe's venv pointed at a base Python that doesn't exist for it (`No Python`, code 103). The worker.log read from Claude was the sandboxed one. Not a Voxlate bug. Fix: run setup from a normal PowerShell; models were copied to `E:\voxlate\voxlate-models` for `-ModelsSource`.
- ✅ **Owner ran `setup_worker.ps1 -ModelsSource E:\voxlate\voxlate-models` in their own PowerShell: setup completed, and Voxlate.exe (installed by the installer, started from the Start menu) reached Ready.** First real end-to-end engine start on Windows (R1 partly verified: opens, dark UI, engine + models load on the RTX 2050).
- First in-app audio path check (models still loading, header "Starting"): `device_busy`, `Unanticipated host error -9999 ... [Windows WDM-KS error 0]`. The "WDM-KS" part is a stale PortAudio host-error string from device enumeration; the code uses WASAPI only. Minutes later, from a shell: all WASAPI cable endpoints opened, and `pathcheck.run('CABLE Input…', 'CABLE Output…')` → **ok, score 1.0, delay 784 ms, silence −180 dBFS** (Gate a detector verified on real VB-CABLE). In-app Retry failed again. **Root cause:** WASAPI needs COM on the calling thread, and PortAudio initialises it only on the thread that imported sounddevice (the main thread). `cmd_path_check` and `cmd_start` open streams from worker threads, so they always failed with −9999. That means starting translation would have failed too. Reproduced: pathcheck in a thread = device_busy; with `CoInitializeEx` = ok. **Fixed:** `devices.com_init()` (called from `_devs()`, so before every stream open) and in `Engine.stop`. Verified: threaded pathcheck ok, score 1.0; unit tests 20/20. Installer repackaged. ✅ **Owner confirmed: after restart and Ready, the in-app audio path check passes.** Pattern across all in-app attempts: the check **fails while models load** (header "Starting": `device_busy` −9999, or the UI's 15 s "Engine not responding"), and **passes after Ready**. Saving a voice reloads the models, which caused the repeat. **Mitigated in the worker:** `cmd_path_check` now answers immediately with `reason: "loading"` and "wait until Ready" while `self.loading`. Repro: answered in 0.1 s. Still open: the QML button should be disabled until models are ready (needs a Qt rebuild). Why GPU loading makes WASAPI fail to open (rather than just glitch) isn't understood.
- Voice setup: after **Stop**, the page stayed on "● Recording 56 s". Cause: `profile.quality()` called `librosa.yin`, whose first call (librosa import + numba JIT) took **28.6 s** here, longer while models load. No progress event was sent, and an exception would have left the page stuck for good. **Fixed:** `median_f0` (only picks the low/high Kokoro base voice) now uses a numpy autocorrelation over loud frames (0.04 s; 120/220 Hz test tones exact). `enroll_stop` always ends in `review` or `error`, with a specific message for an all-silent recording. Repro via the worker protocol: error shown in 0.2 s. ✅ Owner confirmed in the app: after copying the fix, record → Stop → review page appears. Also seen: the Realtek Microphone Array returned exact digital silence (rms 0.000000) on main and worker threads, which suggests the mic is muted; the realme Buds headset gave signal.
- **Model load hung at "Loading translation (indictrans2)"** (after Save voice; also reproduced on a first load via the stdin protocol). GPU memory was fine (2.0/4.0 GB). A faulthandler stack dump showed the load thread stuck inside a native import (scipy.linalg → OpenBLAS/Fortran DLL), with the main thread in `for line in sys.stdin`. A synchronous pipe serialises I/O, so the DLL's stdin probe waited behind the pending ReadFile until the app sent another command. Timing-dependent, which is why the first in-app load happened to work. **Fixed:** the worker reads commands from a private `os.dup(0)` and points fd 0 / STD_INPUT_HANDLE at NUL. Repro: full load 32 s, voice-only reload 11 s, full reload 14 s (CPU). Enroll, path-check guard and unit tests re-verified.
- Save/delete voice now reloads **only the voice** (`Models.load_voice`, `voice_only`). A full reload drops the old bundle and calls `cuda.empty_cache()` before building the new one.
- In-app: switch ON → "Translation engine stopped unexpectedly (code 0)". The worker.log had no error or fatal-exception dump after the voice load. **Not reproduced** from a shell with the installed GPU venv: each stage alone (ASR "turbo", MT "मैं कल रिपोर्ट भेजूँगा।" → "I will send the report tomorrow.", TTS) OK; worker protocol load + start on real devices OK; **live test (Kokoro Hindi clip played into CABLE Input, engine listening on CABLE Output, GPU): 3 phrases translated, no crash, delay p50 9.7 s / p95 10.1 s.** Exit code 0 implies the stdin loop ended (EOF or shutdown), not a crash. Added `[cmd]`, `[models] ready` and `[worker] exiting: <why>` lines to worker.log. **In-app log: `[cmd] start` → `[worker] exiting: command pipe closed (EOF)`.** The fd-0 dup/NUL swap made the app's pipe read as EOF in the real app (not reproduced with an emulated Qt named pipe). **Replaced:** the stdin handling is back to plain `sys.stdin`. Instead, the worker imports the whole model stack on the main thread after `hello` and before the first read (torch first, for its CUDA DLL folder; then scipy.linalg/optimize/signal/sparse.linalg, faster_whisper, transformers, kokoro, misaki, librosa, openvoice, IndicTransToolkit). A second stack dump showed scipy.optimize's Fortran DLL also probing stdin, so preloading only scipy.linalg was not enough. Importing faster_whisper before `_torch()` killed the GPU load (ctranslate2 could not find cuDNN/cuBLAS). Verified: CPU reload sequence 36/17/27 s; GPU live test through an emulated Qt pipe (Hindi clip → translated, start/stop, no EOF); enroll, path guard, unit tests OK. Cost: the engine takes ~15–45 s after start before it handles commands.
- **Root cause of the in-app stop (found with a diagnostic tripwire build):** the EOF persisted with plain stdin. At the moment of "EOF": no code had touched fd 0 / sys.stdin / input() / subprocess during translation; `PeekNamedPipe` succeeded on the stdin handle (pipe alive, 0 bytes available); the app was alive; the ASR thread was inside faster-whisper `generate_with_fallback` on the GPU. So **a single 0-byte read on the live pipe** was treated as EOF by Python's line iterator. **Fixed:** `_commands()` reads fd 0 with `os.read` and treats an empty read as EOF only if `PeekNamedPipe` fails (writer gone). Otherwise it logs `empty read on a live command pipe (xN)` and keeps listening. Repro with a message-mode named pipe and a zero-length write: the previous worker quits (`BrokenPipeError` on the next command); the new one keeps answering and still exits cleanly on a real close. Diagnostic tripwire removed. Why the app's pipe yields 0-byte reads is not known. ✅ **Owner confirmed (27 Oct): with this fix the app keeps translating Hindi → English continuously.** First sustained end-to-end run in the real app (mic → VAD → ASR → MT → cloned voice → VB-CABLE). Open: latency ~10–13 s (target 2–4 s), translation and voice quality not yet rated, Google Meet test (Gate f) not done.
- **Latency far above target:** bench `--synthetic --stream` on the GPU gave onset→ready p50 16 s / p95 29 s; live test 9.7 s. Target 2–4 s. Next: profile where the time goes (ASR hop, Hindi verb-final waits, VAD silence, synth queue).
- bench.py: results JSON/MD now written as UTF-8 (cp1252 crash on Devanagari).
- Minor: when the app is killed, the worker's final `emit("bye")` raises `OSError: [Errno 22]` on the closed stdout pipe (harmless traceback in worker.log).
- VB-CABLE has since been installed (CABLE Input/Output visible to the worker).
- Not yet done (earlier note): VB-CABLE was **not installed** on this PC. Voxlate.exe has not been launched. No bench / latency / Meet test.
