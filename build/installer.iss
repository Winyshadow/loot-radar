; Inno Setup script for LootRadarSetup.exe. Don't run this by hand: build/build.ps1 does,
; after PyInstaller has made dist\LootRadar (and passes the version as /DAppVersion=x.y.z).
;
; Installs for the current Windows user only (no admin prompt), into
;   %LOCALAPPDATA%\Programs\Loot Radar
; Personal data lives in %LOCALAPPDATA%\Loot Radar and is never touched by an update; the
; uninstaller asks before deleting it.
;
; Silent update (what Loot Radar itself runs):  LootRadarSetup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LAUNCH=1

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef DistDir
  #define DistDir "..\dist"
#endif
#ifndef WorkDir
  #define WorkDir "work"
#endif

[Setup]
AppId={{8F3B2C1E-6A4D-4E9B-9C72-5D1A0B7E3F41}
AppName=Loot Radar
AppVersion={#AppVersion}
AppVerName=Loot Radar {#AppVersion}
AppPublisher=solitary_samurai
AppPublisherURL=https://github.com/Winyshadow/loot-radar
AppSupportURL=https://github.com/Winyshadow/loot-radar
AppUpdatesURL=https://github.com/Winyshadow/loot-radar/releases
AppCopyright=(c) 2026 solitary_samurai. All rights reserved.
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Loot Radar setup
PrivilegesRequired=lowest
DefaultDirName={autopf}\Loot Radar
DefaultGroupName=Loot Radar
DisableProgramGroupPage=yes
DisableWelcomePage=no
DisableDirPage=auto
LicenseFile=..\LICENSE
OutputBaseFilename=LootRadarSetup
SetupIconFile=..\art\loot-radar.ico
UninstallDisplayIcon={app}\LootRadar.exe
UninstallDisplayName=Loot Radar
WizardStyle=modern
WizardImageFile={#WorkDir}\wizard-large-1.bmp,{#WorkDir}\wizard-large-2.bmp
WizardSmallImageFile={#WorkDir}\wizard-small-1.bmp,{#WorkDir}\wizard-small-2.bmp
Compression=lzma2/max
SolidCompression=yes
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Put a Loot Radar shortcut on the desktop"; Check: not WizardSilent
Name: "startup"; Description: "Start Loot Radar when I sign in to Windows (quietly in the tray)"; Check: not WizardSilent

[InstallDelete]
; an update replaces the whole program, so files an old version had don't linger
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#DistDir}\LootRadar\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Loot Radar"; Filename: "{app}\LootRadar.exe"
Name: "{autodesktop}\Loot Radar"; Filename: "{app}\LootRadar.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Loot Radar"; ValueData: """{app}\LootRadar.exe"" --no-browser"; Tasks: startup

[Run]
Filename: "{app}\LootRadar.exe"; Description: "Open Loot Radar now"; Flags: nowait postinstall skipifsilent
Filename: "{app}\LootRadar.exe"; Flags: nowait; Check: LaunchAfterSilent

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  ApprovedKey = 'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run';

function LaunchAfterSilent: Boolean;
begin
  { a silent update started by Loot Radar itself asks for the new version to be opened }
  Result := WizardSilent and (ExpandConstant('{param:LAUNCH|0}') = '1');
end;

procedure StopLootRadar;
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im LootRadar.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Sleep(800);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopLootRadar;  { a running copy would lock its own files }
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Data: String;
  Code: Integer;
begin
  if CurUninstallStep = usUninstall then
    StopLootRadar;
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKCU, RunKey, 'Loot Radar');
    RegDeleteValue(HKCU, ApprovedKey, 'Loot Radar');
    Data := ExpandConstant('{localappdata}\Loot Radar');
    if DirExists(Data) and not UninstallSilent then
      if MsgBox('Also delete your Loot Radar settings and the drop miner?' + #13#10#13#10 +
                'They are in ' + Data + #13#10 +
                'Choose No to keep them, so a later reinstall picks up where you left off.' + #13#10#13#10 +
                'Your Twitch login for the miner (in %APPDATA%\TwitchDropsMiner) is kept either way.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im TwitchDropsMiner.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
        Sleep(1500);
        DelTree(Data, True, True, True);
      end;
  end;
end;
