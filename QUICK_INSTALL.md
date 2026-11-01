# Voxlate · Quick install (Windows)

This is the short version. More background is in [INSTALL.md](INSTALL.md).

**Before you start**
- **Already have `dist\Voxlate-Setup-0.1.0.exe`?** Do Part 1, skip Part 2, go to Part 3. A fresh build of it is in `dist\`.
- To make the installer yourself, see Part 2. Building only works on Windows.
- **Always install with the installer.** Don't copy an installed `Voxlate` folder to another PC: its Python environment points at the old PC's user folder and won't start.
- Paths below assume the project is at `E:\voxlate\windows app`. If yours is somewhere else, use your path. The space in the path is fine.
- Plan on about 15 GB of free disk space and internet access during setup.
- **Windows Developer Mode is NOT needed.** Models are downloaded as plain files (no symlinks).

---

## Part 1: Prepare each PC (once)

### Step 1: NVIDIA driver (skip if the PC has no NVIDIA GPU)
1. Install the latest driver from <https://www.nvidia.com/Download/index.aspx>.
2. Reboot.
3. In **PowerShell**, run `nvidia-smi`. It should show your GPU and "CUDA Version 12.4" or higher.

### Step 2: Virtual microphone (VB-Audio Virtual Cable)
1. Download the **VB-CABLE Driver Pack** from <https://vb-audio.com/Cable/> and unzip it.
2. Right-click `VBCABLE_Setup_x64.exe`, choose **Run as administrator**, then click **Install Driver**.
3. **Reboot.**
4. Open *Settings > System > Sound > More sound settings* and check:
   - **Playback** tab: `CABLE Input` is listed, and your speakers or headphones are still the **Default Device**.
   - **Recording** tab: `CABLE Output` is listed. Under *Properties > Listen*, make sure **"Listen to this device"** is OFF.

### Step 3: Microphone permission
*Settings > Privacy & security > Microphone*: turn on **Microphone access** and **Let desktop apps access your microphone**.
If this is off, Windows hands Voxlate only silence (and VB-CABLE's recording side too). Voxlate detects this and shows the fix.

### Step 4: Hugging Face account and token (free, once per person)
The IndicTrans2 translation models are free but "gated": you must accept their terms once.
1. Create an account: <https://huggingface.co/join>
2. While logged in, open **both** pages and click **Agree and access repository**:
   - <https://huggingface.co/ai4bharat/indictrans2-indic-en-dist-200M>
   - <https://huggingface.co/ai4bharat/indictrans2-en-indic-dist-200M>
3. Create a token with the **Read** role: <https://huggingface.co/settings/tokens>. Copy it (it starts with `hf_`).

You paste the token into the installer (Step 7). It is passed to setup only through an environment variable. It is never written to the log, the project or the command line, and it is not saved.

Setup finds a token in any of these places, in this order:
1. The installer's token page (or the hidden prompt in Repair setup).
2. An `HF_TOKEN` **user environment variable**. Set it in *Start > "Edit environment variables for your account" > New*, Name `HF_TOKEN`, Value your token. Then **open a new window**: windows that were already open don't see it.
3. A token saved earlier with `huggingface-cli login`.

Treat the token like a password. Don't paste it into chats, emails or screenshots. If it was exposed, delete it at <https://huggingface.co/settings/tokens> and create a new one. Once the models are downloaded, setup doesn't need the token any more.

---

## Part 2: Build the installer (once, on a Windows build PC)

Skip this part if someone already gave you `Voxlate-Setup-0.1.0.exe`.
Setting up a new build PC from scratch? [REBUILD.md](REBUILD.md) has the exact install commands for every tool.

### Step 5: Install the build tools
| Tool | Download | What to pick |
|---|---|---|
| Visual Studio 2022 Build Tools | <https://visualstudio.microsoft.com/downloads/> | Workload **Desktop development with C++** (includes the x64 compiler, CMake and Ninja) |
| Qt 6.5 or newer | <https://www.qt.io/download-qt-installer-oss> | Any Qt >= 6.5 with the **MSVC 2022 64-bit** kit, e.g. `C:\Qt\6.12.0\msvc2022_64`. MinGW and ARM64 kits do not work. |
| Inno Setup 6 | <https://jrsoftware.org/isdl.php> | Default options |
| uv | In PowerShell: `winget install astral-sh.uv` | Only used if downloading the pinned uv fails |

### Step 6: Build
Open a **normal PowerShell window**. You don't need the Developer Command Prompt; the script sets up the 64-bit compiler itself. Then run:
```
cd "E:\voxlate\windows app"
powershell -NoProfile -ExecutionPolicy Bypass -File build_windows.ps1
```
- The script finds the newest Qt MSVC 64-bit kit by itself. To pick one: `-QtDir C:\Qt\6.12.0\msvc2022_64`.
- Add `-Clean` to rebuild from scratch.
- The first build also compiles the IndicTransToolkit wheel into `wheels\`, so the demo PC never compiles anything.

Result:

| File | Location |
|---|---|
| **Installer** | `E:\voxlate\windows app\dist\Voxlate-Setup-0.1.0.exe` |
| Staged app (what the installer contains) | `E:\voxlate\windows app\dist\Voxlate\` |

Copy `Voxlate-Setup-0.1.0.exe` to a USB stick or to the demo PC.

### Repackage only (no Qt or compiler needed)
If you changed only the Python worker (`worker\`) or the docs, not `desktop\`, you don't need to recompile `Voxlate.exe`. With an earlier full build in `dist\Voxlate\` and only Inno Setup installed:
```
cd "E:\voxlate\windows app"
robocopy worker dist\Voxlate\worker /MIR /XD .venv __pycache__ bench_results
copy README.md, INSTALL.md, QUICK_INSTALL.md, THIRD_PARTY.md dist\Voxlate
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\voxlate.iss
```
It ends with `Successful compile` and writes a new `dist\Voxlate-Setup-0.1.0.exe`. Any change in `desktop\` needs the full build (Step 6).

---

## Part 3: Install Voxlate

The demo PC needs no Python, Qt, Visual Studio or Developer Mode. The installer brings everything, including the Microsoft Visual C++ runtime. Windows may ask for permission once to install that runtime.

### Step 7: Run the installer
1. Double-click `Voxlate-Setup-0.1.0.exe`. You don't need administrator rights.
2. Tick **"No NVIDIA GPU"** only if the PC has no NVIDIA graphics card. Setup also switches to CPU automatically if it finds none.
3. On the **Hugging Face token** page, paste your Read token from Step 4.
4. After the files are copied, a **PowerShell window** opens. It installs Python 3.11 and the engine, then downloads the AI models (several GB, 30-60 min). **Leave it open** until it shows:
   ```
   CUDA: True NVIDIA GeForce RTX ...
   Worker setup complete.
   ```
   Without a valid token it stops within seconds, before any large download, and lists what to do.
5. If anything fails, the installer's error box shows the reason (the last lines of the setup log). Fix the cause, then run **Start menu > Voxlate > Voxlate - Repair setup**. You never need to reinstall. If you need help, send the newest `setup-*.log` from `%LOCALAPPDATA%\Voxlate\logs\` (it never contains your token).

### Upgrading a PC that already had Voxlate (e.g. the laptop)
Just run the new installer over the old one; no uninstall needed.
- This release fixes Hindi clause splitting: words like `कि` / `की` / `का` were treated as the same word, so Hindi phrases were cut in the wrong places.
- The existing Python environment is reused. If it's broken (for example, the folder was copied from another PC), setup deletes it and creates a new one. The missing spaCy language model (the cause of the stuck **Starting**) is added.
- Models now live in one plain folder per model, so they download once more (about 4 GB). Afterwards you can delete the old cache `%LOCALAPPDATA%\Voxlate\models\hf\hub` to free that space.
- A token saved earlier with `huggingface-cli login` is picked up automatically.

### Repair setup (Start menu > Voxlate > Voxlate - Repair setup)
- Reruns engine setup. It reuses the installed Python environment, skips finished models and resumes partial downloads.
- If the translation models still need downloading and no token is set, it asks for the token (the input is hidden).

### Offline install (optional, for demos)
On a PC where setup already worked:
```
powershell -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\Programs\Voxlate\worker\export_models.ps1" -Destination "F:\voxlate-models"
```
On the demo PC, after installing:
```
powershell -NoProfile -ExecutionPolicy Bypass -File "%LOCALAPPDATA%\Programs\Voxlate\worker\setup_worker.ps1" -ModelsSource "F:\voxlate-models"
```
Python packages still need internet; the models then don't. Copied models need no Hugging Face token.

### Where everything is
| What | Location |
|---|---|
| App | `%LOCALAPPDATA%\Programs\Voxlate\Voxlate.exe` |
| Translation engine (Python) | `%LOCALAPPDATA%\Programs\Voxlate\worker\.venv\` |
| Engine setup script | `%LOCALAPPDATA%\Programs\Voxlate\worker\setup_worker.ps1` |
| AI models (one folder per model) | `%LOCALAPPDATA%\Voxlate\models\` |
| Model list + versions | `%LOCALAPPDATA%\Voxlate\models\manifest.json` |
| Your voice profile (encrypted) | `%LOCALAPPDATA%\Voxlate\profile\` |
| **Setup logs** | `%LOCALAPPDATA%\Voxlate\logs\setup-<date>-<time>.log` |
| **Engine log** (previous run: `worker.prev.log`) | `%LOCALAPPDATA%\Voxlate\logs\worker.log` |
| Installed package versions | `%LOCALAPPDATA%\Voxlate\logs\installed-packages.txt` |

Tip: paste a path into the Explorer address bar to open it. `%LOCALAPPDATA%` is usually `C:\Users\<you>\AppData\Local`. The app's **Open logs** button opens the logs folder.

---

## Part 4: First run

### Step 8: Set up Voxlate
1. Open **Voxlate** from the Start menu. The status shows **Starting** with progress ("Loading models...") and turns to **Ready**. The first start on a GPU can take a few minutes.
2. Choose your real microphone and click **Confirm microphone**.
3. Click **Run audio path check**. Within a few seconds it shows either **"Signal reached the virtual microphone"** or a specific reason with a fix. Use **Retry** after fixing, or **Skip for now** so a demo is never blocked.
4. Voice setup: tick the consent box, click **Record**, read the script aloud, click **Stop**, then **Play back** and **Save voice**.

### Step 9: Use it in Google Meet
1. In Voxlate, choose **Hindi > English** and turn the **switch ON**. The status turns green.
2. In Google Meet, open **More options > Settings > Audio**:
   - **Microphone:** `CABLE Output (VB-Audio Virtual Cable)`
   - **Speakers:** your headphones
3. Speak Hindi. The other side hears English in your voice.
4. After the call, set Meet's microphone back to your real mic.

---

## Test checklist (build PC, then demo PC)

Tick each line. If one fails, stop there and send the files named in the last column.

| # | Do | Expect | If not, send |
|---|---|---|---|
| 1 | Build PC: run `build_windows.ps1` (Step 6) | Lines `== Qt: C:\Qt\...\msvc2022_64` and `== Compiler: ...\Hostx64\x64\cl.exe`, ends with `Installer: ...\dist\Voxlate-Setup-0.1.0.exe` | The whole console output |
| 2 | Check `wheels\` in the project | `indictranstoolkit-1.1.1-cp311-cp311-win_amd64.whl` | Console output |
| 3 | Demo PC: run the installer **without** a token | Within seconds: `No access (HTTP 401)` and the 4 steps. No big downloads happened. | Newest `setup-*.log` |
| 4 | Start menu > **Voxlate - Repair setup**, paste the token | `Access OK` for both models, then packages, `imports OK`, models, `CUDA: True ...`, `Worker setup complete.` | Newest `setup-*.log` |
| 5 | Run Repair setup again | Fast: `Reusing Python environment`, every model `OK (already downloaded)` | Newest `setup-*.log` |
| 6 | Open Voxlate | Header: **Starting** with "Loading ..." steps, then **Ready** (first GPU start: up to a few minutes) | `worker.log` |
| 7 | Confirm mic, **Run audio path check** | Pass, or a specific reason within ~10 s. Never an endless "Checking..." | `worker.log` (lists every audio device) |
| 8 | Dashboard: switch ON, speak Hindi | English comes out of `CABLE Output` (test in Meet or Sound settings > Recording > CABLE Output level meter) | `worker.log` |

All files are in `%LOCALAPPDATA%\Voxlate\logs\`. None of them contain your token, and `worker.log` never contains what you said.

---

## Troubleshooting

### Build (build_windows.ps1)
| Message | Fix |
|---|---|
| `No Qt >= 6.5 'MSVC 2022 64-bit' kit found` / `is not an MSVC x64 kit` | In Qt MaintenanceTool, add **MSVC 2022 64-bit** to your Qt version. MinGW/ARM64 kits can't be used. Or pass `-QtDir`. |
| `Expected the 64-bit compiler (...\Hostx64\x64\cl.exe)` / CMake "considered but not accepted ... (64bit)" | Install **Desktop development with C++** in the Visual Studio Installer. The script loads `vcvars64.bat` itself; run it from a normal PowerShell. |
| Old compiler stuck in the build | Handled automatically (build\ is wiped when compiler or Qt changed). Force it with `-Clean`. |
| `ninja: error: manifest 'build.ninja' still dirty after 100 tries` | The PC clock or time zone was wrong. The script now resets future file times and rebuilds. Fix the clock in *Settings > Time & language*. |
| `pip wheel IndicTransToolkit failed` | The build PC needs the VS C++ tools (Step 5). The wheel is built once into `wheels\` and reused. |
| `Inno Setup 6 (ISCC.exe) not found` | Install Inno Setup 6 or pass `-Iscc "<path>\ISCC.exe"`. |
| `WrapVulkanHeaders not found` | Harmless; ignore. |

### Engine setup (installer console / Repair setup)
| Message | Fix |
|---|---|
| `No access (HTTP 401)` / `401 Cannot access gated repo` | Token missing or invalid. Create a **Read** token (Step 4), then run Repair setup and paste it. Set `HF_TOKEN` but still see `Hugging Face token: NOT provided`? The variable wasn't saved, or the window was opened before you set it. Check it in the environment-variables dialog and open a new window. |
| `No Python at 'C:\Users\<someone else>\...\python.exe'` | The install folder was copied from another PC. Run Repair setup (it creates a new environment), or install with the installer instead of copying. |
| Setup stops right after `PyTorch 2.5.1 (...)` | A package download failed (network, proxy or antivirus). Run Repair setup; it continues from there. Send the newest `setup-*.log` if it fails again. |
| `No access (HTTP 403)` | Token works but the terms are not accepted. Open both model pages (Step 4) while logged in and click **Agree**. Then run Repair setup. |
| `[WinError 1314] A required privilege is not held by the client` | Came from the old symlink-based download. Setup now writes plain files, and Developer Mode is not needed. Delete the half-downloaded folder in `%LOCALAPPDATA%\Voxlate\models\` and run Repair setup. |
| `An error happened while trying to locate the file on the Hub` / timeouts | A network blip. Each model is retried 3 times automatically; if it still fails, run Repair setup (finished models are skipped, partial ones resume). |
| `Cannot reach huggingface.co` / `pypi.org` | Check internet, proxy or firewall. |
| `less than 15 GB free` | Free disk space on the drive that holds `%LOCALAPPDATA%`. |
| `No NVIDIA GPU found` | Expected on PCs without NVIDIA: the CPU engine is installed (slower). |
| `CUDA: False` on an NVIDIA PC | Update the NVIDIA driver (Step 1), then run Repair setup. |
| `IndicTransToolkit ... no prebuilt wheel` / tries to compile | The installer was built without `wheels\`. Rebuild with `build_windows.ps1`. |

### App
| Symptom | Fix |
|---|---|
| Status stays yellow **Starting** | It now shows progress. If nothing changes for 10 minutes, or the engine crashes, it turns red with the reason, plus **Retry** and **Open logs** buttons. Check `worker.log`. "Model ... is not downloaded" means: run Repair setup. |
| "Translation engine not installed" | Run Repair setup. |
| Audio path check: **Virtual cable not found** | Install VB-CABLE (Step 2), reboot, press **Detect again**. |
| Audio path check: **Microphone access blocked by Windows** | *Settings > Privacy & security > Microphone*: turn on **Microphone access** and **Let desktop apps access your microphone**, then **Retry**. |
| Audio path check: **Audio device busy** | Close other audio apps, or untick *Allow applications to take exclusive control* in the CABLE device's *Properties > Advanced*. |
| Audio path check: **No signal received** | In Sound settings, make sure CABLE Input and CABLE Output are enabled and not muted. Reinstall VB-CABLE and reboot if it persists. |
| Audio path check: **Engine not responding** | Press Retry. If the engine shows an error, use its Retry / Open logs. |
| Need to demo now | **Skip for now** on the audio check page. You can run the check later from the dashboard. |

---

## Uninstall
1. *Settings > Apps > Voxlate > Uninstall*.
2. The uninstaller asks whether to delete `%LOCALAPPDATA%\Voxlate\` (models, logs and voice profile, several GB). Choose **No** to keep the models for a later reinstall.
