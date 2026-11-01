# Voxlate · Rebuild on another PC

How to build `Voxlate.exe` and `Voxlate-Setup-0.1.0.exe` from source on a fresh Windows PC.
To *install* Voxlate, you don't need any of this. Use the installer and [QUICK_INSTALL.md](QUICK_INSTALL.md).

**Before you start:** check that the current build works on the first PC (Voxlate opens and reaches **Ready**), so you know the source you copy is good.

| You changed | You need |
|---|---|
| Nothing; you just need the installer on another PC | Nothing. Copy `dist\Voxlate-Setup-0.1.0.exe`. |
| Only `worker\` (Python) or the `.md` docs | **Part C** (repackage). Inno Setup only, about 2 minutes. |
| `desktop\` (C++/QML), or no earlier build exists | **Parts A + B** (full build). |

Needs: Windows 10/11 x64, about 15 GB free, internet. All tools are free.

---

## Part A: Prepare the build PC (once)

Open **PowerShell** (not as administrator unless a step says so) and run these one at a time.

### A1. Visual Studio 2022 Build Tools (C++ compiler, CMake, Ninja)
```
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --override "--passive --wait --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```
Windows asks for administrator permission; allow it. It takes 10–20 minutes. Afterwards, open *Visual Studio Installer* and check that **Build Tools 2022** shows **Desktop development with C++**.

### A2. Qt 6 (MSVC 2022 64-bit kit)
The app needs only the base Qt modules (Quick, QuickControls2, Widgets). Pick **one** option:

- **Option 1: Qt Online Installer** (needs a free Qt account). Download <https://www.qt.io/download-qt-installer-oss>. Choose *Custom installation* > **Qt 6.8.x** (LTS) > tick **MSVC 2022 64-bit** only. Install to `C:\Qt`.
- **Option 2: no account (aqtinstall).** Install uv, then download the official Qt binaries:
  ```
  winget install --id astral-sh.uv -e
  ```
  Close and reopen PowerShell, then:
  ```
  uvx --from aqtinstall aqt install-qt windows desktop 6.8.3 win64_msvc2022_64 -O C:\Qt
  ```

Check that this file exists: `C:\Qt\6.8.3\msvc2022_64\lib\cmake\Qt6\Qt6Config.cmake`. MinGW and ARM64 kits do **not** work.

### A3. Inno Setup 6 (makes the installer)
```
winget install --id JRSoftware.InnoSetup -e
```

### A4. Copy the project
Copy the project folder (for example `E:\voxlate\windows app`) to the build PC. You can leave out:
- `build\`, `dist\`, `vox\`: build output and a test install, recreated by the build
- any `.venv\` or `__pycache__\` folder

**Keep `wheels\`.** It holds the prebuilt `indictranstoolkit-1.1.1-cp311-cp311-win_amd64.whl`. Without it, the build compiles that file again (this needs A1, and takes a few minutes).

Models are **not** needed to build. They are downloaded on each PC at install time.

---

## Part B: Full build

In a **normal PowerShell** window (not the Developer Command Prompt; the script sets up the compiler itself):
```
cd "E:\voxlate\windows app"
powershell -NoProfile -ExecutionPolicy Bypass -File build_windows.ps1 -Clean
```
- `-Clean` starts from an empty `build\`. Always use it on a new PC: a `build\` folder copied from another PC points at that PC's paths.
- To use a specific Qt kit: add `-QtDir C:\Qt\6.8.3\msvc2022_64`.

**Expect these lines**, in order:
```
== Qt: C:\Qt\6.8.3\msvc2022_64
== Compiler: ...\Hostx64\x64\cl.exe
== configure + build (Release)
== windeployqt ...
== worker source (no venv, no models)
== uv 0.5.11 ...
== installer (...\ISCC.exe)
Installer: E:\voxlate\windows app\dist\Voxlate-Setup-0.1.0.exe
```

**Results**

| File | What |
|---|---|
| `dist\Voxlate-Setup-0.1.0.exe` | The installer to give to other PCs |
| `dist\Voxlate\` | The staged app (what the installer contains) |
| `build\Voxlate.exe` | The bare app, without Qt DLLs. Don't run it directly. |

If the build fails, check the **Build** table in [QUICK_INSTALL.md](QUICK_INSTALL.md#troubleshooting), or send the whole console output.

---

## Part C: Repackage only (worker or docs changed)

Needs an earlier full build in `dist\Voxlate\` and Inno Setup (A3). No Qt or compiler.
```
cd "E:\voxlate\windows app"
robocopy worker dist\Voxlate\worker /MIR /XD .venv __pycache__ bench_results
copy README.md, INSTALL.md, QUICK_INSTALL.md, THIRD_PARTY.md dist\Voxlate
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\voxlate.iss
```
It ends with `Successful compile` and writes a new `dist\Voxlate-Setup-0.1.0.exe`.
If Inno Setup was installed per-user, its path is `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`.

Before repackaging, run the worker tests (needs a worker environment, for example one created by setup):
```
cd worker
<path to a worker .venv>\Scripts\python.exe -m unittest discover -s tests
```
Expect `Ran 20 tests ... OK`.

---

## Part D: Check the new installer

Test on a PC (or a second Windows user account) that has never had Voxlate:
1. Run `Voxlate-Setup-0.1.0.exe`, paste a Hugging Face Read token on the token page, and wait for `Worker setup complete.`
2. Open Voxlate from the Start menu. It should reach **Ready**.
3. Continue with the test checklist in [QUICK_INSTALL.md](QUICK_INSTALL.md#test-checklist-build-pc-then-demo-pc).

To change the version number, edit `#define AppVersion` in `installer\voxlate.iss` (the file name changes with it).
