; ============================================================================
; Chaqimchi AI — Windows o'rnatuvchisi
;
; Mijoz ko'radigan oqim:
;   Chaqimchi_AI_Setup.exe → "Ha, ruxsat beraman" (UAC)
;   → Keyingi → Keyingi → O'rnatish → Tayyor → brauzer o'zi ochiladi
;
; Ichida hamma narsa bor (Python, AI modeli, kutubxonalar) — mijoz
; kompyuterida internet ham, `pip` ham kerak emas.
;
; Qurish:
;   python scripts/build_windows_payload.py
;   makensis scripts/windows_installer.nsi
;
; Oldingi versiyadan farqlar va nima uchun:
;
;   * Dastur va ma'lumot AJRATILDI.  Ilgari `run_windows.bat` `Program Files`
;     ichiga `.venv`, `data\` va `install.log` yozmoqchi bo'lardi — u yerda
;     oddiy foydalanuvchida yozish huquqi yo'q, ya'ni dastur birinchi ishga
;     tushishdayoq jimgina yiqilardi.  Endi yoziladigan hamma narsa
;     `C:\ProgramData\Chaqimchi` da.
;   * Yorliq YASHIRIN emas.  Ilgari `.vbs` oynani berkitardi va xato
;     ekranga chiqmasdi — mijoz nima bo'lganini bilmasdi.
;   * FIREWALL qoidasi yo'q.  Dastur faqat `127.0.0.1` da tinglaydi;
;     ilgari 8750 port butun tarmoq uchun ochilardi.
;   * AVTOSTART bor.  Do'kon kompyuteri o'chib yonsa nazorat o'zi tiklanadi.
;   * O'CHIRISH to'liq tozalaydi va ma'lumotni saqlashni so'raydi.
; ============================================================================

Unicode True

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

!define APP_NAME     "Chaqimchi AI"
!define APP_VERSION  "0.7.0"
!define APP_PUBLISHER "Chaqimchi AI"
!define APP_PORT     "8760"
!define APP_URL      "http://localhost:${APP_PORT}"
!define REG_UNINSTALL "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChaqimchiAI"
!define REG_RUN      "Software\Microsoft\Windows\CurrentVersion\Run"

Name "${APP_NAME}"
OutFile "..\releases\Chaqimchi_AI_Setup.exe"
InstallDir "$PROGRAMFILES64\Chaqimchi AI"
InstallDirRegKey HKLM "Software\ChaqimchiAI" "InstallDir"

; Dastur `Program Files` ga yozadi va avtostart registrini qo'yadi —
; administrator huquqi kerak.  Windows buni UAC oynasi bilan so'raydi.
RequestExecutionLevel admin

; Payload ~300 MB.  Solid LZMA fayl hajmini taxminan ikki barobar kichraytiradi;
; qurish sekinroq bo'ladi, lekin mijoz kamroq yuklab oladi.
SetCompressor /SOLID lzma
SetCompressorDictSize 64

VIProductVersion "0.7.0.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "FileDescription" "${APP_NAME} o'rnatuvchisi"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "CompanyName" "${APP_PUBLISHER}"
VIAddVersionKey "LegalCopyright" "© ${APP_PUBLISHER}"

; ── Ko'rinish ───────────────────────────────────────────────────────────
!define MUI_ABORTWARNING
!define MUI_ICON "app.ico"
!define MUI_UNICON "app.ico"
!define MUI_HEADERIMAGE
!define MUI_WELCOMEFINISHPAGE_BITMAP "${NSISDIR}\Contrib\Graphics\Wizard\win.bmp"

!define MUI_WELCOMEPAGE_TITLE "${APP_NAME} o'rnatilmoqda"
!define MUI_WELCOMEPAGE_TEXT "Bu dastur do'koningizdagi kameralarni sun'iy intellekt bilan tahlil qiladi: mijozlar soni, kassa navbati va xavfsizlik.$\r$\n$\r$\nO'rnatish uchun qo'shimcha hech narsa kerak emas — Python va AI modeli shu paketning ichida.$\r$\n$\r$\nDavom etish uchun 'Keyingi' ni bosing."

; Oxirgi sahifada dasturni ochish — mijoz yorliq qidirib yurmasin.
!define MUI_FINISHPAGE_RUN "$INSTDIR\Chaqimchi_AI.bat"
!define MUI_FINISHPAGE_RUN_TEXT "${APP_NAME} ni hozir ishga tushirish"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\O'QING.txt"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Qisqacha yo'riqnomani o'qish"
!define MUI_FINISHPAGE_SHOWREADME_NOTCHECKED
!define MUI_FINISHPAGE_TEXT "${APP_NAME} o'rnatildi.$\r$\n$\r$\nIshga tushirgach brauzerda sozlash oynasi ochiladi: ${APP_URL}$\r$\n$\r$\nU yerda kamerangizni ulaysiz va kirish chizig'ini chizasiz."

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; O'zbek tili birinchi: mijoz shu tilda o'qiydi.  Ingliz tili zaxira
; sifatida qoladi — ba'zi Windows nusxalarida o'zbekcha shrift muammosi
; bo'lishi mumkin.
!insertmacro MUI_LANGUAGE "Uzbek"
!insertmacro MUI_LANGUAGE "English"

; ── Asosiy bo'lim ───────────────────────────────────────────────────────

Section "!${APP_NAME} (majburiy)" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"

  ; Payload — `build_windows_payload.py` yig'gan papka.  Ichida Python,
  ; oldindan o'rnatilgan kutubxonalar, AI modeli va dastur kodi bor.
  File /r "..\build\payload\*.*"

  ; Yorliqlar hamma foydalanuvchi uchun: do'konda kassir boshqa hisobdan
  ; kirsa ham dasturni topa olishi kerak.
  SetShellVarContext all

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\Chaqimchi_AI.bat" "" "$INSTDIR\app.ico" 0
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\Boshqaruv paneli.lnk" "${APP_URL}" "" "$INSTDIR\app.ico" 0
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME} ni o'chirish.lnk" "$INSTDIR\Uninstall.exe" "" "$INSTDIR\Uninstall.exe" 0

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  WriteRegStr HKLM "Software\ChaqimchiAI" "InstallDir" "$INSTDIR"
  WriteRegStr HKLM "${REG_UNINSTALL}" "DisplayName" "${APP_NAME} — do'kon nazorati"
  WriteRegStr HKLM "${REG_UNINSTALL}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "${REG_UNINSTALL}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegStr HKLM "${REG_UNINSTALL}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${REG_UNINSTALL}" "DisplayIcon" "$INSTDIR\app.ico"
  WriteRegStr HKLM "${REG_UNINSTALL}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "${REG_UNINSTALL}" "Publisher" "${APP_PUBLISHER}"
  WriteRegDWORD HKLM "${REG_UNINSTALL}" "NoModify" 1
  WriteRegDWORD HKLM "${REG_UNINSTALL}" "NoRepair" 1

  ; "Dasturlar va komponentlar" ro'yxatida hajmni ko'rsatish uchun.
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKLM "${REG_UNINSTALL}" "EstimatedSize" "$0"
SectionEnd

Section "Ish stoliga yorliq" SecDesktop
  SetShellVarContext all
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\Chaqimchi_AI.bat" "" "$INSTDIR\app.ico" 0
SectionEnd

Section "Kompyuter yonganda avtomatik ishga tushsin" SecAutostart
  ; Do'kon kompyuteri kechqurun o'chirilib ertalab yoqiladi.  Avtostartsiz
  ; nazorat jimgina to'xtab qolardi va buni faqat hisobot bo'sh chiqqanda
  ; sezishardi.
  WriteRegStr HKLM "${REG_RUN}" "ChaqimchiAI" '"$INSTDIR\Chaqimchi_AI.bat"'
SectionEnd

Section "Yangilanishlarni o'zi olsin" SecUpdater
  ; Nega rejalashtirilgan vazifa, oddiy avtostart emas: yangilash
  ; `Program Files` ga yozadi va administrator huquqini talab qiladi.
  ; Dastur esa oddiy foydalanuvchi huquqi bilan ishlaydi va o'zini
  ; eleva qila olmaydi — har safar ruxsat oynasi chiqardi.
  ;
  ; Vazifa hozir (o'rnatuvchi administrator bo'lgan paytda) SYSTEM
  ; nomiga yoziladi, keyin esa hech qanday oyna chiqarmasdan ishlaydi.
  ; Bu o'rnatuvchi do'kondan ketgandan keyin ham yangilash imkonini beradi.
  ;
  ; Xavfsizlik: yangilovchi paketni Ed25519 imzosi bilan tekshiradi
  ; (`chaqimchi_ai/local/updater.py`).  Imzo mos kelmasa paket tashlanadi.
  DetailPrint "Yangilanish vazifasi qo'shilmoqda..."
  nsExec::ExecToLog 'schtasks /Create /F /TN "Chaqimchi AI Update" \
    /TR "\"$INSTDIR\python\python.exe\" -m chaqimchi_ai.local.updater" \
    /SC HOURLY /MO 6 /RU SYSTEM /RL HIGHEST'
  Pop $0
  ${If} $0 != 0
    DetailPrint "Ogohlantirish: avtomatik yangilanish sozlanmadi (kod $0)."
    DetailPrint "Dastur ishlaydi; yangilanishni qo'lda o'rnatasiz."
  ${EndIf}
SectionEnd

; ── Bo'lim izohlari ─────────────────────────────────────────────────────

LangString DESC_SecMain ${LANG_UZBEK} "Dastur, Python muhiti va AI modeli. Internet talab qilinmaydi."
LangString DESC_SecDesktop ${LANG_UZBEK} "Ish stolida ${APP_NAME} yorlig'i bo'ladi."
LangString DESC_SecAutostart ${LANG_UZBEK} "Kompyuter yoqilganda nazorat o'zi ishga tushadi. Tavsiya etiladi."
LangString DESC_SecUpdater ${LANG_UZBEK} "Yangi versiyalar o'zi yuklanadi va o'rnatiladi. Faqat imzosi tekshirilgan paketlar qabul qilinadi."
LangString DESC_SecUpdater ${LANG_ENGLISH} "Downloads and installs new versions automatically. Only signature-verified packages are accepted."
LangString DESC_SecMain ${LANG_ENGLISH} "Application, Python runtime and AI model. No internet required."
LangString DESC_SecDesktop ${LANG_ENGLISH} "Adds a ${APP_NAME} shortcut to the desktop."
LangString DESC_SecAutostart ${LANG_ENGLISH} "Starts monitoring automatically when the computer boots."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} $(DESC_SecMain)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_SecDesktop)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAutostart} $(DESC_SecAutostart)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecUpdater} $(DESC_SecUpdater)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function .onInit
  ; Ilgari o'rnatilgan bo'lsa avval o'chirishni taklif qilamiz: eski
  ; `site-packages` ustiga yozilsa mos kelmaydigan versiyalar aralashib
  ; ketardi va sabab topib bo'lmaydigan xato chiqardi.
  ReadRegStr $R0 HKLM "${REG_UNINSTALL}" "UninstallString"
  ${If} $R0 != ""
    MessageBox MB_OKCANCEL|MB_ICONQUESTION \
      "${APP_NAME} allaqachon o'rnatilgan.$\r$\n$\r$\nYangilash uchun avval eski versiya o'chiriladi. Sozlamalaringiz va hisobotlaringiz saqlanib qoladi.$\r$\n$\r$\nDavom etamizmi?" \
      IDOK uninstall_old
    Abort
    uninstall_old:
      ExecWait '$R0 /S _?=$INSTDIR'
  ${EndIf}
FunctionEnd

; ── O'chirish ───────────────────────────────────────────────────────────

Section "Uninstall"
  ; Ishlab turgan dasturni to'xtatamiz, aks holda fayllar band bo'lib
  ; o'chmay qoladi va papka "yarim o'chirilgan" holatda qolardi.
  ExecWait 'taskkill /F /IM python.exe /FI "WINDOWTITLE eq Chaqimchi*"'

  ; Yangilanish vazifasi ham olib tashlanadi: qolib ketsa o'chirilgan
  ; dasturni har olti soatda qayta o'rnatishga urinardi.
  nsExec::ExecToLog 'schtasks /Delete /F /TN "Chaqimchi AI Update"'
  Pop $0

  DeleteRegValue HKLM "${REG_RUN}" "ChaqimchiAI"
  DeleteRegKey HKLM "${REG_UNINSTALL}"
  DeleteRegKey HKLM "Software\ChaqimchiAI"

  SetShellVarContext all
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\Boshqaruv paneli.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME} ni o'chirish.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"

  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\chaqimchi_ai"
  RMDir /r "$INSTDIR\config"
  RMDir /r "$INSTDIR\models"
  Delete "$INSTDIR\Chaqimchi_AI.bat"
  Delete "$INSTDIR\O'QING.txt"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\LICENSE"
  Delete "$INSTDIR\app.ico"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  ; Sozlama va hisobotlar alohida so'raladi.  Ularni so'ramasdan o'chirish
  ; xavfli: mijoz dasturni yangilamoqchi bo'lgan bo'lishi mumkin, kamera
  ; sozlamalari va do'kon statistikasi esa qaytarilmaydi.
  ;
  ; `/S` (jim) rejimda savol berilmaydi va ma'lumot SAQLANADI — yangilash
  ; aynan shu yo'ldan o'tadi (`.onInit` dagi `ExecWait ... /S`).
  IfSilent skip_data
  SetShellVarContext all
  MessageBox MB_YESNO|MB_ICONQUESTION \
    "Sozlamalar va do'kon hisobotlari ham o'chirilsinmi?$\r$\n$\r$\nYo'q — kamera sozlamalari saqlanadi (qayta o'rnatsangiz kerak bo'ladi).$\r$\nHa — hammasi butunlay o'chadi." \
    IDNO skip_data
  RMDir /r "$APPDATA\Chaqimchi"
  skip_data:
SectionEnd
