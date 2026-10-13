; Unsigned, per-user installation. Uninstall never deletes user data.
[Setup]
AppId={{7CBBAED2-EF1B-48DD-A2B0-2C7E260B6B88}
AppName=FIRMAVEX Desktop
AppVersion=0.3.0-dev1
DefaultDirName={localappdata}\Programs\FIRMAVEX
DefaultGroupName=FIRMAVEX
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=FIRMAVEX-Windows-unsigned
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\FIRMAVEX-Desktop.exe
[Files]
Source: "..\dist\FIRMAVEX\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
[Icons]
Name: "{group}\FIRMAVEX Desktop"; Filename: "{app}\FIRMAVEX-Desktop.exe"
Name: "{userdesktop}\FIRMAVEX Desktop"; Filename: "{app}\FIRMAVEX-Desktop.exe"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
