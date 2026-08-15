; ========================================================
; Chaqimchi AI - Professional Windows Installer (Inno Setup 6)
; ========================================================

#define MyAppName "Chaqimchi AI"
#define MyAppVersion "0.7.0"
#define MyAppPublisher "Chaqimchi AI Team"
#define MyAppURL "https://chaqimchi.uz"
#define MyAppExeName "run_windows.bat"

[Setup]
AppId={{D8281F25-B47C-4C41-9507-68789C19904A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=Chaqimchi_AI_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Languages]
Name: "uz"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Kompyuter yoqilganda avtomatik ishga tushish"; GroupDescription: "Avtomatik boshlash:"

[Files]
Source: "..\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\scripts\install_windows.bat"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements-cloud.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\chaqimchi_ai\*"; DestDir: "{app}\chaqimchi_ai"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\cloud\*"; DestDir: "{app}\cloud"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\config\*"; DestDir: "{app}\config"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\webapp\*"; DestDir: "{app}\webapp"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; 1. Paketlarni o'rnatish
Filename: "{app}\scripts\install_windows.bat"; Description: "Python muhiti va kutubxonalarni o'rnatish"; Flags: waituntilterminated runhidden
; 2. Firewall ruxsati
Filename: "netsh.exe"; Parameters: "advfirewall firewall add rule name=""Chaqimchi AI"" dir=in action=allow protocol=TCP localport=8750"; Flags: runhidden
; 3. Dasturni ishga tushirish
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Chaqimchi AI"""; Flags: runhidden
