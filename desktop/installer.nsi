Unicode true
!include "MUI2.nsh"
!define VERSION "1.5.2"
Name "MailAI"
OutFile "build\MailAI-Setup.exe"
InstallDir "$LOCALAPPDATA\MailAI\App-${VERSION}"
RequestExecutionLevel user
SetCompressor /SOLID zlib
CRCCheck force
ShowInstDetails show
BrandingText "!Yos | MailAI ${VERSION}"
VIProductVersion "1.5.2.0"
VIAddVersionKey "ProductName" "MailAI"
VIAddVersionKey "CompanyName" "!Yos"
VIAddVersionKey "FileDescription" "MailAI setup"
VIAddVersionKey "FileVersion" "1.5.2.0"
VIAddVersionKey "ProductVersion" "1.5.2"
VIAddVersionKey "LegalCopyright" "!Yos"
!define MUI_ICON "icon.ico"
!define MUI_UNICON "icon.ico"
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Hebrew"

Function .onInit
 SetRegView 64
 System::Call 'kernel32::OpenMutexW(i 0x100000,i 0,w "Local\MailAIControlV1") p.r0'
 IntCmp $0 0 ready
 System::Call 'kernel32::CloseHandle(p r0)'
 MessageBox MB_OK|MB_ICONEXCLAMATION "MailAI כבר פתוח. סגור אותו דרך הסמל ליד השעון ואז פתח שוב את ההתקנה."
 Abort
 ready:
 InitPluginsDir
 SetOutPath "$PLUGINSDIR\App"
 File "build\MailAI.exe"
 File "MailAI.exe.config"
 File "mailai.py"
 File "bot.py"
 File "thread_guard.py"
 File "web_reader.py"
 SetOutPath "$PLUGINSDIR\App\python"
 File /r "payload\python\*"
 CreateDirectory "$PLUGINSDIR\Data"
 System::Call 'kernel32::SetEnvironmentVariableW(w "MAILAI_DATA",w "$PLUGINSDIR\Data")'
 System::Call 'kernel32::SetEnvironmentVariableW(w "MAILAI_SETUP_STAGE",w "1")'
 ExecWait '$\"$PLUGINSDIR\App\MailAI.exe$\" --package $\"$EXEPATH$\"' $0
 StrCmp $0 42 approved
 SetErrorLevel 0
 Quit
 approved:
 IfFileExists "$PLUGINSDIR\Data\settings.dat" connected
 MessageBox MB_OK|MB_ICONSTOP "החיבור לא נשמר. ההתקנה בוטלה."
 Quit
 connected:
 System::Call 'kernel32::SetEnvironmentVariableW(w "MAILAI_DATA",p 0)'
 System::Call 'kernel32::SetEnvironmentVariableW(w "MAILAI_SETUP_STAGE",p 0)'
 SetOutPath "$TEMP"
FunctionEnd

Section "MailAI"
 DetailPrint "החיבורים אושרו. מתקין את MailAI..."
 ClearErrors
 CreateDirectory "$INSTDIR"
 CopyFiles /SILENT "$PLUGINSDIR\App\*.*" "$INSTDIR"
 CreateDirectory "$LOCALAPPDATA\MailAI\Data"
 CopyFiles /SILENT "$PLUGINSDIR\Data\*.*" "$LOCALAPPDATA\MailAI\Data"
 IfErrors failed
 WriteUninstaller "$INSTDIR\Uninstall.exe"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MailAI" "DisplayName" "MailAI"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MailAI" "DisplayVersion" "${VERSION}"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MailAI" "Publisher" "!Yos"
 WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MailAI" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
 Exec '$\"$INSTDIR\MailAI.exe$\" --background'
 Goto done
 failed:
 MessageBox MB_OK|MB_ICONSTOP "לא ניתן להשלים את העתקת הקבצים. הבוט לא הופעל."
 SetErrorLevel 1
 done:
SectionEnd

Section "Uninstall"
 DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "MailAI"
 DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MailAI"
 Delete "$DESKTOP\MailAI.lnk"
 Delete "$INSTDIR\MailAI.exe"
 Delete "$INSTDIR\MailAI.exe.config"
 Delete "$INSTDIR\mailai.py"
 Delete "$INSTDIR\bot.py"
 Delete "$INSTDIR\thread_guard.py"
 Delete "$INSTDIR\web_reader.py"
 Delete "$INSTDIR\Uninstall.exe"
 RMDir /r "$INSTDIR\python"
 RMDir "$INSTDIR"
SectionEnd
