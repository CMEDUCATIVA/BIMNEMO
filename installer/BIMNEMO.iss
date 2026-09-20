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
; Los accesos directos NO apuntan al .bat: un .bat abre siempre una ventana de
; consola, y esto es una aplicación. `pythonw.exe` es el mismo intérprete sin
; consola. El .bat se queda para diagnosticar (`BIMNEMO.bat --consola`).
;
; La ruta es `python\`, no `.venv\`: el paquete lleva un Python portable, no un
; entorno virtual — un venv de Windows no lleva intérprete dentro y dependería
; de que el cliente tuviera Python instalado.
#define Ejecutable  "python\pythonw.exe"
#define Argumentos  "-m lightrag.api.bimnemo.desktop"

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
; No es una constante fija porque, si había una instalación previa y se
; desinstala, hay que proponer **su** carpeta: es donde están los documentos y
; las memorias del cliente. Ver `DirPropuesto` en [Code].
DefaultDirName={code:DirPropuesto}

; Con esto el **desinstalador** también avisa si BIMNEMO está abierto. El
; mutex lo crea el lanzador (`marcar_en_marcha` en `desktop.py`); si se cambia
; el nombre aquí, hay que cambiarlo allí.
AppMutex=BIMNEMO_EN_MARCHA
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

[InstallDelete]
; El `.venv` de las versiones hasta la 1.2.0. Desde la 1.2.1 el paquete lleva
; un Python portable en `python\` y ese `.venv` no se usa para nada, pero el
; desinstalador anterior no se lo lleva entero: solo borra lo que él instaló,
; y los `__pycache__` que aparecieron al funcionar se quedan. Son megas
; muertos y, peor, un segundo intérprete a medias que confunde a cualquiera
; que abra la carpeta.
;
; El `Check` es por si alguien apunta el instalador a una copia de desarrollo:
; allí el `.venv` sí es el bueno y no se toca.
Type: filesandordirs; Name: "{app}\.venv"; Check: not EsCopiaDeDesarrollo

[Icons]
; Sin `IconFilename`: los accesos directos toman el icono de `pythonw.exe`.
; Feo, pero honesto — BIMNEMO todavía no tiene icono propio. Cuando lo tenga,
; se deja en `installer\bimnemo.ico`, se añade a [Files] y se referencia aquí.
Name: "{group}\{#Nombre}"; Filename: "{app}\{#Ejecutable}"; \
    Parameters: "{#Argumentos}"; WorkingDir: "{app}"
Name: "{group}\Cómo actualizar"; Filename: "{app}\como_actualizar.md"
Name: "{group}\Diagnóstico (con consola)"; Filename: "{app}\BIMNEMO.bat"; \
    Parameters: "--consola"; WorkingDir: "{app}"
Name: "{group}\Desinstalar {#Nombre}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#Nombre}"; Filename: "{app}\{#Ejecutable}"; \
    Parameters: "{#Argumentos}"; WorkingDir: "{app}"; Tasks: escritorio

[Run]
; Sin `shellexec`: se lanza el ejecutable directamente, que es lo que permite
; pasarle los argumentos sin que el intérprete de comandos se meta en medio.
Filename: "{app}\{#Ejecutable}"; Parameters: "{#Argumentos}"; \
    Description: "Abrir {#Nombre} ahora"; WorkingDir: "{app}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Lo que genera el programa al funcionar, no lo que crea el usuario.
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\lightrag.log"

[Messages]
es.WelcomeLabel2=Esto instalará [name/ver] en tu ordenador.%n%nBIMNEMO es una memoria de conocimiento que funciona en tu máquina: tus documentos no salen de ella.%n%nSe instalará en tu carpeta personal para poder actualizarse solo, sin pedirte permisos de administrador cada vez.

[Code]

// --- Instalación anterior --------------------------------------------------
//
// Instalar encima de una versión previa deja mezclados los ficheros de las
// dos: los que la nueva trae se reemplazan, y los que ya no existen se
// quedan ahí para siempre. Con un cambio de estructura —como el paso del
// entorno virtual al Python portable— eso deja una carpeta con las dos cosas
// y accesos directos apuntando a la que ya no está.
//
// Así que se detecta y se ofrece desinstalar primero. **Los datos no se
// tocan**: el desinstalador deja `inputs\`, `rag_storage\` y el `.env` donde
// están, y la instalación nueva los encuentra igual.

// OJO CON LAS LLAVES. En las secciones de Inno, `{{` es una llave escapada:
// por eso arriba pone `AppId={{B1MN3M0-...}`, que vale `{B1MN3M0-...}`. Pero
// **en [Code] no hay tal escape**: una cadena de Pascal es literal. Escribirla
// aquí con la llave doblada buscaba `{{B1MN3M0-...}_is1`, que no existe, y la
// detección de la instalación anterior no encontraba nunca nada aunque
// estuviera delante. Una sola llave.
function ClaveDesinstalacion(): String;
begin
  Result := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
            '{B1MN3M0-0000-4000-A000-BIMNEMO00001}_is1';
end;

function LeerPrevio(Valor: String): String;
var
  dato: String;
begin
  Result := '';
  if RegQueryStringValue(HKCU, ClaveDesinstalacion(), Valor, dato) then
    Result := dato
  else if RegQueryStringValue(HKLM, ClaveDesinstalacion(), Valor, dato) then
    Result := dato;
end;

function DesinstaladorPrevio(): String;
begin
  Result := RemoveQuotes(LeerPrevio('UninstallString'));
end;

function VersionPrevia(): String;
begin
  Result := LeerPrevio('DisplayVersion');
end;

// Dónde proponer la instalación.
//
// Si se desinstala la versión anterior, su entrada del registro desaparece y
// con ella lo que Inno usa para recordar la carpeta. Sin esto, la instalación
// nueva se iría a la carpeta por defecto y **dejaría los documentos y las
// memorias del cliente abandonados en la carpeta vieja**, con la aplicación
// arrancando vacía y sin explicación. Así que se anota antes de desinstalar.
var
  RutaPrevia: String;

// Una copia clonada para desarrollar, no una instalación. Se reconoce por el
// `.git`, y ahí el instalador no debe borrar nada que no haya puesto él.
function EsCopiaDeDesarrollo(): Boolean;
begin
  Result := DirExists(ExpandConstant('{app}\.git'));
end;

function CarpetaPorDefecto(): String;
begin
  Result := ExpandConstant('{localappdata}\BIMNEMO');
end;

function DirPropuesto(Valor: String): String;
begin
  if RutaPrevia <> '' then
    Result := RutaPrevia
  else
    Result := CarpetaPorDefecto();
end;

// Una instalación puede existir SIN constar en el registro: alguien limpia el
// registro, se copia el perfil de un usuario a otro, o —como pasó aquí— otra
// instalación con el mismo AppId se desinstala después y se lleva la entrada
// por delante. La carpeta se queda entera y el detector no veía nada.
//
// Así que el registro es una pista, no la única. Se mira también el disco.
function HayInstalacionEn(carpeta: String): Boolean;
begin
  Result := (carpeta <> '') and
            (FileExists(AddBackslash(carpeta) + 'unins000.exe') or
             FileExists(AddBackslash(carpeta) + 'VERSION'));
end;

function VersionEnCarpeta(carpeta: String): String;
var
  contenido: AnsiString;
begin
  Result := '';
  if carpeta = '' then
    Exit;
  if LoadStringFromFile(AddBackslash(carpeta) + 'VERSION', contenido) then
    Result := Trim(String(contenido));
end;

function QuitarAnterior(): Boolean;
var
  desinstalador, previa, mensaje, carpeta: String;
  respuesta, codigo, espera: Integer;
begin
  Result := True;

  desinstalador := DesinstaladorPrevio();
  carpeta := LeerPrevio('Inno Setup: App Path');

  // Sin entrada en el registro, preguntarle al disco por la carpeta donde
  // BIMNEMO se instala siempre.
  if desinstalador = '' then
  begin
    carpeta := CarpetaPorDefecto();
    if not HayInstalacionEn(carpeta) then
      Exit;
    if FileExists(AddBackslash(carpeta) + 'unins000.exe') then
      desinstalador := AddBackslash(carpeta) + 'unins000.exe';
  end;

  RutaPrevia := carpeta;

  previa := VersionPrevia();
  if previa = '' then
    previa := VersionEnCarpeta(carpeta);

  // Hay una instalación pero no queda desinstalador con el que quitarla. No
  // se borra nada a mano: avisar y dejar que decida.
  if desinstalador = '' then
  begin
    SuppressibleMsgBox(
      'En ' + carpeta + ' ya hay un BIMNEMO, pero no encuentro su ' +
      'desinstalador.' + #13#10#13#10 +
      'Se instalará encima. Tus documentos, tus memorias y tu configuración ' +
      'no se tocan, pero pueden quedar ficheros sueltos de la versión ' +
      'anterior.',
      mbInformation, MB_OK, IDOK);
    Exit;
  end;

  if previa <> '' then
    mensaje := 'Ya tienes BIMNEMO ' + previa + ' instalado.'
  else
    mensaje := 'Ya tienes BIMNEMO instalado.';

  // `SuppressibleMsgBox` y no `MsgBox`: un `MsgBox` normal sale **también**
  // en una instalación silenciosa, y allí no hay quien lo cierre — la
  // instalación se queda colgada para siempre esperando un clic. Así, en
  // silencio se toma la respuesta de abajo (desinstalar) y sigue sola.
  respuesta := SuppressibleMsgBox(
    mensaje + #13#10#13#10 +
    'Conviene desinstalarlo antes para no mezclar ficheros de las dos ' +
    'versiones.' + #13#10#13#10 +
    'Tus documentos, tus memorias y tu configuración NO se borran: se ' +
    'quedan donde están y la instalación nueva los encuentra igual.' + #13#10 +
    '' + #13#10 +
    '¿Desinstalar la versión anterior ahora?',
    mbConfirmation, MB_YESNOCANCEL, IDYES);

  if respuesta = IDCANCEL then
  begin
    Result := False;
    Exit;
  end;

  if respuesta = IDNO then
  begin
    // Se queda como estaba: se instala encima y se respeta su carpeta.
    RutaPrevia := '';
    Exit;
  end;

  if not Exec(desinstalador, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART',
              '', SW_SHOW, ewWaitUntilTerminated, codigo) then
  begin
    MsgBox('No se pudo ejecutar el desinstalador anterior. Se continuará ' +
           'instalando encima.', mbInformation, MB_OK);
    Exit;
  end;

  // Esperar al proceso NO basta. El desinstalador de Inno se copia al
  // temporal, lanza esa copia y **el original sale de inmediato**: el `Exec`
  // de arriba vuelve con la desinstalación aún corriendo, y empezaríamos a
  // copiar ficheros nuevos mientras la copia vieja los va borrando.
  //
  // Se espera a que `unins000.exe` desaparezca, que es lo último que hace al
  // terminar. Se mira el fichero y no el registro porque cuando la
  // instalación se encontró por la carpeta no hay entrada que vigilar.
  espera := 0;
  while (espera < 120) and FileExists(desinstalador) do
  begin
    Sleep(500);
    espera := espera + 1;
  end;

  if FileExists(desinstalador) then
    MsgBox('La desinstalación anterior está tardando más de lo normal. Se ' +
           'continuará, pero si algo queda raro, desinstala a mano y vuelve ' +
           'a instalar.', mbInformation, MB_OK);
end;

// Si hay una instalación previa corriendo, sus ficheros están en uso y la
// copia falla a medias. Se avisa antes en vez de dejar la instalación rota.
function InitializeSetup(): Boolean;
var
  Resultado: Integer;
begin
  Result := True;
  if CheckForMutexes('BIMNEMO_EN_MARCHA') then
  begin
    // En silencio se cancela (IDCANCEL): mejor que la instalación falle con
    // un código de error a que machaque ficheros en uso y deje la aplicación
    // rota sin que nadie se entere.
    Resultado := SuppressibleMsgBox(
      'BIMNEMO parece estar abierto.' + #13#10#13#10 +
      'Ciérralo antes de continuar; si no, la instalación puede quedar a medias.',
      mbError, MB_RETRYCANCEL, IDCANCEL);
    Result := (Resultado = IDRETRY);
    if not Result then
      Exit;
  end;

  Result := QuitarAnterior();
end;

// La detección de arriba mira el registro y la carpeta donde BIMNEMO se
// instala siempre. Si en la pantalla de destino se elige otra a mano, y ahí
// ya hay un BIMNEMO, nadie lo habría mirado. Aquí se cierra ese hueco.
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID <> wpSelectDir then
    Exit;
  if not HayInstalacionEn(WizardDirValue) then
    Exit;
  // Si es la misma por la que ya se preguntó, no repetir.
  if CompareText(RemoveBackslash(WizardDirValue),
                 RemoveBackslash(RutaPrevia)) = 0 then
    Exit;

  Result := SuppressibleMsgBox(
    'En esa carpeta ya hay un BIMNEMO instalado.' + #13#10#13#10 +
    'Si continúas se instalará encima y pueden quedar mezclados ficheros de ' +
    'las dos versiones. Tus documentos, tus memorias y tu configuración no ' +
    'se tocan.' + #13#10#13#10 +
    'Lo más limpio es desinstalar el anterior y volver a empezar.' + #13#10 +
    '' + #13#10 +
    '¿Continuar de todas formas?',
    mbConfirmation, MB_YESNO, IDYES) = IDYES;
end;
