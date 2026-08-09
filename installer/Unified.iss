; Inno Setup 6 script for Unified.
;
; Packages the PyInstaller output (dist\Unified\) into a single
; distributable installer: Unified-Setup-v1.2.1.exe. Run build.py first
; to produce dist\Unified\ before compiling this script.
;
; Compile with:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\Unified.iss
;
; AppId is a fixed, permanent GUID for this product - do not regenerate it
; for future versions, or Windows will treat upgrades as a separate,
; parallel install instead of replacing the old one in place.

#define MyAppName "Unified"
#define MyAppVersion "1.2.1"
#define MyAppPublisher "preinfection"
#define MyAppExeName "Unified.exe"
#define MyDistDir "..\dist\Unified"

[Setup]
AppId={{CFB1B3AC-33C3-477B-B335-8779521C20E0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppVerName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup

; {autopf}\Unified: resolves to the real Program Files when the installer
; is run elevated (as administrator), and to a per-user Programs folder
; otherwise - so a normal user can install with no UAC prompt, while an
; admin running it elevated still gets the standard machine-wide install.
; PrivilegesRequiredOverridesAllowed keeps both paths available: a user
; can right-click "Run as administrator" for a machine-wide install even
; though it isn't required.
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
; DisableDirPage is intentionally left unset (default) so the wizard's
; "Select Destination Location" page with its Browse... button is shown -
; the user can change the install location.

OutputDir=..\release
OutputBaseFilename=Unified-Setup-v{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern

; No app files are bundled per-language; a single English UI is enough.
ShowLanguageDialog=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Both shortcuts are optional and off/on exactly as chosen by the user on
; the "Select Additional Tasks" wizard page - neither is forced. The Start
; Menu shortcut defaults on (ordinary, expected, one click to skip); the
; desktop shortcut defaults off, since a new desktop icon should be
; something the user opts into, not something every install leaves behind.
Name: "startmenuicon"; Description: "Create a Start Menu shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
; The entire PyInstaller onedir output - Unified.exe depends on everything
; under _internal\ and will not run without it.
Source: "{#MyDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Tasks: startmenuicon
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

; Deliberately no [UninstallDelete] section: the uninstaller must only ever
; remove what it installed under {app} (Program Files or the per-user
; equivalent). %APPDATA%\Unified - accounts, settings, and the encrypted
; mailbox cache - lives completely outside {app} and Inno Setup never
; touches it unless explicitly told to, which this script never does. This
; is what makes uninstall/reinstall and version upgrades keep user data.
