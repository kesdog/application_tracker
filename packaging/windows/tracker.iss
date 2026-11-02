#ifndef AppVersion
  #error AppVersion must be supplied by the version checker
#endif
#ifndef OutputName
  #error OutputName must be supplied by the packager
#endif
[Setup]
AppId={{5756E730-739F-4EE6-9257-23F555CFCE22}
AppName=Application Tracker
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\ApplicationTracker
DefaultGroupName=Application Tracker
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\.run
OutputBaseFilename={#OutputName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\ApplicationTracker.exe
; User databases and documents are outside {app}; never add an UninstallDelete rule.
[Files]
Source: "..\..\build\windows\ApplicationTracker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\Application Tracker"; Filename: "{app}\ApplicationTracker.exe"
Name: "{autodesktop}\Application Tracker"; Filename: "{app}\ApplicationTracker.exe"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Run]
Filename: "{app}\ApplicationTracker.exe"; Description: "Open Application Tracker"; Flags: nowait postinstall skipifsilent
