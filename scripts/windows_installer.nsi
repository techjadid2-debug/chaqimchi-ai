; ========================================================
; Chaqimchi AI — Rasmiy Windows NSIS Installer
; ========================================================

!include "MUI2.nsh"
!include "FileFunc.nsh"

; Dastur ma'lumotlari
Name "Chaqimchi AI"
OutFile "..\releases\Chaqimchi_AI_Setup.exe"
Unicode True
RequestExecutionLevel admin
InstallDir "$PROGRAMFILES64\Chaqimchi AI"
InstallDirRegKey HKLM "Software\Chaqimchi AI" "Install_Dir"

; Modern UI Sozlamalari & Chaqimchi Logotipi
!define MUI_ABORTWARNING
!define MUI_ICON "app.ico"
!define MUI_UNICON "app.ico"
!define MUI_HEADERIMAGE
!define MUI_WELCOMEFINISHPAGE_BITMAP "${NSISDIR}\Contrib\Graphics\Wizard\win.bmp"

; Sahifalar
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

; Yakuniy sahifa: Dasturni ishga tushirish
!define MUI_FINISHPAGE_RUN "$INSTDIR\scripts\run_windows.bat"
!define MUI_FINISHPAGE_RUN_TEXT "Chaqimchi AI ni hozir ishga tushirish"
!insertmacro MUI_PAGE_FINISH


; O'chirish sahifalari
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Tillar
!insertmacro MUI_LANGUAGE "English"

; O'rnatish bo'limi
Section "Chaqimchi AI Asosiy Fayllar" SecMain
    SetOutPath "$INSTDIR"

    ; Asosiy skriptlar, ikonkalar va konfiguratsiyalar
    File "app.ico"
    File "..\requirements.txt"
    File "..\requirements-cloud.txt"

    ; Papkalarni nusxalash
    SetOutPath "$INSTDIR\scripts"
    File /r "..\scripts\*.*"

    SetOutPath "$INSTDIR\chaqimchi_ai"
    File /r "..\chaqimchi_ai\*.*"

    SetOutPath "$INSTDIR\cloud"
    File /r "..\cloud\*.*"

    SetOutPath "$INSTDIR\config"
    File /r "..\config\*.*"

    SetOutPath "$INSTDIR\webapp"
    File /r "..\webapp\*.*"

    ; Firewall ruxsatini qo'shish
    ExecWait 'netsh advfirewall firewall add rule name="Chaqimchi AI" dir=in action=allow protocol=TCP localport=8750'

    ; Uninstaller yaratish
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; 1. Barcha foydalanuvchilar (All Users) ish stoliga yorliq
    SetShellVarContext all
    CreateDirectory "$SMPROGRAMS\Chaqimchi AI"
    CreateShortcut "$SMPROGRAMS\Chaqimchi AI\Chaqimchi AI.lnk" "$WINDIR\System32\wscript.exe" '"$INSTDIR\scripts\ChaqimchiAI.vbs"' "$INSTDIR\app.ico" 0
    CreateShortcut "$SMPROGRAMS\Chaqimchi AI\O'chirish (Uninstall).lnk" "$INSTDIR\Uninstall.exe" "" "$INSTDIR\Uninstall.exe" 0
    CreateShortcut "$DESKTOP\Chaqimchi AI.lnk" "$WINDIR\System32\wscript.exe" '"$INSTDIR\scripts\ChaqimchiAI.vbs"' "$INSTDIR\app.ico" 0

    ; 2. Joriy foydalanuvchi (Current User) ish stoliga ham kafolatlangan yorliq
    SetShellVarContext current
    CreateDirectory "$SMPROGRAMS\Chaqimchi AI"
    CreateShortcut "$SMPROGRAMS\Chaqimchi AI\Chaqimchi AI.lnk" "$WINDIR\System32\wscript.exe" '"$INSTDIR\scripts\ChaqimchiAI.vbs"' "$INSTDIR\app.ico" 0
    CreateShortcut "$DESKTOP\Chaqimchi AI.lnk" "$WINDIR\System32\wscript.exe" '"$INSTDIR\scripts\ChaqimchiAI.vbs"' "$INSTDIR\app.ico" 0

    ; Windows Registry
    WriteRegStr HKLM "Software\Chaqimchi AI" "Install_Dir" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Chaqimchi AI" "DisplayName" "Chaqimchi AI - Do'kon Analitikasi"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Chaqimchi AI" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Chaqimchi AI" "DisplayIcon" "$INSTDIR\app.ico"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Chaqimchi AI" "DisplayVersion" "0.7.0"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Chaqimchi AI" "Publisher" "Chaqimchi AI"
SectionEnd

; O'chirish bo'limi
Section "Uninstall"
    ; Firewall ruxsatini o'chirish
    ExecWait 'netsh advfirewall firewall delete rule name="Chaqimchi AI"'

    ; Yorliqlarni o'chirish
    SetShellVarContext all
    Delete "$DESKTOP\Chaqimchi AI.lnk"
    Delete "$SMPROGRAMS\Chaqimchi AI\Chaqimchi AI.lnk"
    Delete "$SMPROGRAMS\Chaqimchi AI\O'chirish (Uninstall).lnk"
    RMDir "$SMPROGRAMS\Chaqimchi AI"

    SetShellVarContext current
    Delete "$DESKTOP\Chaqimchi AI.lnk"
    Delete "$SMPROGRAMS\Chaqimchi AI\Chaqimchi AI.lnk"
    RMDir "$SMPROGRAMS\Chaqimchi AI"

    ; Fayllarni o'chirish
    RMDir /r "$INSTDIR\chaqimchi_ai"
    RMDir /r "$INSTDIR\cloud"
    RMDir /r "$INSTDIR\config"
    RMDir /r "$INSTDIR\scripts"
    RMDir /r "$INSTDIR\webapp"
    Delete "$INSTDIR\app.ico"
    Delete "$INSTDIR\requirements.txt"
    Delete "$INSTDIR\requirements-cloud.txt"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"

    ; Registryni tozalash
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Chaqimchi AI"
    DeleteRegKey HKLM "Software\Chaqimchi AI"
SectionEnd
