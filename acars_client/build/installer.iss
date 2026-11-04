; Inno Setup script for the PAC ACARS installer (https://jrsoftware.org/isinfo.php)
; Built by build_acars.bat after PyInstaller has produced dist\PAC ACARS\

#define AppName "PAC ACARS"
#define AppVersion "1.1.2"
#define Publisher "Pagani Air Cargo"

[Setup]
AppId={{0945C192-A719-4B31-A88D-929DE0688128}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=PAC-ACARS-Setup-{#AppVersion}
SetupIconFile=..\assets\pac-acars.ico
UninstallDisplayIcon={app}\PAC ACARS.exe
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\PAC ACARS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\PAC ACARS.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\PAC ACARS.exe"; Tasks: desktopicon

[Registry]
; pacacars:// links from the PAC website open PAC ACARS with the flight loaded
Root: HKCU; Subkey: "Software\Classes\pacacars"; ValueType: string; ValueName: ""; ValueData: "URL:PAC ACARS"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\pacacars"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\pacacars\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\PAC ACARS.exe"",0"
Root: HKCU; Subkey: "Software\Classes\pacacars\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PAC ACARS.exe"" ""%1"""

[Run]
Filename: "{app}\PAC ACARS.exe"; Description: "Start PAC ACARS"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; settings and logs in %APPDATA%\PAC ACARS are kept, so a reinstall remembers your setup

[Code]
// In-app updates run this installer silently while PAC ACARS is closing. Make sure it has really
// closed (its files can't be replaced while it runs), then give Windows a moment to release them.
function InitializeSetup(): Boolean;
var
  Code: Integer;
begin
  if WizardSilent() then
  begin
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM "PAC ACARS.exe"', '', SW_HIDE, ewWaitUntilTerminated, Code);
    Sleep(1500);
  end;
  Result := True;
end;
