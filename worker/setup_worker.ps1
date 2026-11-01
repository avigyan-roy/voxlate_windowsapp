# Creates the worker's Python environment and downloads models. The installer runs it; the Start-menu
# shortcut "Voxlate - Repair setup" re-runs it. Safe to re-run: reuses the venv, skips finished models,
# resumes partial downloads. Needs nothing preinstalled (uv.exe is bundled in ..\tools).
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup_worker.ps1            # NVIDIA GPU (CUDA 12.4)
#   ... -Cpu                 no NVIDIA GPU (also chosen automatically when none is found)
#   ... -ModelsSource <dir>  copy pre-downloaded models (see export_models.ps1), e.g. from a USB stick
#   ... -AskToken            prompt for a Hugging Face token if one is needed and none is set
#   ... -Nllb   also fetch NLLB-200 comparison model (non-commercial)
#   ... -Xtts   also install XTTS-v2 comparison path (non-commercial, asks you to accept CPML)
# The Hugging Face token is read from the HF_TOKEN environment variable and is never logged.
# Windows PowerShell 5.1 compatible; keep this file ASCII.
param([switch]$Cpu, [switch]$Nllb, [switch]$Xtts, [string]$ModelsSource = '', [switch]$AskToken)
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
Set-Location -LiteralPath $here

$dataDir = Join-Path $env:LOCALAPPDATA 'Voxlate'
$modelsDir = Join-Path $dataDir 'models'
$logDir = Join-Path $dataDir 'logs'
New-Item -ItemType Directory -Force -Path $modelsDir, $logDir | Out-Null
$log = Join-Path $logDir ('setup-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')

function Log([string]$msg) {
  Write-Host $msg
  Add-Content -LiteralPath $log -Value $msg -Encoding UTF8
}

function Fail([string]$msg) {
  Log ''
  Log "ERROR: $msg"
  Log "Full log: $log"
  Log 'After fixing it, run "Voxlate - Repair setup" from the Start menu. No reinstall needed.'
  # The installer shows this in its error dialog (its console window closes on exit). ASCII: Inno reads it as ANSI.
  Get-Content -LiteralPath $log -Tail 20 | Set-Content -LiteralPath (Join-Path $logDir 'last-error.txt') -Encoding ASCII
  exit 1
}

trap {
  Fail ("Unexpected error: " + $_.Exception.Message + " (" + $_.InvocationInfo.PositionMessage + ")")
}

# Runs a native command, copies its stdout+stderr to the console and the log, returns its exit code.
function Invoke-Logged([string]$what, [string]$exe, [string[]]$argList) {
  Log "> $what"
  $ErrorActionPreference = 'Continue'  # native stderr lines must not become terminating errors
  $global:LASTEXITCODE = -1  # stays -1 if the program cannot be started at all
  & $exe @argList 2>&1 | ForEach-Object { Log ('  ' + $_) }
  return $LASTEXITCODE
}

function Run([string]$what, [string]$exe, [string[]]$argList) {
  $code = Invoke-Logged $what $exe $argList
  if ($code -ne 0) { Fail "$what failed (exit code $code). See the lines above." }
}

function Test-Online([string]$url) {
  try {
    Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing -TimeoutSec 20 | Out-Null
    return $true
  } catch {
    return [bool]$_.Exception.Response  # any HTTP answer means the network works
  }
}

function Test-ModelComplete([string]$repo) {
  $name = ($repo -split '/')[-1]
  return Test-Path -LiteralPath (Join-Path (Join-Path $modelsDir $name) '.voxlate_complete')
}

# Environment for uv, Python and huggingface_hub (inherited by every child process).
$env:UV_LINK_MODE = 'copy'
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = '1'
$env:HF_HUB_ETAG_TIMEOUT = '60'
$env:HF_HUB_DOWNLOAD_TIMEOUT = '60'
$env:HF_HUB_DISABLE_PROGRESS_BARS = '1'
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONIOENCODING = 'utf-8'
Remove-Item Env:PYTHONHOME, Env:PYTHONPATH -ErrorAction SilentlyContinue
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

Log "== Voxlate worker setup $(Get-Date -Format 's')"
Log "Worker folder: $here"
Log "Models folder: $modelsDir"
Log ("Options: Cpu=$Cpu Nllb=$Nllb Xtts=$Xtts ModelsSource='$ModelsSource' AskToken=$AskToken")

# ------------------------------------------------------------------ preflight
Log '== Preflight'
$drive = New-Object System.IO.DriveInfo ([System.IO.Path]::GetPathRoot($modelsDir))
$freeGB = [math]::Round($drive.AvailableFreeSpace / 1GB, 1)
Log "Free space on $($drive.Name): $freeGB GB"
if ($freeGB -lt 15) {
  Log "WARNING: less than 15 GB free on $($drive.Name). The engine and models need about 15 GB; setup may fail with 'disk full'."
}

$gpus = @(Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
Log ('Graphics: ' + ($gpus -join '; '))
if (-not $Cpu) {
  if (@($gpus | Where-Object { $_ -match 'NVIDIA' }).Count -eq 0) {
    Log 'WARNING: No NVIDIA GPU found. Installing the CPU engine instead (works, but slower).'
    $Cpu = [switch]$true
  } else {
    $smi = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
    if ($smi) {
      $code = Invoke-Logged 'nvidia-smi' $smi.Source @()
      if ($code -ne 0) { Log 'WARNING: nvidia-smi failed. Update the NVIDIA driver if CUDA is False at the end.' }
    } else {
      Log 'WARNING: nvidia-smi not found. Install the latest NVIDIA driver if CUDA is False at the end.'
    }
  }
}

if (Test-Online 'https://huggingface.co') {
  if (-not (Test-Online 'https://pypi.org/simple/')) { Fail 'Cannot reach pypi.org. Check the internet connection, proxy or firewall.' }
  Log 'Internet: OK'
} elseif ($ModelsSource) {
  Log 'WARNING: no internet access. Continuing because -ModelsSource was given; package installs will fail unless the engine is already installed.'
} else {
  Fail 'Cannot reach huggingface.co. Check the internet connection, proxy or firewall (or use -ModelsSource for offline models).'
}

# ------------------------------------------------------------------ offline models (optional)
if ($ModelsSource) {
  if (-not (Test-Path -LiteralPath $ModelsSource)) { Fail "Models source not found: $ModelsSource" }
  $src = $ModelsSource
  if ($src.EndsWith('\')) { $src += '.' }  # a quoted path ending in \ breaks robocopy's argument parsing
  $code = Invoke-Logged "Copy models from $ModelsSource" 'robocopy.exe' @($src, $modelsDir, '/E', '/XD', 'hf', '/R:1', '/W:1', '/NFL', '/NDL', '/NP')
  if ($code -ge 8) { Fail "Copying models from $ModelsSource failed (robocopy code $code)." }
}

# ------------------------------------------------------------------ Hugging Face access (before any big download)
# Keep in sync with GATED in voxlate_worker\fetch_models.py.
$gated = @('ai4bharat/indictrans2-indic-en-dist-200M', 'ai4bharat/indictrans2-en-indic-dist-200M')
$needAccess = @($gated | Where-Object { -not (Test-ModelComplete $_) })
if ($needAccess.Count -gt 0) {
  Log '== Checking Hugging Face access to gated models'
  $token = $env:HF_TOKEN
  if (-not $token) {
    # A token saved earlier by "huggingface-cli login" (worker HF_HOME first, then the default location).
    foreach ($f in @((Join-Path $modelsDir 'hf\token'), (Join-Path $env:USERPROFILE '.cache\huggingface\token'))) {
      if (-not $token -and (Test-Path -LiteralPath $f)) { $token = "$(Get-Content -LiteralPath $f -Raw)".Trim() }
    }
  }
  if (-not $token -and $AskToken) {
    $sec = Read-Host -AsSecureString 'Paste your Hugging Face Read token (input is hidden), then press Enter'
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try { $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr).Trim() }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
  }
  if ($token) { Log 'Hugging Face token: provided' } else { Log 'Hugging Face token: NOT provided' }
  $denied = @()
  foreach ($repo in $needAccess) {
    $headers = @{}
    if ($token) { $headers['Authorization'] = "Bearer $token" }
    # Do not follow redirects: .NET drops the Authorization header on redirect, so a valid token would
    # look denied. Access is decided on the first hop: 401/403 = denied, 2xx/3xx = allowed.
    $status = 0
    try {
      $r = Invoke-WebRequest -Uri "https://huggingface.co/$repo/resolve/main/config.json" -Headers $headers -UseBasicParsing -TimeoutSec 30 -MaximumRedirection 0
      $status = [int]$r.StatusCode
    } catch {
      $resp = $_.Exception.Response
      if ($resp) { $status = [int]$resp.StatusCode }
      elseif ($_.Exception.Message -match 'redirect') { $status = 307 }
      else { Fail "Could not reach huggingface.co to check $repo ($($_.Exception.Message)). Check the internet connection and retry." }
    }
    if ($status -eq 401 -or $status -eq 403) { $denied += $repo; Log "No access (HTTP $status): $repo" }
    elseif ($status -ge 400) { Fail "Unexpected HTTP $status from huggingface.co for $repo. Try again in a few minutes." }
    else { Log "Access OK: $repo" }
  }
  if ($denied.Count -gt 0) {
    Log ''
    Log 'The IndicTrans2 translation models are free but gated. One-time steps:'
    Log '  1. Create a free account: https://huggingface.co/join'
    Log '  2. While logged in, open each page below and click "Agree and access repository":'
    foreach ($r in $denied) { Log "       https://huggingface.co/$r" }
    Log '  3. Create a token with the "Read" role: https://huggingface.co/settings/tokens'
    Log '  4. Run "Voxlate - Repair setup" from the Start menu and paste the token when asked'
    Log '     (or re-run the installer and paste it on the token page).'
    if ($token) { Fail 'The Hugging Face token is invalid or the model terms are not accepted yet (see steps above).' }
    Fail 'A Hugging Face token is needed to download the translation models (see steps above).'
  }
  $env:HF_TOKEN = $token  # for fetch_models in this process tree only; never written to disk or log
}

# ------------------------------------------------------------------ Python 3.11 + venv
$uv = [System.IO.Path]::GetFullPath((Join-Path $here '..\tools\uv.exe'))
if (-not (Test-Path -LiteralPath $uv)) {
  $cmd = Get-Command uv.exe -ErrorAction SilentlyContinue
  if (-not $cmd) { Fail "uv.exe not found at $uv. Reinstall Voxlate." }
  $uv = $cmd.Source
}
$venv = Join-Path $here '.venv'
$py = Join-Path $venv 'Scripts\python.exe'
$venvOk = $false
if (Test-Path -LiteralPath $py) {
  try {
    & $py -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)"
    $venvOk = ($LASTEXITCODE -eq 0)
  } catch { $venvOk = $false }
}
if ($venvOk) {
  Log "== Reusing Python environment $venv"
} else {
  if (Test-Path -LiteralPath $venv) { Log 'Existing Python environment is broken; recreating it.'; Remove-Item -LiteralPath $venv -Recurse -Force }
  Run 'Install Python 3.11 (uv-managed)' $uv @('python', 'install', '3.11')
  Run 'Create Python environment' $uv @('venv', '--python', '3.11', '--python-preference', 'only-managed', $venv)
}

# ------------------------------------------------------------------ packages
if ($Cpu) { $variant = 'cpu' } else { $variant = 'cu124' }
Run "PyTorch 2.5.1 ($variant)" $uv @('pip', 'install', '--python', $py, "torch==2.5.1+$variant", "torchaudio==2.5.1+$variant", '--index-url', "https://download.pytorch.org/whl/$variant")

# IndicTransToolkit has no Windows wheel on PyPI; the installer ships one built by build_windows.ps1.
$common = @('--python', $py)
$wheels = [System.IO.Path]::GetFullPath((Join-Path $here '..\wheels'))
if (@(Get-ChildItem -Path (Join-Path $wheels 'indictranstoolkit-*.whl') -ErrorAction SilentlyContinue).Count -gt 0) {
  $common += @('--find-links', $wheels, '--only-binary', 'indictranstoolkit')  # uv 0.5.11 pip has no --no-build-package
} else {
  Log "WARNING: no prebuilt IndicTransToolkit wheel in $wheels; it will be compiled (needs Visual Studio Build Tools)."
}

$lock = Join-Path $here 'requirements.lock.txt'
if (Test-Path -LiteralPath $lock) {
  # torch comes from the PyTorch index above; OpenVoice is installed below without its conflicting pins.
  $lines = @(Get-Content -LiteralPath $lock | Where-Object { $_ -notmatch '^\s*(torch|torchaudio)\s*==' -and $_ -notmatch '^\s*myshell-openvoice' })
  $tmpLock = Join-Path $env:TEMP "voxlate-lock-$PID.txt"
  [System.IO.File]::WriteAllLines($tmpLock, [string[]]$lines)  # UTF-8 without BOM
  $code = Invoke-Logged 'Pinned packages (requirements.lock.txt)' $uv (@('pip', 'install') + $common + @('--no-deps', '-r', $tmpLock))
  Remove-Item -LiteralPath $tmpLock -ErrorAction SilentlyContinue
  if ($code -ne 0) { Log "WARNING: installing from the lock file failed (exit code $code); falling back to requirements.txt." }
} else {
  Log 'No requirements.lock.txt; resolving from requirements.txt.'
}
Run 'Worker requirements (requirements.txt)' $uv (@('pip', 'install') + $common + @('-r', (Join-Path $here 'requirements.txt')))

Run 'OpenVoice (converter code only, MIT)' $uv @('pip', 'install', '--python', $py, '--no-deps', 'https://github.com/myshell-ai/OpenVoice/archive/refs/heads/main.zip')

if ($Xtts) {
  Run 'XTTS comparison path' $uv @('pip', 'install', '--python', $py, '-r', (Join-Path $here 'requirements-xtts.txt'))
}

$freeze = & $uv pip freeze --python $py
if ($LASTEXITCODE -ne 0) { Fail 'uv pip freeze failed.' }
[System.IO.File]::WriteAllLines((Join-Path $logDir 'installed-packages.txt'), [string[]]$freeze)
if (-not (Test-Path -LiteralPath $lock)) {
  [System.IO.File]::WriteAllLines($lock, [string[]]$freeze)
  Log "== resolved versions written to $lock (copy it into the project's worker folder)"
}

Run 'Import check' $py @('-c', "import faster_whisper, transformers, kokoro, misaki.en, sounddevice, soxr, silero_vad, openvoice.models, spacy; spacy.load('en_core_web_sm'); from voxlate_worker.models import indic_processor; indic_processor(); print('imports OK')")

# ------------------------------------------------------------------ models
Log '== Models (several GB, one time; finished models are skipped)'
$fetch = @('-m', 'voxlate_worker.fetch_models')
if ($Nllb) { $fetch += '--nllb' }
if ($Xtts) { $fetch += '--xtts' }
Run 'Download models' $py $fetch

# ------------------------------------------------------------------ done
Log '== GPU check'
$gpu = & $py -c "import torch; print('CUDA:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
if ($LASTEXITCODE -ne 0) { Fail 'PyTorch failed to start (GPU check).' }
Log "$gpu"
if (-not $Cpu -and "$gpu" -match 'CUDA: False') {
  Log 'WARNING: CUDA is not available. Update the NVIDIA driver (CUDA 12.4 or newer) and run Repair setup; the app will use the CPU until then.'
}
Log "Log: $log"
Log 'Worker setup complete.'
exit 0
