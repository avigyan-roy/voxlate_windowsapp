# Voxlate · Windows installation guide (app + AI models)

This guide takes a Windows laptop from nothing to a working Voxlate demo: drivers, virtual microphone, the app, the local AI models, and the checks that prove each step worked.

> Everything runs **locally**. No paid accounts, no API keys, no cloud. The only accounts you might need are free ones (Qt, and possibly Hugging Face; see step 5.4).

| | Requirement |
|---|---|
| OS | Windows 11 x64 (Windows 10 22H2 should work but is untested) |
| GPU | NVIDIA with ≥ 4 GB VRAM recommended (tested target: RTX 2050 4 GB). CPU-only works but is much slower |
| RAM | 12 GB |
| Disk | **≥ 15 GB free** on the drive holding `%LOCALAPPDATA%` (engine ~4 GB + models ~4–9 GB) |
| Internet | Needed **only during installation** (several GB of downloads). Not needed while translating |
| Time | ~30–60 min, mostly downloads |

There are two ways to install:

- **Path A: installer** (`Voxlate-Setup-0.1.0.exe`). Use this for the demo laptop once someone has built the installer. Do steps 1–3, then **A**, then 6–7.
- **Path B: from source.** Use this for development or to build the installer yourself. Do steps 1–3, then **B**, then 5–7.

---

## 1. NVIDIA driver

1. Install the latest **NVIDIA Game Ready or Studio driver** for your GPU from <https://www.nvidia.com/Download/index.aspx> (or through the NVIDIA App).
2. Reboot.
3. Check it: open **PowerShell** and run
   ```powershell
   nvidia-smi
   ```
   You should see your GPU name and a "CUDA Version" of **12.4 or higher**.

You do **not** need to install the CUDA Toolkit or cuDNN. PyTorch brings its own copy.

## 2. Virtual microphone (VB-CABLE)

Voxlate sends translated audio into a virtual cable, and Google Meet uses the other end of it as its microphone.

1. Download **VB-CABLE Driver Pack** from <https://vb-audio.com/Cable/> (free, donationware).
2. Unzip it. Right-click **`VBCABLE_Setup_x64.exe`**, choose **Run as administrator**, then **Install Driver**.
3. **Reboot** (required).
4. Open *Settings → System → Sound → More sound settings* and check that these two devices exist:
   - **Playback** tab: `CABLE Input (VB-Audio Virtual Cable)`. Voxlate writes here.
   - **Recording** tab: `CABLE Output (VB-Audio Virtual Cable)`. Google Meet listens here.
5. Two settings to get right:
   - On the **Playback** tab, your **real speakers/headphones must stay the Default Device**, *not* CABLE Input. Otherwise Windows sounds would go into your meeting.
   - On the **Recording** tab: *CABLE Output → Properties → Listen*: **“Listen to this device” must be OFF**.

## 3. Microphone privacy permission

*Settings → Privacy & security → Microphone*: turn on **Microphone access** and **Let desktop apps access your microphone**.

---

## A. Install with the installer (demo laptop)

1. Run **`Voxlate-Setup-0.1.0.exe`**. No administrator rights are needed; it installs to `%LOCALAPPDATA%\Programs\Voxlate`.
2. On the *Select Additional Tasks* page, tick **“No NVIDIA GPU”** only if the machine has no NVIDIA GPU.
3. When it finishes copying, a **PowerShell window opens and installs the translation engine and AI models**. This is the long step (several GB). Leave it open until it prints:
   ```
   Worker setup complete.
   ```
   and shows `CUDA: True NVIDIA GeForce RTX 2050` (or your GPU). If it shows `CUDA: False` on an NVIDIA laptop, go back to step 1.
4. If it stops with an error, read step 5.4 and section 8. To re-run it later, use *Start menu → Voxlate → **Voxlate engine setup (re-run)***.

Then go to **step 6**.

---

## B. Install from source (developer / building the installer)

### B.1 Tools (all free)

| Tool | Where | Notes |
|---|---|---|
| **Visual Studio 2022 Build Tools** | <https://visualstudio.microsoft.com/downloads/> → *Build Tools for Visual Studio 2022* | Select the workload **Desktop development with C++**, which includes MSVC, the Windows SDK, CMake and Ninja |
| **Qt 6.8 LTS** | <https://www.qt.io/download-qt-installer-oss> (free Qt account) | In the installer pick **Qt 6.8.x → MSVC 2022 64-bit**. Default path: `C:\Qt\6.8.3\msvc2022_64` |
| **uv** | `winget install astral-sh.uv` | Installs Python 3.11 and the Python packages |
| **Inno Setup 6** | <https://jrsoftware.org/isdl.php> | Only needed to build the installer `.exe` |
| Git | `winget install Git.Git` | Optional |

### B.2 Get the code

On the dual-boot laptop the project already sits on the shared NTFS drive. Find it in Explorer (for example `D:\voxlate\windows app`). Otherwise copy the `windows app` folder anywhere.

### B.3 Install the translation engine + AI models

```powershell
cd "D:\voxlate\windows app\worker"
powershell -ExecutionPolicy Bypass -File setup_worker.ps1
```

Options:

| Flag | Effect |
|---|---|
| *(none)* | NVIDIA GPU (CUDA 12.4 build of PyTorch) + default models |
| `-Cpu` | No NVIDIA GPU |
| `-Nllb` | Also download the NLLB-200 comparison translator (non-commercial license) |
| `-Xtts` | Also install XTTS-v2 comparison voice cloner (non-commercial license; you must type `AGREE`) |

This step:
1. creates `worker\.venv` with **Python 3.11.9**,
2. installs **PyTorch 2.5.1** and the pinned packages from `requirements.txt`,
3. installs the OpenVoice converter code,
4. writes every resolved version to `worker\requirements.lock.txt`,
5. downloads the AI models (section 5) and records their exact revisions,
6. prints whether CUDA works.

### B.4 Run the logic tests (no mic or models needed)

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```
All tests should report `ok`.

### B.5 Build the app and installer

Open **“x64 Native Tools Command Prompt for VS 2022”** from the Start menu, then:

```powershell
cd "D:\voxlate\windows app"
powershell -ExecutionPolicy Bypass -File build_windows.ps1 -QtDir C:\Qt\6.8.3\msvc2022_64
```

Output:
- `dist\Voxlate\Voxlate.exe`: the portable app. It looks for the engine in `dist\Voxlate\worker\.venv`, which doesn't exist yet. Either run `dist\Voxlate\worker\setup_worker.ps1`, or point it at your dev engine:
  ```powershell
  $env:VOXLATE_WORKER_DIR = "D:\voxlate\windows app\worker"
  .\dist\Voxlate\Voxlate.exe
  ```
- `dist\Voxlate-Setup-0.1.0.exe`: the installer for Path A.

---

## 5. The AI models

### 5.1 What gets installed

All models run **on your laptop**. They are downloaded once and then loaded **offline**. While translating, Voxlate never contacts the internet.

| Stage | Model (Hugging Face repo) | Approx. download | License | Commercial use | Installed by default |
|---|---|---|---|---|---|
| Speech detection | Silero VAD 5.1 (inside the `silero-vad` pip package) | ~2 MB | MIT | ✅ | ✅ |
| Speech recognition (GPU) | `dropbox-dash/faster-whisper-large-v3-turbo` | ~1.6 GB | MIT | ✅ | ✅ |
| Speech recognition (CPU / low-VRAM fallback) | `Systran/faster-whisper-small` | ~0.5 GB | MIT | ✅ | ✅ |
| Translation Hindi → English | `ai4bharat/indictrans2-indic-en-dist-200M` | ~0.9 GB | MIT | ✅ | ✅ |
| Translation English → Hindi | `ai4bharat/indictrans2-en-indic-dist-200M` | ~0.9 GB | MIT | ✅ | ✅ |
| Base speech (Hindi + English voices) | `hexgrad/Kokoro-82M` | ~0.35 GB | Apache-2.0 | ✅ | ✅ |
| Your-voice conversion | `myshell-ai/OpenVoiceV2` (converter only) | ~0.13 GB | MIT | ✅ | ✅ |
| *Comparison:* translation | `facebook/nllb-200-distilled-600M` | ~2.5 GB | CC-BY-NC-4.0 | ❌ non-commercial | only with `-Nllb` |
| *Comparison:* voice cloning | Coqui XTTS-v2 | ~1.9 GB | Coqui Public Model License | ❌ non-commercial (outputs too) | only with `-Xtts` |

Sizes are approximate and change with upstream revisions. The default set totals about **4.5 GB**.

### 5.2 Where they are stored

```
%LOCALAPPDATA%\Voxlate\models\hf\            ← Hugging Face cache (all HF models above)
%LOCALAPPDATA%\Voxlate\models\manifest.json  ← exact revision + license of each downloaded model
%LOCALAPPDATA%\tts\                          ← XTTS-v2 only (Coqui's own cache)
```

Models are kept **separate from the app** and are never inside the installer. Uninstalling Voxlate leaves them in place; delete the folders above to reclaim the space.

### 5.3 Download or re-download the models manually

The setup script does this for you. To (re)run only the model step:

```powershell
cd "<install or source folder>\worker"
.venv\Scripts\python -m voxlate_worker.fetch_models              # default set
.venv\Scripts\python -m voxlate_worker.fetch_models --nllb       # + NLLB comparison
.venv\Scripts\python -m voxlate_worker.fetch_models --xtts       # + XTTS comparison (type AGREE)
```

It is safe to re-run: files already downloaded are skipped. It ends with `OK. Manifest: ...\manifest.json`.

To download a single model with the Hugging Face CLI, first point it at Voxlate's cache:

```powershell
$env:HF_HOME = "$env:LOCALAPPDATA\Voxlate\models\hf"
.venv\Scripts\huggingface-cli download hexgrad/Kokoro-82M
```

### 5.4 If a download fails with 401 / 403 (gated model)

Some Hugging Face repos (possibly the AI4Bharat IndicTrans2 ones) require you to accept their terms with a free account:

1. Create a free account at <https://huggingface.co/join>.
2. Open the model page (for example <https://huggingface.co/ai4bharat/indictrans2-indic-en-dist-200M>), click **Agree and access repository**, and do the same for the other repo named in the error.
3. Create a **Read** token: *Settings → Access Tokens*.
4. Log in once on this PC (the token is stored in your user profile, never in Voxlate's code):
   ```powershell
   $env:HF_HOME = "$env:LOCALAPPDATA\Voxlate\models\hf"
   .venv\Scripts\huggingface-cli login
   ```
5. Re-run `fetch_models` (5.3).

### 5.5 Check that the models load

```powershell
cd "<install or source folder>\worker"
$env:HF_HUB_OFFLINE = "1"
.venv\Scripts\python -c "from voxlate_worker.models import Models; m = Models(log=print); print(m.info)"
```

Expected: a few `Loading …` lines, then a dictionary with `'device': 'cuda'`, the model names, their licenses and `peak_vram_mb`. Before voice setup it says `'voice': 'generic (debug fallback, NOT your voice)'`; after enrollment it says `'cloned'`.

If you see `out of memory` on a 4 GB GPU, use the smaller recognizer (step 5.6).

### 5.6 Choosing models (optional)

Voxlate reads these **user environment variables**. Set them with *Start → “Edit environment variables for your account”*, then restart Voxlate.

| Variable | Values | Default |
|---|---|---|
| `VOXLATE_ASR` | `large-v3-turbo`, `small` | `large-v3-turbo` on GPU, `small` on CPU |
| `VOXLATE_MT` | `indictrans2`, `nllb` | `indictrans2` |
| `VOXLATE_TTS` | `kokoro_openvoice`, `xtts` | `kokoro_openvoice` |
| `VOXLATE_DEVICE` | `cuda`, `cpu` | `cuda` if available |

Rough VRAM budget on 4 GB (to be confirmed by the benchmark): turbo ASR + both IndicTrans2 + Kokoro + OpenVoice ≈ 2.5–3 GB. XTTS adds ≈ 2 GB, so pair it with `VOXLATE_ASR=small`.

### 5.7 Benchmark the models (recommended before the demo)

```powershell
cd "<install or source folder>\worker"
.venv\Scripts\python -m voxlate_worker.bench --src hi --tgt en --synthetic --stream
.venv\Scripts\python -m voxlate_worker.bench --src en --tgt hi --synthetic --stream
```

Results go to `worker\bench_results\`: a summary table in `RESULTS.md` (timings, latency median and p95, peak VRAM/RAM), full details in JSON, and WAV files to listen to. To compare paths, set `VOXLATE_TTS=xtts` or `VOXLATE_MT=nllb` in the same window and run again. Use your own recordings with `--wav path\to\clip.wav`.

### 5.8 Copying models to another PC (no internet there)

Install Voxlate on the second PC, then copy the whole folder `%LOCALAPPDATA%\Voxlate\models\` from the first PC to the same location on the second. The app loads models offline, so nothing else is needed. (The engine packages in `worker\.venv` still need one online install.)

---

## 6. First launch

1. Start **Voxlate** from the Start menu. It never starts automatically with Windows.
2. **Confirm microphone**: choose your real mic and press *Confirm microphone*. You'll do this on every launch.
3. **Audio path check** (first run): press *Run audio path check*. You won't hear anything. Expect **✔ Signal reached the virtual microphone**.
4. **Voice setup** (first run, about 1 minute):
   1. tick the consent box,
   2. press **Record** and read the whole script aloud in your normal voice,
   3. press **Stop** and wait for the quality check,
   4. **Play back** to listen, **Re-record** if needed, then **Save voice**.

   The engine then reloads to prepare your voice. The dashboard shows *Speaking with: cloned*.

   Your recording is stored encrypted for your Windows account in `%LOCALAPPDATA%\Voxlate\profile\`.

## 7. Google Meet setup and test

1. In Voxlate choose **Hindi → English**, **Translated only**, and turn the **switch ON**. The status turns green: *Translating*.
2. In Google Meet (Chrome): **⋮ → Settings → Audio**
   - **Microphone:** `CABLE Output (VB-Audio Virtual Cable)`
   - **Speakers:** your headphones (strongly recommended so the call audio can't reach your mic)
3. Join a call from a second device and speak Hindi. The other side should hear English in your voice, and **never** your raw Hindi.
4. The dashboard shows the **measured delay** after the first phrase.
5. Closing the window (X) keeps translating in the tray. Use the tray icon for **Open / Stop translation / Exit**.
6. After the demo, switch Meet's microphone back to your real mic.

The full acceptance checklist is in [TASKS.md §4](TASKS.md).

---

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `setup_worker.ps1` cannot be run (“running scripts is disabled”) | Use the exact command shown, which includes `-ExecutionPolicy Bypass` |
| `uv.exe not found` | `winget install astral-sh.uv`, then open a new PowerShell |
| `CUDA: False` on an NVIDIA laptop | Update the NVIDIA driver (step 1), reboot, re-run setup. In Windows *Graphics settings* you can also set `python.exe` to *High performance* |
| Package install fails (version conflict) | Send the error output to the developer; the pins in `requirements.txt` are adjusted and `requirements.lock.txt` is committed after the first good install |
| Model download 401/403 | Step 5.4 |
| Model download interrupted | Re-run `fetch_models` (5.3); it resumes |
| `out of memory` / CUDA OOM | `VOXLATE_ASR=small` (5.6); close games or browsers using the GPU |
| App says “Translation engine not installed” | Run *Voxlate engine setup (re-run)* from the Start menu |
| “VB-CABLE not found” | Install as administrator and **reboot** (step 2) |
| Path check: “Other audio is reaching the virtual microphone” | CABLE Input is set as the default playback device, or another app plays into it (step 2.5) |
| Meet hears nothing | Meet mic = **CABLE Output**; Voxlate switch ON; not muted |
| Voice doesn't sound like you | Re-record in a quiet room. Also try `VOXLATE_TTS=xtts` for comparison (non-commercial only) |
| Anything else | Read `%LOCALAPPDATA%\Voxlate\Voxlate\worker.log` (errors and timings only; no transcripts or audio) |

## 9. Uninstall

1. *Settings → Apps → Voxlate → Uninstall*. This removes the app and its engine `.venv`.
2. To also remove models and your voice profile, delete `%LOCALAPPDATA%\Voxlate\` (and `%LOCALAPPDATA%\tts\` if you installed XTTS).
3. VB-CABLE: run `VBCABLE_Setup_x64.exe` as administrator, choose **Remove Driver**, then reboot.
