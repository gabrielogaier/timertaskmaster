#define MyAppName "Timer Task Master"
#define MyAppVersion "2.1.0"
#define MyAppPublisher "gabrielogaier"
#define MyAppExeName "Timer Task Master.exe"

[Setup]
; Mesmo AppId do Timer Task: o Master é instalado como atualização/substituição.
AppId={{A8D1F4E9-DC92-4EBA-B5C8-70E28D3890A1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Timer Task
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=TimerTaskMaster-Setup
SetupIconFile=..\.build-assets\timertaskmaster.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoDescription=Instalador do Timer Task Master

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked
Name: "startup"; Description: "Iniciar o Timer Task Master com o Windows"; GroupDescription: "Inicialização:"; Flags: unchecked

[InstallDelete]
; Remove somente arquivos do programa antigo. Os dados em %LOCALAPPDATA%\TimerTask não são apagados.
Type: files; Name: "{app}\Timer Task.exe"
Type: files; Name: "{userprograms}\Timer Task\Timer Task.lnk"
Type: files; Name: "{autodesktop}\Timer Task.lnk"

[Files]
Source: "..\dist\Timer Task Master.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Timer Task Master"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\Timer Task Master"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Timer Task Master"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o Timer Task Master"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Timer Task');
    DeleteFile(ExpandConstant('{userprograms}\Timer Task\Timer Task.lnk'));
    DeleteFile(ExpandConstant('{autodesktop}\Timer Task.lnk'));
  end;
end;
