; Inno Setup 6 script. Built by build_windows.ps1 (ISCC.exe installer\voxlate.iss).
; Per-user install: no administrator rights needed (the MSVC runtime installer may ask for consent once).
; Does NOT bundle VB-CABLE (vendor terms) or model weights. Keep this file ASCII.
#define AppVersion "0.1.0"

[Setup]
AppId={{6F0B7C1E-4E0A-4F5B-9C55-7A1D2B0E9A11}
AppName=Voxlate
AppVersion={#AppVersion}
AppPublisher=Voxlate
DefaultDirName={localappdata}\Programs\Voxlate
DefaultGroupName=Voxlate
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Voxlate-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\Voxlate.exe
SetupLogging=yes

[Files]
Source: "..\dist\Voxlate\*"; DestDir: "{app}"; Excludes: "vc_redist.x64.exe"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\dist\Voxlate\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Tasks]
Name: "cpuonly"; Description: "No NVIDIA GPU (install CPU-only engine, slower)"; Flags: unchecked

[Icons]
Name: "{group}\Voxlate"; Filename: "{app}\Voxlate.exe"
; Re-runs engine setup (reuses the venv, skips finished models). Asks for a Hugging Face token only if one is needed.
Name: "{group}\Voxlate - Repair setup"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -NoExit -File ""{app}\worker\setup_worker.ps1"" -AskToken"; WorkingDir: "{app}\worker"; Tasks: not cpuonly
Name: "{group}\Voxlate - Repair setup"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -NoExit -File ""{app}\worker\setup_worker.ps1"" -AskToken -Cpu"; WorkingDir: "{app}\worker"; Tasks: cpuonly
Name: "{group}\Uninstall Voxlate"; Filename: "{uninstallexe}"
; No Startup entry: Voxlate is launched manually by design.

[Run]
Filename: "https://vb-audio.com/Cable/"; Description: "Open the VB-CABLE download page (required virtual microphone, free)"; Flags: postinstall shellexec skipifsilent unchecked
Filename: "{app}\Voxlate.exe"; Description: "Launch Voxlate"; Flags: postinstall nowait skipifsilent unchecked

[InstallDelete]
; Shortcut name used by 0.1.0 builds before "Voxlate - Repair setup".
Type: files; Name: "{group}\Voxlate engine setup (re-run).lnk"

[UninstallDelete]
; Python environment, caches and the lock file written by setup.
Type: filesandordirs; Name: "{app}\worker"

[Code]
var
  TokenPage: TInputQueryWizardPage;

function SetEnvironmentVariable(lpName: String; lpValue: String): Integer;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

procedure InitializeWizard;
begin
  TokenPage := CreateInputQueryPage(wpSelectTasks,
    'Hugging Face token (optional)',
    'Needed once to download the IndicTrans2 translation models.',
    'The IndicTrans2 models are free but gated. Before installing:' + #13#10 +
    '1. Create a free account at https://huggingface.co/join' + #13#10 +
    '2. Logged in, open both pages below and click "Agree and access repository":' + #13#10 +
    '   https://huggingface.co/ai4bharat/indictrans2-indic-en-dist-200M' + #13#10 +
    '   https://huggingface.co/ai4bharat/indictrans2-en-indic-dist-200M' + #13#10 +
    '3. Create a token with the "Read" role at https://huggingface.co/settings/tokens' + #13#10 + #13#10 +
    'Leave empty if the models are already on this PC. The token is used for this download only and is not saved.');
  TokenPage.Add('Read token (starts with hf_):', True);
end;

function RegVCVersion(Root: Integer; var Major, Minor, Bld: Cardinal): Boolean;
var
  Key: String;
begin
  Key := 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64';
  Result := RegQueryDWordValue(Root, Key, 'Major', Major) and
            RegQueryDWordValue(Root, Key, 'Minor', Minor) and
            RegQueryDWordValue(Root, Key, 'Bld', Bld);
end;

{ True if the installed VC++ 2015-2022 x64 runtime is missing or older than the bundled one. }
function VCRedistNeeded(const Exe: String): Boolean;
var
  MS, LS, Major, Minor, Bld, FMajor, FMinor, FBld: Cardinal;
begin
  Result := True;
  if not GetVersionNumbers(Exe, MS, LS) then Exit;
  FMajor := MS shr 16;
  FMinor := MS and $FFFF;
  FBld := LS shr 16;
  if not RegVCVersion(HKLM64, Major, Minor, Bld) then
    if not RegVCVersion(HKLM32, Major, Minor, Bld) then Exit;
  if Major <> FMajor then begin Result := Major < FMajor; Exit; end;
  if Minor <> FMinor then begin Result := Minor < FMinor; Exit; end;
  Result := Bld < FBld;
end;

procedure InstallVCRedist;
var
  Exe: String;
  RC: Integer;
begin
  Exe := ExpandConstant('{tmp}\vc_redist.x64.exe');
  if not FileExists(Exe) then Exit;
  if not VCRedistNeeded(Exe) then begin
    Log('Microsoft Visual C++ runtime is already installed.');
    Exit;
  end;
  WizardForm.StatusLabel.Caption := 'Installing the Microsoft Visual C++ runtime...';
  if not Exec(Exe, '/install /quiet /norestart', '', SW_SHOW, ewWaitUntilTerminated, RC) then
    if not ShellExec('', Exe, '/install /quiet /norestart', '', SW_SHOW, ewWaitUntilTerminated, RC) then
      RC := -1;
  Log('vc_redist exit code: ' + IntToStr(RC));
  { 0 = installed, 1638 = same or newer already present, 3010 = installed, reboot pending }
  if (RC <> 0) and (RC <> 1638) and (RC <> 3010) then
    SuppressibleMsgBox('The Microsoft Visual C++ runtime could not be installed (code ' + IntToStr(RC) + ').' + #13#10 +
      'Voxlate may not start. Install it from https://aka.ms/vs/17/release/vc_redist.x64.exe', mbError, MB_OK, IDOK);
end;

procedure RunWorkerSetup;
var
  Params, Token, ErrFile: String;
  Tail: TArrayOfString;
  RC, I: Integer;
begin
  ErrFile := ExpandConstant('{localappdata}\Voxlate\logs\last-error.txt');
  DeleteFile(ErrFile);
  Token := Trim(TokenPage.Values[0]);
  { Through the environment only, never the command line (visible to other processes and logs). }
  if Token <> '' then SetEnvironmentVariable('HF_TOKEN', Token);
  Params := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\worker\setup_worker.ps1') + '"';
  if WizardIsTaskSelected('cpuonly') then Params := Params + ' -Cpu';
  WizardForm.StatusLabel.Caption := 'Installing the translation engine and downloading models (one time, several GB). Progress is shown in the console window.';
  if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Params, ExpandConstant('{app}\worker'), SW_SHOW, ewWaitUntilTerminated, RC) then
    RC := -1;
  if Token <> '' then SetEnvironmentVariable('HF_TOKEN', '');
  Log('setup_worker.ps1 exit code: ' + IntToStr(RC));
  if RC <> 0 then begin
    Params := '';
    if LoadStringsFromFile(ErrFile, Tail) then
      for I := 0 to GetArrayLength(Tail) - 1 do Params := Params + Tail[I] + #13#10;
    if Params = '' then
      Params := 'The reason is at the end of the newest setup-*.log in:' + #13#10 +
        ExpandConstant('{localappdata}\Voxlate\logs') + #13#10 + #13#10 +
        'Fix it, then run "Voxlate - Repair setup" from the Start menu. You do not need to reinstall.';
    SuppressibleMsgBox('The translation engine setup did not finish (exit code ' + IntToStr(RC) + ').' + #13#10 + #13#10 + Params,
      mbError, MB_OK, IDOK);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    InstallVCRedist;
    RunWorkerSetup;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  D: String;
begin
  if CurUninstallStep = usPostUninstall then begin
    D := ExpandConstant('{localappdata}\Voxlate');
    if DirExists(D) then
      if SuppressibleMsgBox('Also delete the downloaded models, logs and your voice profile?' + #13#10 + D + #13#10 + #13#10 +
        'This frees several GB. Choose No to keep them for a later reinstall.',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
        DelTree(D, True, True, True);
  end;
end;
