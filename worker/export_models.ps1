# Copies the downloaded models from this PC to a folder (e.g. a USB stick) for an offline install elsewhere:
#   powershell -NoProfile -ExecutionPolicy Bypass -File export_models.ps1 -Destination "F:\voxlate-models"
# Then on the target PC:
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup_worker.ps1 -ModelsSource "F:\voxlate-models"
# The hf\ folder is skipped: it can hold a saved Hugging Face token. Keep this file ASCII (PowerShell 5.1).
param([Parameter(Mandatory = $true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$src = Join-Path $env:LOCALAPPDATA 'Voxlate\models'
if (-not (Test-Path -LiteralPath $src)) { throw "No models found at $src. Run setup on this PC first." }
$incomplete = @(Get-ChildItem -LiteralPath $src -Directory | Where-Object {
    $_.Name -ne 'hf' -and -not (Test-Path -LiteralPath (Join-Path $_.FullName '.voxlate_complete')) })
foreach ($d in $incomplete) { Write-Warning "$($d.Name) is not fully downloaded; the target PC will finish it online." }
$dst = $Destination
if ($dst.EndsWith('\')) { $dst += '.' }  # a quoted path ending in \ breaks robocopy's argument parsing
robocopy.exe $src $dst /E /XD hf /R:1 /W:1 /NFL /NDL
if ($LASTEXITCODE -ge 8) { throw "robocopy failed with code $LASTEXITCODE" }
Write-Host "Models exported to $Destination"
Write-Host "On the target PC run: setup_worker.ps1 -ModelsSource `"$Destination`""
exit 0
