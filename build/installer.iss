; -*- coding: utf-8 -*-
; ============================================================
; Open Meeting Scribe — Inno Setup 安装脚本
; 用法：iscc build\installer.iss /DMyAppVersion=7.0.0
;   或：iscc build\installer.iss（自动从 VERSION 文件读取）
; ============================================================

#define MyAppName "会议助手"
#define MyAppNameEn "Open Meeting Scribe"
#define MyAppExeName "OpenMeetingScribe.exe"
#define MyAppPublisher "Open Meeting Scribe"
#define MyAppURL "https://github.com/open-meeting-scribe/open-meeting-scribe"

; ── 版本号：优先通过 /DMyAppVersion=x.y.z 注入，否则从 VERSION 文件读取 ──
#ifndef MyAppVersion
  #define FileHandle FileOpen(SourcePath + "..\VERSION")
  #define MyAppVersion FileRead(FileHandle)
  #expr FileClose(FileHandle)
  #define MyAppVersion Trim(MyAppVersion)
#endif

[Setup]
; 固定 AppId，确保安装/升级/卸载识别为同一应用
AppId={{E8A3F3B3-6C1D-4E2F-9A7B-1D5C8F6A2E40}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppURL}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; 默认安装路径（Program Files 下）
DefaultDirName={autopf}\OpenMeetingScribe
DefaultGroupName={#MyAppName}

; 允许用户选择安装目录
DisableDirPage=no

; 安装向导语言（简体中文优先，英文兜底）
ShowLanguageDialog=auto

; 使用安装向导的推荐设置
UsePreviousAppDir=yes
UsePreviousSetupType=yes
UsePreviousTasks=yes
UsePreviousGroup=yes

; 输出到项目根目录的 dist/（.iss 位于 build/，需要向上一级）
OutputDir=..\dist
OutputBaseFilename=OpenMeetingScribe-{#MyAppVersion}-Setup
Compression=lzma2/ultra64
SolidCompression=yes

; 图标
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; 安装向导外观
WizardStyle=modern
WizardSizePercent=120,120

; 权限：安装到 Program Files 需要管理员权限
PrivilegesRequired=admin

; 卸载时不删除带 uninsneveruninstall 标志的文件
; （这是默认行为，显式声明以增强可读性）

[Languages]
; 简体中文语言文件来自第三方翻译项目，不一定随 Inno Setup 安装
; 优先使用 build/ 目录下的本地副本，其次查找 Inno Setup 自带 Languages 目录
#if FileExists(SourcePath + "\ChineseSimplified.isl")
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
#elif FileExists("C:\Program Files (x86)\Inno Setup 6\Languages\ChineseSimplified.isl")
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; ── 程序文件（升级时覆盖） ──
; Source 路径相对于 .iss 文件位置（build/），需要向上一级到项目根目录
Source: "..\dist\OpenMeetingScribe\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\OpenMeetingScribe\启动.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\OpenMeetingScribe\.env.example"; DestDir: "{app}"; Flags: uninsneveruninstall
Source: "..\dist\OpenMeetingScribe\ffmpeg\*"; DestDir: "{app}\ffmpeg"; Flags: ignoreversion recursesubdirs createallsubdirs

; ── 数据目录（升级/卸载时保留） ──
; uninsneveruninstall: 卸载时不删除，升级时旧版卸载后数据仍在
; skipifsourcedoesntexist: CI 环境中 data 目录可能为空，源不存在时不报错
Source: "..\dist\OpenMeetingScribe\data\*"; DestDir: "{app}\data"; Flags: createallsubdirs skipifsourcedoesntexist uninsneveruninstall

[Icons]
; 开始菜单快捷方式
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; 桌面快捷方式（可选）
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; 安装完成后可选启动程序
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 清理安装时产生的临时文件（如有），但不碰 data/ 和 .env
; data/ 和 .env 通过 uninsneveruninstall 标志保护，无需在此列出
