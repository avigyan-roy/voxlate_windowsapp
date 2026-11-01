# Voxlate · Windows investor-demo app

Live **outgoing** Hindi ↔ English speech translation in your own (enrolled) voice, sent to a virtual microphone that Google Meet (or any app that lets you pick a microphone) can use. Everything runs **locally** on the laptop: no paid APIs, no cloud, ₹0 software cost.

> Status: code complete for all gates; **nothing has been run on Windows yet**. See [TASKS.md](TASKS.md) for what is verified (nothing yet), what needs Windows verification, and the test steps.

```
Physical mic ──► Voxlate worker (Python, local)                                   ┌───────────────┐
                 VAD → streaming ASR → stable commits → clause-aware MT → voice ─► CABLE Input    │ VB-CABLE
                                                                                  │ CABLE Output ─┼──► Google Meet mic
Voxlate.exe (Qt 6 / QML dark UI + tray) ◄── JSON lines over stdin/stdout ──►      └───────────────┘
```

| Folder | What |
|---|---|
| `desktop/` | C++20 + Qt 6 Quick (QML) app: UI, tray, settings, worker lifecycle |
| `worker/` | Python 3.11 worker: audio I/O (WASAPI), pipeline, models, enrollment, path check, bench, tests |
| `installer/` | Inno Setup script (per-user, no admin) |
| `build_windows.ps1` | Build + package everything into `dist\` |

Supported: **Windows 11 x64** (Windows 10 22H2 expected to work, untested). Developed on Ubuntu 26.04 but **built and run only on Windows** (an Ubuntu ELF is not a Windows EXE). Target hardware: NVIDIA RTX 2050 4 GB, 12 GB RAM.

---

**Full step-by-step installation, including the AI models: [INSTALL.md](INSTALL.md).**

## 1. One-time machine setup (Windows)

1. **NVIDIA driver** (Game Ready/Studio, any 2024+ version). CUDA toolkit is *not* needed; PyTorch brings its own runtime.
2. **VB-CABLE** (free, donationware; not bundled because redistribution needs a vendor license): download from <https://vb-audio.com/Cable/>, unzip, right-click `VBCABLE_Setup_x64.exe` → *Run as administrator* → Install → **reboot**.
   - It creates **Playback: `CABLE Input (VB-Audio Virtual Cable)`** (Voxlate writes here) and **Recording: `CABLE Output (VB-Audio Virtual Cable)`** (Meet listens here).
   - In *Sound settings*, make sure **CABLE Input is NOT your default playback device** (otherwise Windows sounds go into the meeting). The path check detects this.
   - On *CABLE Output → Properties → Listen*, leave **“Listen to this device” OFF**.
3. Install **Voxlate-Setup-0.1.0.exe** (from `dist\`, see §3). It installs per-user, then runs the engine setup, which downloads Python 3.11 and the packages (~3 GB) plus the models (~3 GB). Tick *“No NVIDIA GPU”* only on machines without one.

## 2. Using it (acceptance demo flow)

1. Start **Voxlate** from the Start menu (it never auto-starts).
2. **Confirm microphone**: your last mic is preselected; press *Confirm microphone* (required on every launch).
3. First run only: **Audio path check** (inaudible test sweep through the cable; must pass), then **voice setup**: tick consent, *Record*, read the English + Roman-Hindi script (~45–60 s), *Stop*, *Play back*, *Save voice*.
4. Dashboard: choose **Hindi → English** (⇄ swaps), **Translated only**, flip the **switch ON**.
5. **Google Meet**: ⋮ → *Settings* → *Audio* → **Microphone: `CABLE Output (VB-Audio Virtual Cable)`**. Speaker: your headphones (headphones strongly recommended).
6. Speak. The dashboard shows mic/output levels and the **measured** delay (median and p95, from real timestamps).
7. **X** hides the window to the tray and translation keeps running. Tray right-click: *Open*, *Stop/Resume translation*, *Exit*. **Exit** stops translation, releases the devices and ends the engine.

Modes: **Translated only** (default; your raw voice can never reach the cable), **Original only** (passthrough, no translation), **Both** (overlaps). **Mute** silences the cable immediately and discards queued speech. On any engine/device error the cable goes **silent** (fail-closed) and the status turns red.

## 3. Building from source (Windows)

Prerequisites (all free): Visual Studio 2022 Build Tools (*Desktop development with C++*, which includes CMake and Ninja), **Qt 6.8 LTS** *MSVC 2022 64-bit* via the Qt Online Installer (open-source/LGPL), **Inno Setup 6**, Git (optional).

From **“x64 Native Tools Command Prompt for VS 2022”**:

```powershell
cd "D:\voxlate\windows app"          # wherever this folder is on the shared NTFS volume
powershell -ExecutionPolicy Bypass -File build_windows.ps1 -QtDir C:\Qt\6.8.3\msvc2022_64
# -> dist\Voxlate\ (portable app)  and  dist\Voxlate-Setup-0.1.0.exe (installer)
```

### Developer loop without the installer

```powershell
winget install astral-sh.uv
cd worker
powershell -ExecutionPolicy Bypass -File setup_worker.ps1          # add -Cpu / -Nllb / -Xtts as needed
.venv\Scripts\python -m unittest discover -s tests -v               # pipeline logic tests (no devices/models)
cd ..
cmake -S desktop -B build -G Ninja -DCMAKE_BUILD_TYPE=Debug -DCMAKE_PREFIX_PATH=C:\Qt\6.8.3\msvc2022_64
cmake --build build
$env:VOXLATE_WORKER_DIR = "$PWD\worker"; & "C:\Qt\6.8.3\msvc2022_64\bin\windeployqt.exe" --qmldir desktop\qml build\Voxlate.exe; .\build\Voxlate.exe
```

## 4. Models, rights and benchmarks

Default (commercially clean licenses): **Silero VAD** (MIT) → **faster-whisper large-v3-turbo** int8 on GPU / small on CPU (MIT) → **IndicTrans2 distilled 200M** (MIT) → **Kokoro-82M** (Apache-2.0) + **OpenVoice V2** tone converter (MIT) for your voice.
Comparison paths (**non-commercial only**, opt-in): NLLB-200 600M (`VOXLATE_MT=nllb`, CC-BY-NC-4.0), XTTS-v2 (`VOXLATE_TTS=xtts`, Coqui CPML). Details: [THIRD_PARTY.md](THIRD_PARTY.md).

Benchmarks (writes `worker\bench_results\RESULTS.md` + JSON + WAVs to listen to):

```powershell
cd worker
.venv\Scripts\python -m voxlate_worker.bench --src hi --tgt en --synthetic --stream
.venv\Scripts\python -m voxlate_worker.bench --src en --tgt hi --synthetic --stream
.venv\Scripts\python -m voxlate_worker.bench --src hi --tgt en --wav ..\clips\hi_01.wav --stream   # your real recordings
$env:VOXLATE_TTS="xtts"; .venv\Scripts\python -m voxlate_worker.bench --src hi --tgt en --synthetic --stream
```

Selectors: `VOXLATE_ASR` (`large-v3-turbo`|`small`), `VOXLATE_MT` (`indictrans2`|`nllb`), `VOXLATE_TTS` (`kokoro_openvoice`|`xtts`), `VOXLATE_DEVICE` (`cuda`|`cpu`). Set them as user environment variables to change what the app uses.

## 5. Data and privacy

- Voice profile: `%LOCALAPPDATA%\Voxlate\profile\` with the reference recording **encrypted with Windows DPAPI** (only your Windows account can decrypt it). Delete it from the dashboard or by removing the folder.
- Models: `%LOCALAPPDATA%\Voxlate\models\` (+ `manifest.json` with exact revisions).
- Logs: `%LOCALAPPDATA%\Voxlate\Voxlate\worker.log`: errors and timings only, **no transcripts or audio**.
- No network use while running (models load offline). Setup downloads from huggingface.co, pytorch.org, pypi.org, github.com.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| “VB-CABLE not found” | Install it as admin and **reboot**. Other cable product? Set `VOXLATE_CABLE_PLAYBACK` / `VOXLATE_CABLE_RECORDING` to name substrings. |
| Path check: “Other audio is reaching the virtual microphone” | CABLE Input is the Windows default playback device, or another app is playing into it. |
| “Translation engine not installed” | Start menu → *Voxlate engine setup (re-run)*. |
| Model download fails with 401/403 | That repo is gated: accept its terms on huggingface.co, run `worker\.venv\Scripts\huggingface-cli login`, re-run setup. |
| Meet hears nothing | Meet mic must be **CABLE Output**; Voxlate switch ON; not muted; mode not set to an empty path. |
| After Exit, Meet is silent | Expected: switch Meet's microphone back to your real mic. |
