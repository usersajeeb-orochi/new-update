; Inno Setup 6 script - builds NAB_Setup.exe from build_output\NAB
; Per-user install (no administrator needed) so the auto-updater can write to the folder.
#define AppName "News Automation Bot"
#ifndef AppVer
#define AppVer  "3.0.34"
#endif

[Setup]
AppId={{6C1E3E3B-4B64-4D0B-9A53-2D6F7A9B5E11}
AppName={#AppName}
AppVersion={#AppVer}
AppPublisher=NAB
DefaultDirName={localappdata}\Programs\NAB
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=build_output
OutputBaseFilename=NAB_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\NAB.exe
SetupIconFile=app_icon.ico
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: checkedonce

[Files]
Source: "build_output\NAB\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\NAB_Launcher.exe"; IconFilename: "{app}\NAB.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\NAB_Launcher.exe"; IconFilename: "{app}\NAB.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\NAB_Launcher.exe"; Description: "Start NAB"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\_old"
Type: filesandordirs; Name: "{app}\_update"
