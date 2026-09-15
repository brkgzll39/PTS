; PTS Windows installer definition for Inno Setup 6
#define MyAppName "SPY PTS"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "SPY PTS"
#define MyAppExeName "calistir.bat"

[Setup]
AppId={{B9E93E1D-95C2-4F3F-8E0A-PTS2026}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\SPY PTS
DefaultGroupName={#MyAppName}
OutputDir=output
OutputBaseFilename=SPY-PTS-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\backend\*"; DestDir: "{app}\backend"; Flags: recursesubdirs ignoreversion; Excludes: "__pycache__\*,*.pyc,license.json,cameras.json,config.json,database_config.json"
Source: "..\frontend\*"; DestDir: "{app}\frontend"; Flags: recursesubdirs ignoreversion
Source: "..\calistir.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\kurulum.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\veritabani\"; DestDir: "{app}\veritabani"; Flags: recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist
Source: "..\goruntuler\"; DestDir: "{app}\goruntuler"; Flags: recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist
Source: "..\disa_aktarilanlar\"; DestDir: "{app}\disa_aktarilanlar"; Flags: recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\SPY PTS"; Filename: "{app}\calistir.bat"; WorkingDir: "{app}"
Name: "{commondesktop}\SPY PTS"; Filename: "{app}\calistir.bat"; WorkingDir: "{app}"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\backend\__pycache__"

[Run]
Filename: "{app}\kurulum.bat"; Description: "PTS Python ortamını ve bağımlılıklarını kur"; Flags: postinstall waituntilterminated
Filename: "{app}\calistir.bat"; Description: "PTS'yi başlat"; Flags: postinstall nowait skipifsilent
