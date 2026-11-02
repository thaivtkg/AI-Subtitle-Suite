[Setup]
AppId={{9A2B4C6D-1234-5678-90AB-CDEF12345678}
AppName=AI Subtitle Suite
AppVersion=1.0.0
AppPublisher=ThaiVTKG
DefaultDirName={autopf}\AI Subtitle Suite
DefaultGroupName=AI Subtitle Suite
UninstallDisplayIcon={app}\AI Subtitle Suite.exe
SetupIconFile=resources\app_icon.ico
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
OutputDir=dist
OutputBaseFilename=AI_Subtitle_Suite_Setup_v1.0.0
InfoBeforeFile=RELEASE_NOTES.txt

[Files]
Source: "dist\AI Subtitle Suite\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AI Subtitle Suite"; Filename: "{app}\AI Subtitle Suite.exe"
Name: "{autodesktop}\AI Subtitle Suite"; Filename: "{app}\AI Subtitle Suite.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Run]
Filename: "{app}\AI Subtitle Suite.exe"; Description: "{cm:LaunchProgram,AI Subtitle Suite}"; Flags: nowait postinstall skipifsilent
