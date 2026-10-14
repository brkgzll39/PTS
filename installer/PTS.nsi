; PTS - Plaka Tanima Sistemi -- Windows kurulum programi (NSIS 3)
;
; 2026-10-14: Inno Setup betigi (PTS.iss) hedef bilgisayarda internet, uv ve
; Python'un hazir olmasini bekliyordu. Bu kurulum programi her seyi ICINDE
; tasir: gomulu Python 3.12 (python\), tum Windows paketleri (paket\) ve plaka
; modelleri (modeller\). Hedef bilgisayarda internet gerekmez.
;
; Dogrudan derlenmez: installer/setup_olustur.sh hazirlik klasorunu (KAYNAK)
; doldurup bu betigi makensis ile derler -- bkz. o betigin basindaki not.

Unicode true
SetCompressor /SOLID lzma
SetCompressorDictSize 64

!ifndef KAYNAK
  !error "KAYNAK tanimli degil -- installer/setup_olustur.sh ile derleyin"
!endif
!ifndef SURUM
  !define SURUM "1.0.0"
!endif
!ifndef CIKTI
  !define CIKTI "output\PTS-Kurulum.exe"
!endif

!define UYGULAMA "PTS - Plaka Tanima Sistemi"
!define KALDIRMA_ANAHTARI "Software\Microsoft\Windows\CurrentVersion\Uninstall\PTS"

Name "${UYGULAMA}"
OutFile "${CIKTI}"
; Program Files YERINE C:\PTS: PTS veritabanini, goruntuleri ve loglari kendi
; klasorune yazar; Program Files yonetici olmayan kullaniciya yazilamaz.
InstallDir "C:\PTS"
InstallDirRegKey HKLM "${KALDIRMA_ANAHTARI}" "InstallLocation"
RequestExecutionLevel admin
ShowInstDetails show
BrandingText "PTS ${SURUM}"
VIProductVersion "${SURUM}.0"
VIAddVersionKey "ProductName" "${UYGULAMA}"
VIAddVersionKey "FileDescription" "${UYGULAMA} kurulumu"
VIAddVersionKey "FileVersion" "${SURUM}"
VIAddVersionKey "ProductVersion" "${SURUM}"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "PTS Kurulumuna Hos Geldiniz"
!define MUI_WELCOMEPAGE_TEXT "Bu program PTS - Plaka Tanima Sistemi'ni bu bilgisayara kurar.$\r$\n$\r$\nPython ve tum gerekli paketler kurulumun icindedir; internet baglantisi gerekmez.$\r$\n$\r$\nDaha once kurulmus bir PTS'in uzerine kurarsaniz veritabani, goruntuler ve ayarlar KORUNUR; yalnizca program dosyalari guncellenir."
!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "PTS'i simdi baslat"
!define MUI_FINISHPAGE_RUN_FUNCTION BaslatVePaneliAc
!define MUI_FINISHPAGE_TEXT "Kurulum tamamlandi.$\r$\n$\r$\nMasaustundeki 'PTS Baslat' kisayolu sistemi baslatir, 'PTS Paneli' tarayicida paneli acar (http://localhost:8000).$\r$\n$\r$\nIlk acilista yonetici hesabi olusturulur; ardindan Lisans sekmesinden lisans girilir."

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Turkish"

Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "PTS yalnizca 64 bit Windows uzerinde calisir."
    Abort
  ${EndIf}
  SetRegView 64
FunctionEnd

Section "PTS (gerekli)" SecAna
  SectionIn RO

  ; Calisan bir PTS varken dosyalar kilitli olur; kullaniciyi uyar.
  nsExec::ExecToStack '"$SYSDIR\cmd.exe" /c netstat -ano | findstr /C:":8000 " | findstr LISTENING'
  Pop $0 ; cikis kodu (0 = port dinleniyor)
  Pop $1 ; komut ciktisi
  ${If} $0 == 0
    MessageBox MB_OKCANCEL|MB_ICONEXCLAMATION "8000 portunda calisan bir PTS (ya da baska bir program) var.$\r$\nGuncelleme icin once PTS penceresini kapatin, sonra Tamam'a basin." IDOK +2
    Abort
  ${EndIf}

  SetOutPath "$INSTDIR"
  File /r "${KAYNAK}\*.*"

  ; Bos veri klasorleri (icerikleri kurulumda/guncellemede hic silinmez).
  CreateDirectory "$INSTDIR\veritabani"
  CreateDirectory "$INSTDIR\goruntuler"
  CreateDirectory "$INSTDIR\disa_aktarilanlar"
  CreateDirectory "$INSTDIR\loglar"

  DetailPrint "Python ortami ve paketler kuruluyor (birkac dakika surebilir)..."
  nsExec::ExecToLog '"$SYSDIR\cmd.exe" /c ""$INSTDIR\kurulum.bat" otomatik"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONEXCLAMATION "Python ortami kurulurken hata olustu (kod $0).$\r$\nAyrintilar kurulum penceresinin 'Ayrintilari goster' bolumunde.$\r$\nSorunu giderdikten sonra $INSTDIR\kurulum.bat dosyasini calistirabilirsiniz."
  ${EndIf}

  ; Kisayollar
  CreateShortCut "$DESKTOP\PTS Baslat.lnk" "$INSTDIR\calistir.bat" "" "$SYSDIR\shell32.dll" 137
  WriteINIStr "$DESKTOP\PTS Paneli.url" "InternetShortcut" "URL" "http://localhost:8000"
  CreateDirectory "$SMPROGRAMS\PTS"
  CreateShortCut "$SMPROGRAMS\PTS\PTS Baslat.lnk" "$INSTDIR\calistir.bat" "" "$SYSDIR\shell32.dll" 137
  WriteINIStr "$SMPROGRAMS\PTS\PTS Paneli.url" "InternetShortcut" "URL" "http://localhost:8000"
  CreateShortCut "$SMPROGRAMS\PTS\PTS Kaldir.lnk" "$INSTDIR\Kaldir.exe"

  ; Kaldirma bilgisi
  WriteUninstaller "$INSTDIR\Kaldir.exe"
  WriteRegStr HKLM "${KALDIRMA_ANAHTARI}" "DisplayName" "${UYGULAMA}"
  WriteRegStr HKLM "${KALDIRMA_ANAHTARI}" "DisplayVersion" "${SURUM}"
  WriteRegStr HKLM "${KALDIRMA_ANAHTARI}" "Publisher" "PTS"
  WriteRegStr HKLM "${KALDIRMA_ANAHTARI}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${KALDIRMA_ANAHTARI}" "UninstallString" '"$INSTDIR\Kaldir.exe"'
  WriteRegDWORD HKLM "${KALDIRMA_ANAHTARI}" "NoModify" 1
  WriteRegDWORD HKLM "${KALDIRMA_ANAHTARI}" "NoRepair" 1
SectionEnd

Section "Diger bilgisayarlarin panele baglanmasina izin ver (guvenlik duvari, port 8000)" SecGuvenlikDuvari
  ; Nizamiyelerdeki diger bilgisayarlar paneli http://<bu bilgisayar>:8000
  ; adresinden acar; Windows Guvenlik Duvari bu portu varsayilan olarak kapatir.
  nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="PTS Panel (8000)"'
  Pop $0
  nsExec::ExecToLog 'netsh advfirewall firewall add rule name="PTS Panel (8000)" dir=in action=allow protocol=TCP localport=8000 profile=domain,private'
  Pop $0
SectionEnd

Section /o "Windows acilisinda PTS'i otomatik baslat" SecOtomatik
  SetShellVarContext all
  CreateShortCut "$SMSTARTUP\PTS Baslat.lnk" "$INSTDIR\calistir.bat" "" "$SYSDIR\shell32.dll" 137 SW_SHOWMINIMIZED
  SetShellVarContext current
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAna} "Program dosyalari, gomulu Python 3.12, paketler ve plaka modelleri."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecGuvenlikDuvari} "Ag uzerindeki diger nizamiye bilgisayarlarinin bu PTS'e tarayiciyla baglanabilmesi icin 8000 portunu (alan ve ozel aglarda) acar."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecOtomatik} "Bilgisayar acildiginda (kullanici oturum actiginda) PTS kendiliginden baslar."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Function BaslatVePaneliAc
  Exec '"$SYSDIR\cmd.exe" /c start "PTS" /D "$INSTDIR" "$INSTDIR\calistir.bat"'
  Sleep 4000
  ExecShell "open" "http://localhost:8000"
FunctionEnd

Section "Uninstall"
  SetRegView 64
  ; Veri (veritabani, goruntuler, disa aktarilanlar, loglar, .env, ayar ve
  ; lisans dosyalari) BILEREK silinmez -- yanlislikla kaldirma kayit kaybina
  ; yol acmasin. Yalnizca program dosyalari kaldirilir.
  RMDir /r "$INSTDIR\.venv"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\paket"
  RMDir /r "$INSTDIR\modeller"
  RMDir /r "$INSTDIR\frontend"
  RMDir /r "$INSTDIR\backend\__pycache__"
  Delete "$INSTDIR\backend\*.py"
  Delete "$INSTDIR\backend\requirements*.txt"
  RMDir /r "$INSTDIR\backend\fonts"
  Delete "$INSTDIR\calistir.bat"
  Delete "$INSTDIR\kurulum.bat"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\.env.example"
  Delete "$INSTDIR\KURULUM-NOTLARI.txt"
  Delete "$INSTDIR\Kaldir.exe"

  Delete "$DESKTOP\PTS Baslat.lnk"
  Delete "$DESKTOP\PTS Paneli.url"
  RMDir /r "$SMPROGRAMS\PTS"
  SetShellVarContext all
  Delete "$SMSTARTUP\PTS Baslat.lnk"
  SetShellVarContext current

  nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="PTS Panel (8000)"'
  Pop $0
  DeleteRegKey HKLM "${KALDIRMA_ANAHTARI}"

  MessageBox MB_ICONINFORMATION "Program dosyalari kaldirildi.$\r$\nVeritabani, goruntuler ve ayarlar $INSTDIR klasorunde birakildi; artik gerekmiyorsa bu klasoru elle silebilirsiniz."
SectionEnd
