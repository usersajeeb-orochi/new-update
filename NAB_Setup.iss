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
; Microsoft's small WebView2 runtime installer: NAB needs it for its own window and for the overlay. Only run when it is missing.
Source: "build_output\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedWebView2
Source: "build_output\NAB\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\NAB_Launcher.exe"; IconFilename: "{app}\NAB.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\NAB_Launcher.exe"; IconFilename: "{app}\NAB.exe"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing the Microsoft WebView2 runtime (needed for the NAB window)..."; Flags: waituntilterminated runhidden; Check: NeedWebView2
Filename: "{app}\NAB_Launcher.exe"; Description: "Start NAB"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\_old"
Type: filesandordirs; Name: "{app}\_update"

[Code]
function HasWV2(Root: Integer; Key: String): Boolean;
var V: String;
begin
  Result := RegQueryStringValue(Root, Key, 'pv', V) and (V <> '') and (V <> '0.0.0.0');
end;

function NeedWebView2: Boolean;
begin
  Result := not (HasWV2(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}')
             or HasWV2(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}')
             or HasWV2(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'));
end;
