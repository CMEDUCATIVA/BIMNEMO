# Cómo se construye el instalador de BIMNEMO

Para una persona o una IA que tenga que generar el instalador de Windows o
tocarlo. Cómo se publica y cómo se actualizan los clientes después está en
[`como_actualizar.md`](como_actualizar.md).

---

## Qué sale

`installer\salida\BIMNEMO-X.Y.Z-instalador.exe`: unos **96 MB**. Instala unos
**376 MB** que llevan:

- el programa (lo que git versiona, sin lo que es de desarrollo);
- un **Python 3.14 portable** con todas las dependencias y Qt: el cliente no
  instala Python ni nada;
- `bimnemo.exe` en la raíz, con el icono y la descripción de BIMNEMO.

Se instala **sin permisos de administrador**, por defecto en
`%LOCALAPPDATA%\Programs\BIMNEMO`, y crea los accesos directos «BIMnemo».

---

## Construirlo

### Requisitos

- Windows, con la copia de desarrollo y su `.venv` funcionando:
  `.venv\Scripts\python.exe -m pip install -e ".[api,escritorio]"`.
- El Python base del `.venv` (el `home` de `.venv\pyvenv.cfg`, hoy
  `C:\Python314`): de ahí sale el intérprete portable.
- [Inno Setup 6](https://jrsoftware.org/isdl.php) en
  `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`.
- Pillow en el `.venv` (lo usa `icono.py`).

### De una vez

```bat
scripts\release\construir_instalador.bat v1.4.5
```

Sin argumento, usa lo que diga `VERSION`. Hace los dos pasos de abajo.

### Paso a paso

```bash
.venv/Scripts/python.exe scripts/release/empaquetar.py v1.4.5
MSYS_NO_PATHCONV=1 "/c/Program Files (x86)/Inno Setup 6/ISCC.exe" /Q /DVersion=1.4.5 "installer\\BIMNEMO.iss"
```

> **Desde Git Bash, `MSYS_NO_PATHCONV=1` es obligatorio.** Sin él, Git Bash
> convierte `/Q` y `/DVersion=…` en rutas de disco, e Inno Setup responde
> «You may not specify more than one script filename».

Tiempos medidos: el empaquetado, un par de minutos; la compresión (`lzma2`
máxima), unos minutos más.

**El número va sin la `v`** en `/DVersion` (el `.bat` la quita solo). El
empaquetado sí la lleva, porque escribe el `VERSION` de la instalación, que
es con lo que compara el actualizador.

---

## Qué hace `empaquetar.py`

Monta en `installer\salida\app` exactamente lo que se instalará. Por orden:

1. **Limpia** `installer\salida\app`.
2. **Copia el programa**: la lista de `git ls-files`, menos lo que
   `reparto.sobra_en_cliente()` considera de desarrollo (pruebas, Docker,
   Kubernetes, `scripts/`, `installer/`, `lightrag_webui/`, los README
   traducidos, este documento…). Unos 1.086 ficheros fuera, unos 352 dentro.
   > **Trampa:** sale de `git ls-files`, así que un fichero **nuevo que no se
   > ha añadido a git no entra**, aunque esté en disco. Y lo que sí entra se
   > copia **del disco**, con los cambios sin commit. Antes de empaquetar una
   > versión, `git status` limpio.
   >
   > La misma función `sobra_en_cliente` la usa el actualizador al desplegar
   > un zip: por eso la lista vive en `lightrag/api/bimnemo/reparto.py` y no
   > aquí. Si se añade algo de desarrollo al repositorio, se añade allí.
3. **Escribe `VERSION`** con la versión pedida.
4. **Monta el Python portable** en `app\python\`:
   - `python.exe`, `pythonw.exe`, las DLL, `DLLs\` y `Lib\` del Python base
     (sin `test`, `idlelib`, `tkinter`, `turtledemo`, `ensurepip`);
   - `Lib\site-packages` desde el `.venv`.
   Un `venv` de Windows **no lleva Python dentro**, solo apunta al del
   sistema; copiarlo tal cual daba un programa que solo arrancaba en
   ordenadores con Python 3.14 en `C:\Python314`. Así se rompieron las
   instalaciones 1.1.0 y 1.2.0.
5. **Quita el enlace editable** (`__editable__…pth`, `direct_url.json`): en
   desarrollo apunta a la carpeta del repositorio, que en el cliente no existe.
6. **Poda Qt**, de 124 a 86 MB: fuera QML/Quick, Designer, cabeceras,
   `metatypes`, traducciones que no sean `es`/`en`, los `.pyd` de módulos que
   no se importan (se quedan `QtCore`, `QtGui`, `QtWidgets`, `QtNetwork`,
   `QtSvg`) y DLL como `Qt6DBus`. **`opengl32sw.dll` se queda a propósito**
   (~20 MB): es el OpenGL por software que usa Qt en máquinas virtuales y
   escritorio remoto, donde no hay aceleración.
7. **Pone la cara de BIMNEMO** (`_poner_cara`): copia `python\pythonw.exe` a
   `python\bimnemo.exe` y `python\python.exe` a `python\bimnemo-consola.exe`,
   y las sella con icono y descripción (ver abajo). Son **copias**:
   `python.exe` sigue haciendo falta, es el que usa `pip` al actualizar.
8. **La puerta de entrada**: `bimnemo.exe` en la **raíz** de la instalación,
   con `python314.dll`, `python3.dll`, `vcruntime140.dll` y
   `vcruntime140_1.dll` al lado.
   > Sin esas DLL al lado, Windows busca `python314.dll` por el PATH y carga
   > la del Python del sistema, si lo hay: en un ordenador limpio no arranca.
9. **Los `._pth`**: Python busca su fichero de rutas **por el nombre del
   ejecutable** (`bimnemo.exe` → `bimnemo._pth`). Se escribe uno por cada
   nombre (`python`, `pythonw`, `bimnemo`, `bimnemo-consola`); sin él, el
   intérprete renombrado pierde el modo aislado y sale a buscar una
   instalación de Python del sistema.
10. **Comprueba que no quedan rutas de desarrollo**: busca la ruta del
    repositorio dentro de `.pth`, `.py`, `.cfg`, `.json`… Si aparece, para.
    Es la comprobación que distingue un paquete que funciona en otro
    ordenador de uno que solo funciona en este.

### Identidad: `icono.py` y `sellar.py`

- `scripts/release/icono.py` dibuja `installer/bimnemo.ico` (16 a 256 px) con
  **la misma función que la ventana**, `nativo/iconos.cuadrado()`: el cerebro
  blanco sobre el cuadrado azul. Así el icono del instalador, el de la barra
  de tareas y el del encabezado no pueden separarse.
- `scripts/release/sellar.py` escribe en un `.exe` el icono y la
  `VERSIONINFO`, con `BeginUpdateResourceW`/`UpdateResourceW`. La
  descripción es `bimnemo`, en minúscula: es lo que el Administrador de
  tareas enseña como nombre del proceso. Al borrar los recursos se borra
  también el manifiesto (DPI, rutas largas), así que se lee antes y se
  vuelve a escribir.

---

## Qué hace el instalador (`installer/BIMNEMO.iss`)

### Dónde instala

- `PrivilegesRequired=lowest`: **sin administrador**. BIMNEMO se actualiza
  reescribiendo sus propios ficheros; en *Program Files* eso pediría permiso
  en cada actualización.
- Carpeta por defecto: `{userpf}\BIMNEMO` =
  `%LOCALAPPDATA%\Programs\BIMNEMO`, la de los programas de un usuario (la
  misma que usan VS Code o Discord). Se puede cambiar.
- Si había una instalación, propone **su** carpeta (`DirPropuesto`): ahí
  están el `.env`, `rag_storage\` e `inputs\` de ese cliente.

### Antes de instalar: lo que ya hubiera

`InitializeSetup` hace dos cosas, en este orden:

1. **Que BIMNEMO no esté abierto** (`AsegurarCerrado`). Si lo está, ofrece
   cerrarlo. Lo reconoce por el mutex `BIMNEMO_EN_MARCHA` (lo crea
   `desktop.marcar_en_marcha`; el nombre tiene que coincidir en los dos
   sitios) y lo cierra matando los procesos cuyo ejecutable está en la
   carpeta de la instalación. En versiones hasta la 1.3, además, el Chrome
   con el perfil de BIMNEMO. **Nunca** `taskkill /IM pythonw.exe`: se llevaría
   cualquier otro Python del usuario.
2. **Si ya hay un BIMNEMO instalado** (`QuitarAnterior`), dice qué versión y
   ofrece desinstalarlo primero. Lo busca en el registro
   (`…\Uninstall\{B1MN3M0-0000-4000-A000-BIMNEMO00001}_is1`) y, si no consta,
   **en disco**: en la carpeta nueva y en la de antes de la 1.4
   (`%LOCALAPPDATA%\BIMNEMO`). Un `unins000.exe` o un `VERSION` bastan para
   darla por instalada.

Si en la pantalla de destino se elige a mano otra carpeta que ya tiene un
BIMNEMO, avisa antes de instalar encima.

### Durante

- `[InstallDelete]` borra restos de versiones viejas: el `.venv` de la 1.2.0
  y anteriores (salvo en una copia de desarrollo, que tiene `.git`), los
  perfiles de Chromium de la época web y los accesos directos «BIMNEMO.lnk»
  —Windows no distingue mayúsculas: sin borrarlos, el nuevo «BIMnemo» se
  escribiría encima y conservaría el nombre viejo—.
- `[Files]` copia `installer\salida\app\*` entero.
- `[Icons]`: «BIMnemo» en el menú Inicio y, si se marca, en el escritorio.
  Apuntan a `{app}\bimnemo.exe -m lightrag.api.bimnemo.desktop` con
  directorio de trabajo `{app}`: el motor lee el `.env` y crea `rag_storage\`
  en el directorio de trabajo. También «Cómo actualizar» (abre
  `como_actualizar.md`) y «Diagnóstico (con consola)» (`BIMNEMO.bat --consola`).

### Al desinstalar

**Los datos se quedan**: `.env`, `inputs\` y `rag_storage\` no los instaló el
instalador y no los borra. Solo se limpia lo que genera el programa al
funcionar (`__pycache__`, `lightrag.log`). Un desinstalador que se lleva
meses de trabajo es un desastre sin vuelta atrás.

---

## Comprobar antes de repartirlo

```bash
# 1. Que no viaja ninguna copia del .env (tiene que no encontrar nada)
ls installer/salida/app/.env installer/salida/app/.env.* 2>/dev/null

# 2. La versión
cat installer/salida/app/VERSION

# 3. Que el paquete funciona solo, sin el Python del sistema ni el repositorio
cd /c && PATH="/c/Windows/System32:/c/Windows" \
  "<repo>/installer/salida/app/python/bimnemo-consola.exe" -c \
  "import sys, lightrag, PySide6; print(sys.executable); print(lightrag.__file__); print(PySide6.__file__)"
```

Las tres rutas del paso 3 tienen que estar **dentro de `installer\salida\app`**.
Si alguna apunta al repositorio o a `C:\Python314`, el instalador solo
funcionaría en este ordenador.

Y la prueba de verdad, en una máquina o usuario sin BIMNEMO: instalar,
comprobar que sale el cuadro «Crea tu primera memoria» y que en el
Administrador de tareas los procesos se llaman `bimnemo`.

---

## Adjuntarlo a una versión publicada

```bash
.venv/Scripts/python.exe scripts/release/publicar.py v1.4.5 notas.md installer/salida/BIMNEMO-1.4.5-instalador.exe
```

Crea la *release* y sube el `.exe` como *asset*. Hace falta que la etiqueta
ya esté en GitHub. El proceso completo de publicar está en
[`como_actualizar.md`](como_actualizar.md).

Para actualizar, los clientes **no** necesitan el instalador: les basta la
etiqueta. El instalador es para quien instala por primera vez, y para quien
viene de la 1.2 o la 1.3, cuyo actualizador no puede traer la ventana nueva.

---

## Trampas que ya costaron un fallo

- **Llaves en `[Code]`.** En `[Setup]` o `[Files]`, `{{` es una llave
  escapada; dentro de una cadena de Pascal son **dos llaves literales**. Con
  `{{B1MN3M0-…` en el código, la clave del registro no existía y la detección
  de instalaciones previas no saltaba nunca.
- **`MsgBox` en vez de `SuppressibleMsgBox`** bloquea para siempre una
  instalación silenciosa.
- **`/SILENT` y no `/VERYSILENT`** para la desinstalación previa: `/SILENT`
  enseña la barra de progreso; lo que quita las preguntas es
  `/SUPPRESSMSGBOXES`.
- **El desinstalador de Inno se copia a sí mismo al temporal** y el original
  sale enseguida: esperar al proceso no basta. Se espera a que desaparezca
  `unins000.exe` (hasta 60 s).
- **Pillow e `.ico`**: la imagen base tiene que ser la más grande, o Pillow
  descarta en silencio los tamaños mayores.
- **El paquete funciona en esta máquina aunque esté roto**, porque aquí sí
  están el repositorio y `C:\Python314`. Por eso existen las comprobaciones
  del paso 3 y la de rutas de desarrollo.

---

## En la copia de desarrollo

`scripts/release/cara_local.py` hace lo mismo que el paso 7 con el `.venv`:
copia el intérprete **base** (no el `pythonw.exe` del `.venv`, que es un
redirector que lanza el del sistema como hijo) a `.venv\Scripts\bimnemo.exe`,
con sus DLL, y lo sella. `desktop.py` se relanza con él si existe, así que en
desarrollo también se ve «bimnemo» en el Administrador de tareas.
