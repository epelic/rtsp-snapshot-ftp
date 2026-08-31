Unicode True
Name "RTSP Snapshot FTP"
OutFile "outputs\RTSP-Snapshot-FTP-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\RTSP Snapshot FTP"
InstallDirRegKey HKCU "Software\RTSP Snapshot FTP" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Icon "assets\camera-icon.ico"
UninstallIcon "assets\camera-icon.ico"

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "assets\camera-icon.ico"
!define MUI_UNICON "assets\camera-icon.ico"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Italian"
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "German"

Function .onInit
  !insertmacro MUI_LANGDLL_DISPLAY
FunctionEnd

Function un.onInit
  !insertmacro MUI_UNGETLANGUAGE
FunctionEnd

Section "Applicazione" SEC_APP
  SetOutPath "$INSTDIR"
  File "dist\RTSP-Snapshot-FTP.exe"
  File /oname=camera-icon.ico "assets\camera-icon.ico"
  WriteUninstaller "$INSTDIR\Disinstalla.exe"
  WriteRegStr HKCU "Software\RTSP Snapshot FTP" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RTSP Snapshot FTP" "DisplayName" "RTSP Snapshot FTP"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RTSP Snapshot FTP" "DisplayIcon" "$INSTDIR\RTSP-Snapshot-FTP.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RTSP Snapshot FTP" "UninstallString" '"$INSTDIR\Disinstalla.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RTSP Snapshot FTP" "Publisher" "Freewaves"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RTSP Snapshot FTP" "DisplayVersion" "1.1.3"
  CreateDirectory "$SMPROGRAMS\RTSP Snapshot FTP"
  CreateShortcut "$SMPROGRAMS\RTSP Snapshot FTP\RTSP Snapshot FTP.lnk" "$INSTDIR\RTSP-Snapshot-FTP.exe" "" "$INSTDIR\camera-icon.ico"
  CreateShortcut "$SMPROGRAMS\RTSP Snapshot FTP\Disinstalla.lnk" "$INSTDIR\Disinstalla.exe"
  CreateShortcut "$DESKTOP\RTSP Snapshot FTP.lnk" "$INSTDIR\RTSP-Snapshot-FTP.exe" "" "$INSTDIR\camera-icon.ico"
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\RTSP Snapshot FTP.lnk"
  Delete "$SMPROGRAMS\RTSP Snapshot FTP\RTSP Snapshot FTP.lnk"
  Delete "$SMPROGRAMS\RTSP Snapshot FTP\Disinstalla.lnk"
  RMDir "$SMPROGRAMS\RTSP Snapshot FTP"
  Delete "$INSTDIR\RTSP-Snapshot-FTP.exe"
  Delete "$INSTDIR\camera-icon.ico"
  Delete "$INSTDIR\Disinstalla.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\RTSP Snapshot FTP"
  DeleteRegKey HKCU "Software\RTSP Snapshot FTP"
SectionEnd
