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
;
; Y se llama `bimnemo.exe`, no `pythonw.exe`: es el mismo intérprete, sellado
; con el icono y la descripción de BIMNEMO por `scripts\release\sellar.py`.
; Así el Administrador de tareas dice «BIMNEMO» y no «Python», que es lo único
; que el usuario tiene para reconocer su propio programa.
;
; Y está en la raíz, no dentro de `python\`: quien abre la carpeta de BIMNEMO
; tiene que encontrarse el programa en la puerta, no enterrado dos niveles
; abajo entre ficheros del intérprete.
#define Ejecutable  "bimnemo.exe"
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

; Deja un registro en la carpeta temporal en cada ejecución. Cuesta nada y es
; la diferencia entre saber qué pasó y adivinarlo: sin esto, un instalador que
; se porta raro en el ordenador de un cliente no deja nada que mirar.
SetupLogging=yes
DefaultGroupName={#Nombre}
DisableProgramGroupPage=yes
OutputDir=salida
OutputBaseFilename=BIMNEMO-{#Version}-instalador
; Para que el propio instalador se vea como BIMNEMO en la carpeta de descargas
; y en el aviso de Windows, no como un ejecutable anónimo.
SetupIconFile=bimnemo.ico
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

; Los perfiles de Chromium de las versiones hasta la 1.3, cuando la ventana
; era un Chrome. Desde la 1.4 es nativa y nadie vuelve a abrirlos: son 35 MB
; de caché de navegador que se quedarían para siempre. El segundo nombre es
; el de las primeras versiones, antes de mover el perfil fuera del repositorio.
Type: filesandordirs; Name: "{localappdata}\BIMNEMO\chromium-profile"
Type: filesandordirs; Name: "{app}\chromium-profile"
Type: filesandordirs; Name: "{app}\perfil-chrome"

[Icons]
; Sin `IconFilename`: el icono ya va **dentro** de `bimnemo.exe`, sellado al
; empaquetar. Referenciar un `.ico` suelto además sería tener el mismo icono
; en dos sitios y un día uno de los dos se quedaría viejo.
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
  desinstalador, previa, mensaje, carpeta, modo: String;
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

  // `/SILENT` y no `/VERYSILENT`: la diferencia es que `/SILENT` **sí enseña
  // la ventana de progreso** de la desinstalación. Con `/VERYSILENT` no se ve
  // nada: el instalador se quedaba congelado unos segundos sin explicar por
  // qué, que desde fuera es un programa colgado. Las preguntas las quita
  // `/SUPPRESSMSGBOXES`, no `/VERYSILENT`.
  //
  // Si la instalación sí es silenciosa de verdad, se respeta y no se enseña
  // ninguna ventana.
  if WizardSilent then
    modo := '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART'
  else
    modo := '/SILENT /SUPPRESSMSGBOXES /NORESTART';

  if not Exec(desinstalador, modo,
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

// --- BIMNEMO abierto -------------------------------------------------------
//
// Si hay una instalación previa corriendo, sus ficheros están en uso y la
// copia falla a medias. Se avisa antes en vez de dejar la instalación rota.
//
// Pero decir «ciérralo» no siempre basta: **BIMNEMO puede estar en marcha sin
// ninguna ventana**. El motor y la ventana son dos procesos, y si la ventana
// se cierra mal el motor se queda vivo por detrás. Entonces el usuario lee
// «ciérralo» mirando un escritorio vacío y se queda atascado sin salida. Así
// que se ofrece cerrarlo desde aquí.

function CarpetaDeLaInstalacion(): String;
begin
  Result := LeerPrevio('Inno Setup: App Path');
  if (Result = '') and HayInstalacionEn(CarpetaPorDefecto()) then
    Result := CarpetaPorDefecto();
end;

// En WQL la barra invertida es el carácter de escape, así que hay que
// doblarla o ninguna ruta casa con nada.
function ParaWQL(ruta: String): String;
begin
  Result := ruta;
  StringChangeEx(Result, '\', '\\', True);
end;

// Mata lo que devuelva la consulta. Devuelve cuántos, o -1 si ni se pudo
// preguntar (sin WMI no hay nada que hacer, pero tampoco se rompe nada).
function TerminarPorConsulta(consulta: String): Integer;
var
  localizador, servicios, conjunto, proceso: Variant;
  i: Integer;
begin
  Result := 0;
  try
    localizador := CreateOleObject('WbemScripting.SWbemLocator');
    servicios := localizador.ConnectServer('', 'root\CIMV2');
    conjunto := servicios.ExecQuery(consulta);
    for i := 0 to conjunto.Count - 1 do
    begin
      proceso := conjunto.ItemIndex(i);
      proceso.Terminate();
      Result := Result + 1;
    end;
  except
    Result := -1;
  end;
end;

// Cierra BIMNEMO entero. **Solo BIMNEMO.**
//
// La tentación es un `taskkill /IM pythonw.exe`, y sería un desastre: se
// llevaría por delante cualquier otro Python del usuario —un script suyo a
// medias, otra aplicación— sin que él lo sepa.
//
// Son DOS cosas distintas, y esto costó una prueba fallida entenderlo:
//
//  1. **La ventana**, en las versiones hasta la 1.3, es un Chromium *del
//     sistema* —desde la 1.4 es nativa y vive en `bimnemo.exe`—. Se sigue
//     cerrando porque quien actualiza viene de una de ésas. Su ejecutable está en
//     `Program Files`, no en la carpeta de BIMNEMO, así que filtrar por la
//     ruta del ejecutable no la tocaba: el motor moría y la ventana se
//     quedaba en pantalla, enseñando la página que ya tenía cargada. Desde
//     fuera parecía que el botón de cerrar no hacía nada y que BIMNEMO
//     seguía vivo mientras se desinstalaba.
//
//     Se reconoce por el perfil propio que se le pasa en la línea de
//     órdenes, que no comparte con ningún otro navegador del usuario.
//
//  2. **El motor y el lanzador** sí viven en la carpeta de la instalación.
//
// Se repite hasta que no queda ninguno porque el lanzador vigila al motor y
// lo vuelve a levantar si se muere: matarlos en el orden equivocado dejaría
// un motor recién nacido con los ficheros abiertos.
function CerrarBimnemo(carpeta: String): Integer;
var
  vuelta, cerrados, n: Integer;
  perfil: String;
begin
  Result := 0;
  perfil := ExpandConstant('{localappdata}\BIMNEMO\chromium-profile');

  for vuelta := 1 to 5 do
  begin
    cerrados := 0;

    n := TerminarPorConsulta(
      'SELECT ProcessId FROM Win32_Process WHERE CommandLine LIKE "%' +
      ParaWQL(perfil) + '%"');
    if n > 0 then
      cerrados := cerrados + n;

    if carpeta <> '' then
    begin
      n := TerminarPorConsulta(
        'SELECT ProcessId FROM Win32_Process WHERE ExecutablePath LIKE "' +
        ParaWQL(AddBackslash(carpeta)) + '%"');
      if n > 0 then
        cerrados := cerrados + n;
    end;

    Result := Result + cerrados;
    if cerrados = 0 then
      Break;
    Sleep(700);
  end;
end;

function AsegurarCerrado(): Boolean;
var
  respuesta: Integer;
begin
  Result := True;
  while CheckForMutexes('BIMNEMO_EN_MARCHA') do
  begin
    // En silencio se contesta que sí (IDYES): cerrarlo es lo que permite
    // seguir. Si aun así no se puede, se cancela unas líneas más abajo.
    respuesta := SuppressibleMsgBox(
      'BIMNEMO está abierto, y hay que cerrarlo antes de continuar: si no, ' +
      'la instalación puede quedar a medias.' + #13#10 +
      '' + #13#10 +
      'Si no ves ninguna ventana de BIMNEMO, es que el motor se quedó en ' +
      'marcha por detrás. Puedo cerrarlo yo; no afecta a nada más de tu ' +
      'ordenador, ni a tus documentos.' + #13#10 +
      '' + #13#10 +
      '¿Lo cierro ahora?',
      mbConfirmation, MB_YESNOCANCEL, IDYES);

    if respuesta = IDCANCEL then
    begin
      Result := False;
      Exit;
    end;

    if respuesta = IDYES then
    begin
      if CerrarBimnemo(CarpetaDeLaInstalacion()) <> 0 then
        // Al proceso le lleva un instante morirse y soltar el mutex.
        Sleep(2000);

      if CheckForMutexes('BIMNEMO_EN_MARCHA') then
      begin
        if SuppressibleMsgBox(
             'No he conseguido cerrar BIMNEMO.' + #13#10 +
             '' + #13#10 +
             'Ciérralo a mano y reintenta. Si no encuentras su ventana, ' +
             'búscalo en el Administrador de tareas como «pythonw.exe» o ' +
             '«python.exe».',
             mbError, MB_RETRYCANCEL, IDCANCEL) = IDCANCEL then
        begin
          Result := False;
          Exit;
        end;
      end;
    end;
    // Con IDNO se vuelve a comprobar: el usuario lo está cerrando él mismo.
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := AsegurarCerrado();
  if not Result then
    Exit;

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
