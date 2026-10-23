Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"
!include "WinVer.nsh"

Name "超星桌面版 ${APP_VERSION}"
OutFile "${OUTPUT_EXE}"
InstallDir "$LOCALAPPDATA\Programs\ChaoxingDesktop"
InstallDirRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChaoxingDesktop" "InstallLocation"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 64
ShowInstDetails show
ShowUninstDetails show
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName" "ChaoxingDesktop"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "FileDescription" "超星桌面版安装程序"
VIAddVersionKey "LegalCopyright" "GPL-3.0"

Var NoRegistration
Var NoShortcuts

!define MUI_ABORTWARNING
!define MUI_ICON "${APP_ICON}"
!define MUI_UNICON "${APP_ICON}"
!define MUI_FINISHPAGE_RUN "$INSTDIR\ChaoxingDesktop.exe"
!define MUI_FINISHPAGE_RUN_TEXT "运行超星桌面版"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!define MUI_FINISHPAGE_TEXT "安装完成。覆盖更新沿用原有设置和个人数据；首次安装使用独立配置目录。卸载程序将保留个人数据。"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${APP_DIR}\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Function .onInit
    SetShellVarContext current
    SetRegView 64
    ${IfNot} ${RunningX64}
        MessageBox MB_ICONSTOP "此程序需要 Windows 10/11 64 位系统。"
        Abort
    ${EndIf}
    ${IfNot} ${AtLeastWin10}
        MessageBox MB_ICONSTOP "此程序需要 Windows 10 或更新的系统。"
        Abort
    ${EndIf}
    StrCpy $NoRegistration 0
    StrCpy $NoShortcuts 0
    ${GetParameters} $0
    ClearErrors
    ${GetOptions} $0 "/NoRegistration" $1
    ${IfNot} ${Errors}
        StrCpy $NoRegistration 1
    ${EndIf}
    ClearErrors
    ${GetOptions} $0 "/NoShortcuts" $1
    ${IfNot} ${Errors}
        StrCpy $NoShortcuts 1
    ${EndIf}
FunctionEnd

Section "超星桌面版" SEC_MAIN
    SetOutPath "$INSTDIR"
    ; The marker selects the existing user's data. Keep it on upgrades.
    SetOverwrite off
    File "${APP_DIR}\installation.json"
    SetOverwrite on
    ; Remove only explicitly listed obsolete application files on upgrades.
    ; No wildcards or recursive directory deletion; personal data stays intact.
    !include "${RETIRED_FILES}"
    File /r /x installation.json "${APP_DIR}\*.*"
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    ${If} $NoShortcuts == 0
        CreateDirectory "$SMPROGRAMS\ChaoxingDesktop"
        CreateShortcut "$SMPROGRAMS\ChaoxingDesktop\超星桌面版.lnk" "$INSTDIR\ChaoxingDesktop.exe"
        CreateShortcut "$SMPROGRAMS\ChaoxingDesktop\卸载.lnk" "$INSTDIR\Uninstall.exe"
        CreateShortcut "$DESKTOP\超星桌面版.lnk" "$INSTDIR\ChaoxingDesktop.exe"
    ${Else}
        FileOpen $0 "$INSTDIR\installer-no-shortcuts" w
        FileClose $0
    ${EndIf}
    ${If} $NoRegistration == 0
        WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChaoxingDesktop" "DisplayName" "超星桌面版 ${APP_VERSION}"
        WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChaoxingDesktop" "DisplayVersion" "${APP_VERSION}"
        WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChaoxingDesktop" "UninstallString" '$\"$INSTDIR\Uninstall.exe$\"'
        WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChaoxingDesktop" "QuietUninstallString" '$\"$INSTDIR\Uninstall.exe$\" /S'
        WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChaoxingDesktop" "InstallLocation" "$INSTDIR"
        WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChaoxingDesktop" "DisplayIcon" "$INSTDIR\ChaoxingDesktop.exe"
        WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChaoxingDesktop" "NoModify" 1
        WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChaoxingDesktop" "NoRepair" 1
    ${Else}
        FileOpen $0 "$INSTDIR\installer-no-registration" w
        FileClose $0
    ${EndIf}
SectionEnd

Function un.onInit
    SetShellVarContext current
    SetRegView 64
FunctionEnd

Section "Uninstall"
    IfFileExists "$INSTDIR\installer-no-shortcuts" skip_shortcuts
        Delete "$DESKTOP\超星桌面版.lnk"
        Delete "$SMPROGRAMS\ChaoxingDesktop\超星桌面版.lnk"
        Delete "$SMPROGRAMS\ChaoxingDesktop\卸载.lnk"
        RMDir "$SMPROGRAMS\ChaoxingDesktop"
    skip_shortcuts:
    IfFileExists "$INSTDIR\installer-no-registration" skip_registration
        DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ChaoxingDesktop"
    skip_registration:
    !include "${UNINSTALL_FILES}"
    Delete "$INSTDIR\installer-no-shortcuts"
    Delete "$INSTDIR\installer-no-registration"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir "$INSTDIR"
SectionEnd
