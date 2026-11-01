# Third-party components, licenses and what Voxlate bundles

| Component | Used for | License | Bundled in installer? | Commercial use |
|---|---|---|---|---|
| Qt 6.8 (Core, Gui, Qml, Quick, QuickControls2, Widgets) | Desktop UI | LGPL-3.0 (dynamic linking via windeployqt DLLs) | Yes (DLLs) | Yes, with LGPL obligations (ship license, allow relinking) |
| uv (Astral) | Installs Python 3.11 + packages | MIT / Apache-2.0 | Yes (`tools\uv.exe`) | Yes |
| Python 3.11 (python-build-standalone) | Worker runtime | PSF | Downloaded at setup | Yes |
| PyTorch 2.5.1 (+CUDA runtime) | Inference | BSD-3 (+ NVIDIA EULA for CUDA libs) | Downloaded at setup | Yes |
| PortAudio / sounddevice | WASAPI audio I/O | MIT | Downloaded at setup | Yes |
| Silero VAD 5.1 | Speech activity | MIT | Downloaded at setup | Yes |
| faster-whisper / CTranslate2 + Whisper weights | ASR | MIT | Weights downloaded at setup | Yes |
| IndicTrans2 distilled 200M (AI4Bharat) + IndicTransToolkit | Hindi↔English MT (default) | MIT | Downloaded at setup | Yes |
| Kokoro-82M | Base TTS (Hindi + English voices) | Apache-2.0 | Downloaded at setup | Yes |
| misaki / espeak-ng (via espeakng-loader) | Grapheme→phoneme for Kokoro | Apache-2.0 / **GPL-3.0** (espeak-ng) | Downloaded at setup | Review GPL implications before a commercial bundle |
| OpenVoice V2 converter (MyShell) | Voice/timbre conversion to enrolled owner | MIT | Code + weights downloaded at setup | Yes |
| NLLB-200 distilled 600M (Meta) | MT comparison only (`--nllb`) | CC-BY-NC-4.0 | Opt-in download | **No** |
| XTTS-v2 (Coqui) | Cloning comparison only (`--xtts`) | Coqui Public Model License | Opt-in download, explicit AGREE prompt | **No** (outputs too) |
| VB-CABLE (VB-Audio) | Virtual microphone | Donationware; redistribution needs a vendor license | **No**; user installs it | Contact VB-Audio for bundling/rebranding |

Model weights are never stored in the app source or installer. Exact downloaded revisions are recorded in `%LOCALAPPDATA%\Voxlate\models\manifest.json`, and exact Python package versions in `worker\requirements.lock.txt` after setup.

The UI does **not** claim a "Voxlate Virtual Microphone"; it names the actual third-party cable device. A branded device would require a signed custom driver (out of MVP scope).
