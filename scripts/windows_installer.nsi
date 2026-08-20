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

; Versiya `build_windows_payload.py` tomonidan yoziladi (manba —
; `chaqimchi_ai/__init__.py`).  Bu yerda qo'lda yozilmaydi: ilgari
; shunday edi va siljib ketgan — dastur 0.6.2, o'rnatuvchi esa "0.7.0"
; deb yozardi.  Nomuvofiqlik bir marta cheksiz yangilanish siklini
; keltirib chiqargan, chunki cloud va qurilma har xil raqam aytardi.
;
; Fayl yo'q bo'lsa kompilyatsiya ataylab to'xtaydi: bu payload
; qurilmaganini bildiradi va o'sha payloadsiz o'rnatuvchi baribir
; yaroqsiz bo'lardi.
!include "..\build\version.nsh"

!define APP_NAME     "Chaqimchi AI"
!define APP_PUBLISHER "Chaqimchi AI"
!define APP_PORT     "8760"
!define APP_URL      "http://localhost:${APP_PORT}"
!define REG_UNINSTALL "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChaqimchiAI"
!define REG_RUN      "Software\Microsoft\Windows\CurrentVersion\Run"

; Fayl nomidan olingan pairing kod.  NSIS o'zgaruvchini **ishlatilishidan
; oldin** e'lon qilishni talab qiladi, shuning uchun bu yerda.
Var PairingCode

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

VIProductVersion "${APP_VERSION_NUMERIC}"
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

  ; ── Pairing kodni fayl nomidan olish ────────────────────────────────
  ;
  ; Admin panel `...?code=A1B2C3` havolasini beradi va brauzer faylni
  ; `Chaqimchi_AI_Setup-A1B2C3.exe` nomi bilan saqlaydi.  Kodni
  ; `%PROGRAMDATA%\Chaqimchi\pairing.txt` ga yozamiz — dastur birinchi
  ; ishga tushishda uni o'qib cloudga o'zi ulanadi va faylni o'chiradi.
  ;
  ; Nom buzilsa (brauzer `(1)` qo'shsa yoki mijoz faylni qayta nomlasa)
  ; hech narsa yozilmaydi va sehrgar kodni odatdagidek so'raydi.
  ; Ya'ni bu qulaylik, majburiyat emas.
  Call ExtractPairingCode
  ${If} $PairingCode != ""
    CreateDirectory "$APPDATA\Chaqimchi"
    FileOpen $0 "$APPDATA\Chaqimchi\pairing.txt" w
    FileWrite $0 "$PairingCode"
    FileClose $0
    DetailPrint "Ulanish kodi topildi: $PairingCode"
  ${EndIf}

  ; ── Ma'lumotlar papkasi ruxsatlari ──────────────────────────────────
  ;
  ; `%PROGRAMDATA%` standart holda hamma lokal user'ga o'qish beradi —
  ; ya'ni config.yaml ichidagi qurilma tokeni va NVR RTSP parollarini
  ; istalgan hisob o'qiy olardi.  Meros ruxsatlarni uzamiz va faqat
  ; SYSTEM, Administrators hamda **interaktiv** kirgan user'ga beramiz
  ; (panel user sessiyasida ishlaydi — usiz dastur ochilmay qolardi).
  ; SID'lar ataylab: guruh nomlari tildan tilga o'zgaradi (ruscha
  ; Windows'da "Administrators" yo'q), SID esa hamma joyda bir xil.
  ;   S-1-5-18 = SYSTEM, S-1-5-32-544 = Administrators, S-1-5-4 = INTERACTIVE
  CreateDirectory "$APPDATA\Chaqimchi"
  DetailPrint "Sozlamalar papkasi himoyalanmoqda..."
  nsExec::ExecToLog 'icacls "$APPDATA\Chaqimchi" /inheritance:r \
    /grant:r "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-4:(OI)(CI)M"'
  Pop $0
  ${If} $0 != 0
    DetailPrint "Ogohlantirish: papka ruxsatlari toraytirilmadi (kod $0)."
  ${EndIf}

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

Section "Kameralarni avtomatik topish (tarmoq ruxsati)" SecFirewall
  ; Kameralarni topish ONVIF WS-Discovery ga tayanadi: dastur
  ; 239.255.255.250:3702 ga UDP so'rov yuboradi va kameralar unga
  ; **javob** qaytaradi.
  ;
  ; Muammo shundaki, Windows Fayrvoli multicast so'roviga kelgan
  ; javobni faqat qisqa vaqt oynasida o'tkazadi, undan keyin jimgina
  ; tashlab yuboradi.  Natijada "Kameralarni topish" tugmasi hech
  ; qanday xato bermasdan bo'sh ro'yxat qaytarardi — mijoz uchun bu
  ; eng tushunarsiz holat.
  ;
  ; Ruxsat faqat **lokal tarmoq** bilan cheklangan: internetdan hech
  ; kim bu portga ulana olmaydi.
  ;
  ; MUHIM: localport ko'rsatilmaydi — dastur so'rovni tasodifiy
  ; (ephemeral) portdan yuboradi va kameraning javobi ham o'sha portga
  ; keladi.  Ilgari qoida localport=3702 bilan edi, ya'ni haqiqiy javob
  ; portiga umuman mos kelmasdi va tugma baribir bo'sh ro'yxat qaytarardi.
  DetailPrint "Kamera qidiruvi uchun tarmoq ruxsati..."
  nsExec::ExecToLog 'netsh advfirewall firewall add rule \
    name="Chaqimchi AI — kamera qidiruvi" dir=in action=allow \
    protocol=UDP profile=private,domain \
    remoteip=localsubnet program="$INSTDIR\python\python.exe"'
  Pop $0
  ${If} $0 != 0
    DetailPrint "Ogohlantirish: tarmoq ruxsati qo'shilmadi (kod $0)."
    DetailPrint "Kameralarni qo'lda IP manzili bilan qo'shishingiz mumkin."
  ${EndIf}
SectionEnd

Section "Ish stoliga yorliq" SecDesktop
  SetShellVarContext all
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\Chaqimchi_AI.bat" "" "$INSTDIR\app.ico" 0
SectionEnd

Section "Kompyuter yonganda avtomatik ishga tushsin" SecAutostart
  ; Do'kon kompyuteri kechqurun o'chirilib ertalab yoqiladi.  Avtostartsiz
  ; nazorat jimgina to'xtab qolardi va buni faqat hisobot bo'sh chiqqanda
  ; sezishardi.
  ;
  ; Ilgari bu `HKLM\...\Run` kaliti edi.  Uning ikkita jiddiy kamchiligi
  ; bor edi va ikkalasi ham do'konda haqiqatan uchraydi:
  ;
  ;   1. Run kaliti kompyuter YONGANDA emas, kimdir tizimga KIRGANDA
  ;      ishlaydi.  Do'kon kompyuteri yonib qulf ekranida tursa (masalan
  ;      kechasi elektr uzilib qayta kelgan bo'lsa) nazorat umuman
  ;      boshlanmasdi.
  ;   2. Dastur kassirning ekranida qora oyna bo'lib turardi.  "Bu oynani
  ;      YOPMANG" yozuviga qaramay u yopiladi.
  ;
  ; Rejalashtirilgan vazifa ikkalasini ham yopadi: SYSTEM nomidan, kirishdan
  ; qat'i nazar, ko'rinmas holda ishlaydi.
  DetailPrint "Avtomatik ishga tushirish vazifasi..."
  nsExec::ExecToLog 'schtasks /Create /F /TN "Chaqimchi AI" \
    /TR "\"$INSTDIR\Chaqimchi_AI_xizmat.bat\"" \
    /SC ONSTART /DELAY 0000:30 /RU SYSTEM /RL HIGHEST'
  Pop $0
  ${If} $0 != 0
    ; Zaxira yo'l: vazifa yaratilmasa hech bo'lmasa eski usul ishlasin.
    DetailPrint "Ogohlantirish: vazifa qo'shilmadi (kod $0)."
    DetailPrint "Eski usul ishlatiladi: dastur tizimga kirgandan keyin ochiladi."
    WriteRegStr HKLM "${REG_RUN}" "ChaqimchiAI" '"$INSTDIR\Chaqimchi_AI.bat"'
  ${Else}
    ; `schtasks` yaratgan vazifa standart bo'yicha 72 soatdan keyin
    ; TO'XTATILADI (`ExecutionTimeLimit=PT72H`).  24/7 nazorat uchun bu
    ; jimgina o'chish degani — va aynan 72 soatlik barqarorlik sinovining
    ; oxirida.  Cheklovni olib tashlaymiz va yiqilsa qayta ko'tarilsin.
    DetailPrint "Vazifa sozlanmoqda (vaqt cheklovisiz, qayta ko'tarish bilan)..."
    nsExec::ExecToLog "powershell -NoProfile -ExecutionPolicy Bypass -Command $\"$$t = Get-ScheduledTask -TaskName 'Chaqimchi AI'; $$t.Settings.ExecutionTimeLimit = 'PT0S'; $$t.Settings.RestartCount = 3; $$t.Settings.RestartInterval = 'PT1M'; $$t.Settings.DisallowStartIfOnBatteries = $$false; $$t.Settings.StopIfGoingOnBatteries = $$false; Set-ScheduledTask -InputObject $$t | Out-Null$\""
    Pop $0
    ${If} $0 != 0
      DetailPrint "Ogohlantirish: vazifa sozlamalari o'zgartirilmadi (kod $0)."
      DetailPrint "Dastur ishlaydi, lekin 72 soatdan keyin qayta yoqish kerak bo'lishi mumkin."
    ${EndIf}
    ; Vazifani hoziroq ishga tushiramiz — mijoz kompyuterni qayta
    ; yoqmasdan ham nazorat boshlansin.
    nsExec::ExecToLog 'schtasks /Run /TN "Chaqimchi AI"'
    Pop $0
  ${EndIf}
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
  ;
  ; Nega 15 daqiqa (ilgari 6 soat edi): admin paneldan yangilanish
  ; buyurilgach uni olti soat kutish amalda "masofadan boshqarish yo'q"
  ; degani edi — o'rnatuvchi do'konda o'tirib kutolmaydi.
  ;
  ; Narxi deyarli nol: ulanmagan qurilmada tekshiruv tarmoqqa umuman
  ; chiqmaydi (`updater._cloud()` darhol to'xtaydi), ulangan qurilmada
  ; esa bu bitta kichik HTTPS so'rovi.  Yuklab olish faqat haqiqatan
  ; yangi versiya bo'lganda boshlanadi.
  DetailPrint "Yangilanish vazifasi qo'shilmoqda..."
  nsExec::ExecToLog 'schtasks /Create /F /TN "Chaqimchi AI Update" \
    /TR "\"$INSTDIR\python\python.exe\" -m chaqimchi_ai.local.updater" \
    /SC MINUTE /MO 15 /RU SYSTEM /RL HIGHEST'
  Pop $0
  ${If} $0 != 0
    DetailPrint "Ogohlantirish: avtomatik yangilanish sozlanmadi (kod $0)."
    DetailPrint "Dastur ishlaydi; yangilanishni qo'lda o'rnatasiz."
  ${EndIf}
SectionEnd

; ── Bo'lim izohlari ─────────────────────────────────────────────────────

LangString DESC_SecMain ${LANG_UZBEK} "Dastur, Python muhiti va AI modeli. Internet talab qilinmaydi."
LangString DESC_SecFirewall ${LANG_UZBEK} "Kameralarni tarmoqdan avtomatik topish uchun ruxsat. Faqat lokal tarmoq, internetdan kirish yo'q."
LangString DESC_SecFirewall ${LANG_ENGLISH} "Allows automatic camera discovery on the local network. Local subnet only; no access from the internet."
LangString DESC_SecDesktop ${LANG_UZBEK} "Ish stolida ${APP_NAME} yorlig'i bo'ladi."
LangString DESC_SecAutostart ${LANG_UZBEK} "Kompyuter yoqilganda nazorat o'zi ishga tushadi. Tavsiya etiladi."
LangString DESC_SecUpdater ${LANG_UZBEK} "Yangi versiyalar o'zi yuklanadi va o'rnatiladi. Faqat imzosi tekshirilgan paketlar qabul qilinadi."
LangString DESC_SecUpdater ${LANG_ENGLISH} "Downloads and installs new versions automatically. Only signature-verified packages are accepted."
LangString DESC_SecMain ${LANG_ENGLISH} "Application, Python runtime and AI model. No internet required."
LangString DESC_SecDesktop ${LANG_ENGLISH} "Adds a ${APP_NAME} shortcut to the desktop."
LangString DESC_SecAutostart ${LANG_ENGLISH} "Starts monitoring automatically when the computer boots."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} $(DESC_SecMain)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecFirewall} $(DESC_SecFirewall)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_SecDesktop)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAutostart} $(DESC_SecAutostart)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecUpdater} $(DESC_SecUpdater)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function ExtractPairingCode
  ; Fayl nomidan oxirgi `-` dan keyingi 6 belgini oladi va ular hex
  ; ekanini tekshiradi: `Chaqimchi_AI_Setup-A1B2C3.exe` -> `A1B2C3`.
  ;
  ; Nega qat'iy tekshiruv: bu qiymat keyin cloudga yuboriladi.  Nomda
  ; tasodifiy matn bo'lsa (`Setup (1).exe`) uni kod deb yuborish
  ; foydasiz so'rov va chalkash xato xabari bo'lardi.
  Push $R0
  Push $R1
  Push $R2
  Push $R3
  StrCpy $PairingCode ""

  StrCpy $R0 "$EXEFILE"
  ; `.exe` kengaytmasini kesamiz.
  StrLen $R1 $R0
  IntOp $R1 $R1 - 4
  StrCpy $R0 $R0 $R1

  ; Oxirgi 7 belgi `-XXXXXX` shaklidami?
  StrCpy $R2 $R0 7 -7
  StrCpy $R3 $R2 1
  StrCmp $R3 "-" 0 done

  StrCpy $R2 $R2 6 1          ; chiziqchadan keyingi 6 belgi
  StrCpy $R1 0                ; tekshirilgan belgilar soni

  check_loop:
    StrCmp $R1 6 accept
    StrCpy $R3 $R2 1 $R1
    ; Faqat 0-9 va A-F (katta harf) qabul qilinadi.
    StrCmp $R3 "0" next
    StrCmp $R3 "1" next
    StrCmp $R3 "2" next
    StrCmp $R3 "3" next
    StrCmp $R3 "4" next
    StrCmp $R3 "5" next
    StrCmp $R3 "6" next
    StrCmp $R3 "7" next
    StrCmp $R3 "8" next
    StrCmp $R3 "9" next
    StrCmp $R3 "A" next
    StrCmp $R3 "B" next
    StrCmp $R3 "C" next
    StrCmp $R3 "D" next
    StrCmp $R3 "E" next
    StrCmp $R3 "F" next
    Goto done
  next:
    IntOp $R1 $R1 + 1
    Goto check_loop

  accept:
    StrCpy $PairingCode $R2

  done:
    Pop $R3
    Pop $R2
    Pop $R1
    Pop $R0
FunctionEnd

Function .onInit
  ; Ilgari o'rnatilgan bo'lsa avval o'chirishni taklif qilamiz: eski
  ; `site-packages` ustiga yozilsa mos kelmaydigan versiyalar aralashib
  ; ketardi va sabab topib bo'lmaydigan xato chiqardi.
  ReadRegStr $R0 HKLM "${REG_UNINSTALL}" "UninstallString"
  ${If} $R0 != ""
    ; `/S` (jim) — bu masofadan yangilanish yo'li.  `MessageBox` u yerda
    ; SYSTEM sessiyasida (`schtasks /RU SYSTEM`) ochiladi va uni HECH KIM
    ; ko'rmaydi: o'rnatuvchi javob kutib abadiy osilib qoladi.  Yangilanish
    ; tekshiruvi har 15 daqiqada takrorlangani uchun osilgan jarayonlar
    ; yig'ilib boradi va do'kon hech qachon yangilanmaydi.
    ;
    ; O'chirish bo'limida bu himoya allaqachon bor edi — shu yerga
    ; yozilmagan.  Savol faqat odam o'zi o'rnatayotganda beriladi.
    IfSilent uninstall_old
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
  ; Avtostart vazifasi ham: qolib ketsa o'chirilgan dasturni har yonishda
  ; ishga tushirishga urinib, xato jurnalini to'ldirardi.
  nsExec::ExecToLog 'schtasks /End /TN "Chaqimchi AI"'
  nsExec::ExecToLog 'schtasks /Delete /F /TN "Chaqimchi AI"'
  ; Fayrvol qoidasi ham olib tashlanadi: o'chirilgan dasturdan keyin
  ; ochiq port qolib ketmasligi kerak.
  nsExec::ExecToLog 'netsh advfirewall firewall delete rule \
    name="Chaqimchi AI — kamera qidiruvi"'
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
