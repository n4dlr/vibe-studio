; ===============================================================================
; J.A.R.V.I.S — Inno Setup Installer Script for Windows x64
; Produces: JARVIS-Setup-x64.exe
; Target: C:\Program Files\JARVIS\ or %LOCALAPPDATA%\Programs\JARVIS\
; ===============================================================================

#define MyAppName "JARVIS"
#define MyAppDisplayName "J.A.R.V.I.S — Autonomous OS"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Vibe Studio"
#define MyAppURL "https://github.com/n4dlr/vibe-studio"
#define MyAppExeName "jarvis.exe"
#define SourceDir "..\..\..\dist\jarvis"

[Setup]
AppId={{E8B763F2-9981-4FA4-94F1-71BE40526B4A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppDisplayName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableDirPage=no
DefaultGroupName={#MyAppDisplayName}
DisableProgramGroupPage=no
LicenseFile=..\..\..\LICENSE
InfoBeforeFile=..\..\..\THIRD_PARTY_NOTICES
OutputDir=..\..\..\dist
OutputBaseFilename=JARVIS-Setup-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Launch J.A.R.V.I.S automatically on Windows startup"; GroupDescription: "Startup Options:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\..\models\*"; DestDir: "{app}\models"; Flags: ignoreversion recursesubdirs createallsubdirs; Permissions: users-readexec
Source: "..\..\..\THIRD_PARTY_NOTICES"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Diagnostics (Doctor)"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--doctor"
Name: "{group}\Interactive CLI"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--cli"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppDisplayName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppDisplayName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only delete runtime caches and logs, preserve user configuration & models
Type: files; Name: "{app}\*.log"
Type: dirifempty; Name: "{app}"
