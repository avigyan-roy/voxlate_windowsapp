# Builds Voxlate.exe, stages it with Qt runtime + worker source + uv + prebuilt wheels, and produces the installer.
# Run from a normal PowerShell window (no Developer Command Prompt needed), in this folder:
#   powershell -NoProfile -ExecutionPolicy Bypass -File build_windows.ps1
#   ... -QtDir C:\Qt\6.12.0\msvc2022_64   use a specific Qt kit (default: newest MSVC 64-bit kit >= 6.5 in <drive>:\Qt)
#   ... -Clean                           wipe build\ first
# Needs: Visual Studio 2022 (Build Tools) with "Desktop development with C++", Qt >= 6.5 "MSVC 2022 64-bit", Inno Setup 6.
# Windows PowerShell 5.1 compatible; keep this file ASCII.
param(
  [string]$QtDir = '',
  [switch]$Clean,
  [string]$Iscc = '',
  [string]$UvVersion = '0.5.11'
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location -LiteralPath $root

function Assert-Exit([string]$what) {
  if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE). See the output above." }
}

# ------------------------------------------------------------------ Qt kit
function Test-QtKit([string]$dir) { return Test-Path -LiteralPath (Join-Path $dir 'lib\cmake\Qt6\Qt6Config.cmake') }
$addMsvc = 'Open Qt MaintenanceTool > Add or remove components > Qt <version> and tick "MSVC 2022 64-bit", then rerun.'

if (-not $QtDir) {
  $kits = @()
  foreach ($drv in Get-PSDrive -PSProvider FileSystem) {
    $qtRoot = Join-Path $drv.Root 'Qt'
    if (-not (Test-Path -LiteralPath $qtRoot)) { continue }
    foreach ($verDir in Get-ChildItem -LiteralPath $qtRoot -Directory -ErrorAction SilentlyContinue) {
      $ver = $null
      if (-not [version]::TryParse($verDir.Name, [ref]$ver)) { continue }
      if ($ver -lt [version]'6.5') { continue }
      foreach ($kit in Get-ChildItem -LiteralPath $verDir.FullName -Directory -Filter 'msvc20*_64' -ErrorAction SilentlyContinue) {
        if ($kit.Name -match 'arm64') { continue }
        if (Test-QtKit $kit.FullName) { $kits += New-Object PSObject -Property @{ Version = $ver; Name = $kit.Name; Path = $kit.FullName } }
      }
    }
  }
  if ($kits.Count -eq 0) { throw "No Qt >= 6.5 'MSVC 2022 64-bit' kit found in <drive>:\Qt (mingw and arm64 kits cannot be used). $addMsvc Or pass -QtDir." }
  $QtDir = ($kits | Sort-Object -Property @{ Expression = 'Version'; Descending = $true }, @{ Expression = 'Name'; Descending = $true } | Select-Object -First 1).Path
}
$QtDir = $QtDir.TrimEnd('\')
$kitName = Split-Path -Leaf $QtDir
if ($kitName -match 'mingw|arm64|llvm' -or $kitName -notmatch '^msvc20\d\d_64$') {
  throw "Qt kit '$QtDir' is not an MSVC x64 kit. $addMsvc"
}
if (-not (Test-QtKit $QtDir)) { throw "Qt kit '$QtDir' has no lib\cmake\Qt6\Qt6Config.cmake. $addMsvc" }
$windeployqt = Join-Path $QtDir 'bin\windeployqt.exe'
if (-not (Test-Path -LiteralPath $windeployqt)) { throw "windeployqt.exe not found in '$QtDir\bin'." }
Write-Host "== Qt: $QtDir"

# ------------------------------------------------------------------ x64 MSVC environment (works from a plain PowerShell)
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) { throw "vswhere.exe not found. Install Visual Studio 2022 Build Tools with 'Desktop development with C++'." }
$vsPath = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
Assert-Exit 'vswhere'
if (-not $vsPath) { throw "No Visual Studio with the C++ x64 tools found. Install 'Desktop development with C++' in the Visual Studio Installer." }
$vcvars = Join-Path $vsPath 'VC\Auxiliary\Build\vcvars64.bat'
if (-not (Test-Path -LiteralPath $vcvars)) { throw "vcvars64.bat not found at $vcvars" }
Write-Host "== MSVC x64 environment from $vcvars"
$helper = Join-Path $env:TEMP 'voxlate-vcvars64.cmd'
# vcvars' own errorlevel is unreliable; the cl.exe check below is the real test.
Set-Content -LiteralPath $helper -Encoding ASCII -Value @('@echo off', "call `"$vcvars`" >nul", 'set')
$envLines = & cmd.exe /c $helper
foreach ($line in $envLines) {
  if ($line -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') }
}
Remove-Item -LiteralPath $helper -ErrorAction SilentlyContinue
$cl = (Get-Command cl.exe -ErrorAction SilentlyContinue)
if (-not $cl -or $cl.Source -notmatch '\\Hostx64\\x64\\cl\.exe$') {
  throw "Expected the 64-bit compiler (...\Hostx64\x64\cl.exe) but got '$($cl.Source)'. Check the Visual Studio C++ x64 tools."
}
$cl = $cl.Source
Write-Host "== Compiler: $cl"

# cmake + ninja ship with VS ("C++ CMake tools for Windows") and with Qt (Tools\CMake_64, Tools\Ninja).
$qtTools = Join-Path (Split-Path -Parent (Split-Path -Parent $QtDir)) 'Tools'
foreach ($t in @(@('cmake.exe', 'CMake_64\bin'), @('ninja.exe', 'Ninja'))) {
  if (-not (Get-Command $t[0] -ErrorAction SilentlyContinue)) {
    $p = Join-Path $qtTools $t[1]
    if (Test-Path -LiteralPath (Join-Path $p $t[0])) { $env:Path = "$p;$env:Path" }
    else { throw "$($t[0]) not found. Install 'C++ CMake tools for Windows' in the Visual Studio Installer, or CMake/Ninja in Qt MaintenanceTool." }
  }
}

# ------------------------------------------------------------------ clock skew + stale cache
$buildDir = Join-Path $root 'build'
$wipe = [bool]$Clean
$limit = (Get-Date).AddMinutes(1)
$future = @(Get-ChildItem -LiteralPath (Join-Path $root 'desktop'), (Join-Path $root 'worker'), (Join-Path $root 'installer') -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch '\\\.venv\\' -and $_.LastWriteTime -gt $limit })
$future += @(Get-ChildItem -LiteralPath $root -File | Where-Object { $_.LastWriteTime -gt $limit })
if ($future.Count -gt 0) {
  Write-Warning "$($future.Count) source file(s) have timestamps in the future (newest: $(($future | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime)). The system clock or time zone may be wrong. Resetting them to now and rebuilding from scratch."
  $now = Get-Date
  foreach ($f in $future) {
    try { $f.LastWriteTime = $now } catch { Write-Warning "Could not reset $($f.FullName): $($_.Exception.Message)" }
  }
  $wipe = $true
}

$cache = Join-Path $buildDir 'CMakeCache.txt'
if (-not $wipe -and (Test-Path -LiteralPath $cache)) {
  $cacheLines = Get-Content -LiteralPath $cache
  $cxx = $cacheLines | Where-Object { $_ -like 'CMAKE_CXX_COMPILER:*' } | Select-Object -First 1
  $qt6 = $cacheLines | Where-Object { $_ -like 'Qt6_DIR:*' } | Select-Object -First 1
  $wantQt6 = (Join-Path $QtDir 'lib\cmake\Qt6').Replace('/', '\').TrimEnd('\')
  $haveQt6 = ''
  if ($qt6) { $haveQt6 = ($qt6 -split '=', 2)[1].Replace('/', '\').TrimEnd('\') }
  if (-not $cxx -or $cxx -notmatch 'Hostx64[\\/]x64') {
    Write-Host "== build\ was configured with another compiler ($cxx); wiping it"
    $wipe = $true
  } elseif ($haveQt6 -ne $wantQt6) {
    Write-Host "== build\ was configured with another Qt ($haveQt6); wiping it"
    $wipe = $true
  }
}
if ($wipe -and (Test-Path -LiteralPath $buildDir)) { Remove-Item -LiteralPath $buildDir -Recurse -Force }

# ------------------------------------------------------------------ configure + build
Write-Host '== configure + build (Release)'
cmake -S (Join-Path $root 'desktop') -B $buildDir -G Ninja -DCMAKE_BUILD_TYPE=Release "-DCMAKE_PREFIX_PATH=$($QtDir.Replace('\', '/'))" "-DCMAKE_CXX_COMPILER=$($cl.Replace('\', '/'))"
Assert-Exit 'cmake configure'
cmake --build $buildDir
Assert-Exit 'build'

$stage = Join-Path $root 'dist\Voxlate'
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage, (Join-Path $stage 'tools'), (Join-Path $stage 'wheels') | Out-Null
Copy-Item -LiteralPath (Join-Path $buildDir 'Voxlate.exe') -Destination $stage

Write-Host '== windeployqt (Qt DLLs, plugins, QML imports, MSVC runtime installer)'
& $windeployqt --release --compiler-runtime --no-translations --qmldir (Join-Path $root 'desktop\qml') (Join-Path $stage 'Voxlate.exe')
Assert-Exit 'windeployqt'
$redist = Join-Path $stage 'vc_redist.x64.exe'
if (-not (Test-Path -LiteralPath $redist)) {
  $fromVs = Join-Path "$env:VCToolsRedistDir" 'vc_redist.x64.exe'
  if (-not (Test-Path -LiteralPath $fromVs)) { throw "vc_redist.x64.exe not found (windeployqt did not deploy it and VCToolsRedistDir has none). Repair the Visual Studio C++ tools." }
  Copy-Item -LiteralPath $fromVs -Destination $redist
}

Write-Host '== worker source (no venv, no models)'
robocopy.exe (Join-Path $root 'worker') (Join-Path $stage 'worker') /E /XD .venv __pycache__ bench_results /NFL /NDL /NJH /NJS /NP
if ($LASTEXITCODE -ge 8) { throw "robocopy of the worker failed (code $LASTEXITCODE)" }

Write-Host "== uv $UvVersion (MIT/Apache-2.0) for Python + package install"
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$zip = Join-Path $env:TEMP "uv-$UvVersion-x86_64-pc-windows-msvc.zip"
$uv = Join-Path $stage 'tools\uv.exe'
try {
  if (-not (Test-Path -LiteralPath $zip)) {
    Invoke-WebRequest -Uri "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip" -OutFile $zip -UseBasicParsing
  }
  Expand-Archive -LiteralPath $zip -DestinationPath (Join-Path $stage 'tools') -Force
} catch {
  Remove-Item -LiteralPath $zip -ErrorAction SilentlyContinue
  $local = Get-Command uv.exe -ErrorAction SilentlyContinue
  if (-not $local) { throw "Could not download uv $UvVersion ($($_.Exception.Message)) and no uv.exe is installed." }
  Write-Warning "uv download failed; bundling the installed $($local.Source) instead."
  Copy-Item -LiteralPath $local.Source -Destination $uv
}
if (-not (Test-Path -LiteralPath $uv)) { throw "uv.exe missing from $(Split-Path -Parent $uv)" }

Write-Host '== IndicTransToolkit 1.1.1 wheel (cp311-win_amd64; PyPI has only an sdist that needs a C compiler)'
$wheels = Join-Path $root 'wheels'
New-Item -ItemType Directory -Force -Path $wheels | Out-Null
$itWheel = { Get-ChildItem -LiteralPath $wheels -Filter '*.whl' | Where-Object { $_.Name -like 'indictranstoolkit-1.1.1-cp311-cp311-win_amd64.whl' } | Select-Object -First 1 }
if (-not (& $itWheel)) {
  & $uv python install 3.11
  Assert-Exit 'uv python install 3.11'
  $wenv = Join-Path $buildDir 'wheelenv'
  $wpy = Join-Path $wenv 'Scripts\python.exe'
  if (-not (Test-Path -LiteralPath $wpy)) {
    & $uv venv --seed --python 3.11 --python-preference only-managed $wenv
    Assert-Exit 'uv venv (wheel build)'
  }
  & $wpy -m pip wheel --no-deps --wheel-dir $wheels 'IndicTransToolkit==1.1.1'
  Assert-Exit 'pip wheel IndicTransToolkit'
  if (-not (& $itWheel)) { throw "pip did not produce indictranstoolkit-1.1.1-cp311-cp311-win_amd64.whl in $wheels" }
}
Copy-Item -LiteralPath (& $itWheel).FullName -Destination (Join-Path $stage 'wheels')

Copy-Item -LiteralPath (Join-Path $root 'README.md'), (Join-Path $root 'INSTALL.md'), (Join-Path $root 'QUICK_INSTALL.md'), (Join-Path $root 'THIRD_PARTY.md') -Destination $stage

# ------------------------------------------------------------------ installer
if (-not $Iscc) {
  $cands = @((Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'), (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'), (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'))
  $Iscc = $cands | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  if (-not $Iscc) { $c = Get-Command ISCC.exe -ErrorAction SilentlyContinue; if ($c) { $Iscc = $c.Source } }
}
if (-not $Iscc -or -not (Test-Path -LiteralPath $Iscc)) {
  throw "Inno Setup 6 (ISCC.exe) not found. Install it from https://jrsoftware.org/isdl.php or pass -Iscc. The staged app is in dist\Voxlate."
}
Write-Host "== installer ($Iscc)"
& $Iscc (Join-Path $root 'installer\voxlate.iss')
Assert-Exit 'ISCC'
Write-Host "Installer: $(Join-Path $root 'dist\Voxlate-Setup-0.1.0.exe')"
exit 0
