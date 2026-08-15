; ========================================================
; Chaqimchi AI - Professional Windows Installer (Inno Setup 6)
; Standalone Windows App (.exe) o'rnatuvchi
; ========================================================

#define MyAppName "Chaqimchi AI"
#define MyAppVersion "0.7.0"
#define MyAppPublisher "Chaqimchi AI"
#define MyAppURL "https://chaqimchi.uz"
#define MyAppExeName "ChaqimchiAI.exe"

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
OutputDir=..\releases
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
Name: "desktopicon"; Description: "Ish stolida yorliq yaratish (Desktop Shortcut)"; GroupDescription: "Qo‘shimcha belgilar:"
Name: "autostart"; Description: "Kompyuter yoqilganda avtomatik ishga tushish"; GroupDescription: "Avtomatik boshlash:"

[Files]
; Standalone PyInstaller bundle fayllari
Source: "..\dist\ChaqimchiAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; 1. Windows Firewall ruxsati (Lokal tarmoqdagi kameralarni qidirish uchun)
Filename: "netsh.exe"; Parameters: "advfirewall firewall add rule name=""Chaqimchi AI"" dir=in action=allow protocol=TCP localport=8750"; Flags: runhidden
; 2. Dasturni ishga tushirish
Filename: "{app}\{#MyAppExeName}"; Description: "Chaqimchi AI ni hozir ishga tushirish"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Chaqimchi AI"""; Flags: runhidden
