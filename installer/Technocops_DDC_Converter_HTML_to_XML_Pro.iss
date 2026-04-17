#define MyAppName "Technocops DDC Converter (HTML to XML) Pro"
#define MyAppVersion "1.0.3"
#define MyAppPublisher "Technocops Technology & Innovation"
#define MyAppExeName "Technocops_DDC_Converter_HTML_to_XML_Pro.exe"
#define MyAppDirName "Technocops_DDC_Converter_HTML_to_XML_Pro"
#ifndef MyPortableRoot
  #define MyPortableRoot "..\\release\\portable"
#endif

[Setup]
AppId={{A14D7F0E-0F42-4A3E-A9B4-2B9B5AC869E3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
LicenseFile=license_terms.txt
SetupIconFile=..\assets\branding\technocops_app_icon.ico
OutputDir=..\release\installer
OutputBaseFilename=Technocops_DDC_Converter_HTML_to_XML_Pro_Setup_v1.0.3
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion=1.0.3.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Installer
SetupLogging=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "{#MyPortableRoot}\{#MyAppDirName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
