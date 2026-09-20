; ===========================================================================
;  BIMNEMO — instalador de Windows (Inno Setup 6)
; ---------------------------------------------------------------------------
;  Se compila con:
;      scripts\release\construir_instalador.bat
;  que antes prepara la carpeta `installer\salida\app` con el programa y su
;  entorno virtual.
;
;  ## Dos decisiones que conviene entender
;
;  **Se instala en la carpeta del usuario, no en Program Files.** BIMNEMO se
;  actualiza a sí mismo reescribiendo sus propios ficheros; en Program Files
;  eso exige permisos de administrador en cada actualización, y pedirle eso a
;  alguien cada semana acaba en «actualizar más tarde» para siempre.
;
;  **Al desinstalar NO se borran los datos.** Las memorias, los documentos y
;  la configuración del usuario se quedan. Un desinstalador que se lleva por
;  delante meses de trabajo es un desastre del que nadie se recupera; si
;  quiere borrarlos, están en una carpeta y puede hacerlo él.
; ===========================================================================

#define Nombre      "BIMNEMO"
#define Publicador  "CM Educativa"
#define Web         "https://github.com/CMEDUCATIVA/BIMNEMO"
#define Ejecutable  "BIMNEMO.bat"

; La versión la inyecta el guion de construcción con /DVersion=...
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{B1MN3M0-0000-4000-A000-BIMNEMO00001}
AppName={#Nombre}
AppVersion={#Version}
AppVerName={#Nombre} {#Version}
AppPublisher={#Publicador}
AppPublisherURL={#Web}
AppSupportURL={#Web}/blob/main/como_actualizar.md
AppUpdatesURL={#Web}/releases

; Sin permisos de administrador: ver la nota de arriba.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\BIMNEMO
DefaultGroupName={#Nombre}
DisableProgramGroupPage=yes
OutputDir=salida
OutputBaseFilename=BIMNEMO-{#Version}-instalador
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; El entorno virtual son cientos de megas: sin esto el instalador tarda una
; eternidad en prepararse y el usuario cree que se colgó.
DiskSpanning=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"; \
    GroupDescription: "Accesos directos:"

[Files]
; Todo lo que prepara el guion de construcción: el programa y su `.venv`.
Source: "salida\app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Sin `IconFilename`: los accesos directos toman el icono del .bat. Feo, pero
; honesto — BIMNEMO todavía no tiene icono propio. Cuando lo tenga, se deja en
; `installer\bimnemo.ico`, se añade a [Files] y se referencia aquí.
Name: "{group}\{#Nombre}"; Filename: "{app}\{#Ejecutable}"; WorkingDir: "{app}"
Name: "{group}\Cómo actualizar"; Filename: "{app}\como_actualizar.md"
Name: "{group}\Desinstalar {#Nombre}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#Nombre}"; Filename: "{app}\{#Ejecutable}"; \
    WorkingDir: "{app}"; Tasks: escritorio

[Run]
Filename: "{app}\{#Ejecutable}"; Description: "Abrir {#Nombre} ahora"; \
    WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent shellexec

[UninstallDelete]
; Lo que genera el programa al funcionar, no lo que crea el usuario.
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\lightrag.log"

[Messages]
es.WelcomeLabel2=Esto instalará [name/ver] en tu ordenador.%n%nBIMNEMO es una memoria de conocimiento que funciona en tu máquina: tus documentos no salen de ella.%n%nSe instalará en tu carpeta personal para poder actualizarse solo, sin pedirte permisos de administrador cada vez.

[Code]
// Si hay una instalación previa corriendo, sus ficheros están en uso y la
// copia falla a medias. Se avisa antes en vez de dejar la instalación rota.
function InitializeSetup(): Boolean;
var
  Resultado: Integer;
begin
  Result := True;
  if CheckForMutexes('BIMNEMO_EN_MARCHA') then
  begin
    Resultado := MsgBox(
      'BIMNEMO parece estar abierto.' + #13#10#13#10 +
      'Ciérralo antes de continuar; si no, la instalación puede quedar a medias.',
      mbError, MB_RETRYCANCEL);
    Result := (Resultado = IDRETRY);
  end;
end;
