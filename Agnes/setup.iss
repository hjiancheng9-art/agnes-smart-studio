; Agnes AI — Inno Setup 安装脚本
; 用 Inno Setup 6 编译: iscc setup.iss

#define MyAppName "Agnes AI"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Agnes AI"
#define MyAppURL "https://agnes-ai.com"
#define MyAppExeName "AgnesLauncher.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE.txt
InfoBeforeFile=README.md
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=AgnesSetup_v{#MyAppVersion}
SetupIconFile=agnes.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce

[Files]
Source: "dist\AgnesLauncher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\AgnesQuery.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\AgnesKids.exe"; DestDir: "{app}"; Flags: ignoreversion
; 运行时依赖（PyInstaller --onedir）
Source: "dist\AgnesLauncher\*"; DestDir: "{app}\AgnesLauncher"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\AgnesQuery\*"; DestDir: "{app}\AgnesQuery"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\AgnesKids\*"; DestDir: "{app}\AgnesKids"; Flags: ignoreversion recursesubdirs createallsubdirs
; 资源文件
Source: "agnes.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "agnes_preview.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autoprograms}\{#MyAppName}\Agnes 查询工具"; Filename: "{app}\AgnesQuery.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\{#MyAppName}\Agnes 小画家"; Filename: "{app}\AgnesKids.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 Agnes AI"; Flags: postinstall nowait skipifsilent unchecked

[UninstallRun]
