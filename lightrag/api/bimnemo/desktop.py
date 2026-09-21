"""BIMNEMO como aplicación de escritorio.

Arranca el servidor LightRAG y abre BIMNEMO en una **ventana propia** de
Chromium, sin barra de direcciones, sin pestañas y con su propio perfil. Para
quien lo usa es un programa, no una página web; por debajo sigue siendo el
mismo servidor, así que la API y Swagger siguen disponibles para cualquier
agente que se conecte.

Tres decisiones que conviene no deshacer:

* **Perfil aparte** (``--user-data-dir``). Sin él, Chromium detecta la
  instancia que el usuario ya tenga abierta, le delega la ventana y termina
  al instante — y este proceso creería que la aplicación se ha cerrado. El
  perfil propio también evita que BIMNEMO herede sesiones, extensiones o
  cookies del navegador personal.
* **El servidor es un subproceso**, no un hilo. ``lightrag.api.lightrag_server``
  lee ``sys.argv`` al importarse y monta su propio ciclo de vida asíncrono;
  meterlo en este proceso obliga a pelearse con ambas cosas para no ganar nada.
* **Si el puerto ya responde, no se arranca un segundo servidor.** Abrir
  BIMNEMO dos veces debe dar dos ventanas contra la misma memoria, no dos
  motores escribiendo sobre los mismos ficheros — que es justo lo que los
  almacenes respaldados por fichero no toleran.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from lightrag.api.bimnemo.runtime import (
    CONFIGURABLE_ENV_KEYS,
    RESTART_EXIT_CODE,
)

UI_PATH = "/bimnemo-app/"
HEALTH_PATH = "/health"

# Cuánto se espera a que el servidor conteste antes de rendirse. La primera
# vez tarda más: importa el motor, crea los almacenes y valida la config.
SERVER_TIMEOUT_SECONDS = 180.0
POLL_SECONDS = 0.4


def _repo_root() -> Path:
    """Raíz del repositorio, subiendo desde este fichero."""
    return Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Localizar Chromium
# ---------------------------------------------------------------------------


def _playwright_builds() -> list[Path]:
    """Chromium «Chrome for Testing» que Playwright haya dejado en la máquina.

    Va aparte y **al final** de la lista por una razón medida, no por gusto:
    ese build no sirve como navegador de aplicación. Comprobado en Windows
    con `chromium-1243`, la ventana `--app` **se queda en blanco** y nunca
    pinta la página, y encima muestra un cartel fijo que dice que esa versión
    solo sirve para pruebas automatizadas. Es un binario pensado para
    conducirse por CDP, que es justo para lo que se descargó aquí.
    """
    roots: list[Path] = []
    playwright_home = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if playwright_home:
        roots.append(Path(playwright_home))
    roots.append(Path.home() / "AppData" / "Local" / "ms-playwright")

    builds: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        # Mayor número de build primero: es la instalación más reciente.
        versions = sorted(
            (d for d in root.glob("chromium-*") if d.is_dir()),
            key=lambda d: d.name,
            reverse=True,
        )
        for version in versions:
            builds.append(version / "chrome-win64" / "chrome.exe")
            builds.append(version / "chrome-linux" / "chrome")
    return builds


def is_chrome_for_testing(path: Path) -> bool:
    """¿Es este binario el build de pruebas de Playwright?"""
    return "ms-playwright" in str(path).replace("\\", "/").lower()


def _candidate_browsers() -> list[Path]:
    """Chromium candidatos, en el orden en que conviene probarlos.

    1. El que viaje con la aplicación (``chromium/`` junto al repositorio):
       un despliegue autocontenido no depende de nada instalado.
    2. Los navegadores del sistema. En Windows **Edge siempre está**, forma
       parte del sistema operativo, así que este escalón nunca queda vacío.
    3. El build de pruebas de Playwright, solo como último recurso y
       avisando — ver :func:`_playwright_builds`.
    """
    candidates: list[Path] = []

    bundled_names = ("chrome.exe", "chrome", "chromium.exe", "chromium")
    bundled_dir = _repo_root() / "chromium"
    candidates.extend(bundled_dir / name for name in bundled_names)

    program_files = [
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    relatives = [
        r"Google\Chrome\Application\chrome.exe",
        r"Microsoft\Edge\Application\msedge.exe",
        r"Chromium\Application\chrome.exe",
        r"BraveSoftware\Brave-Browser\Application\brave.exe",
    ]
    for base in program_files:
        if not base:
            continue
        for relative in relatives:
            candidates.append(Path(base) / relative)

    candidates.extend(_playwright_builds())
    return candidates


def find_chromium(explicit: str | None = None) -> Path | None:
    """Devuelve el Chromium a usar, o ``None`` si no hay ninguno."""
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None

    for candidate in _candidate_browsers():
        if candidate.is_file():
            return candidate

    # Última oportunidad: que esté en el PATH (habitual en Linux).
    for name in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        found = shutil.which(name)
        if found:
            return Path(found)

    return None


# ---------------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------------


def port_is_open(host: str, port: int, timeout: float = 0.5) -> bool:
    """¿Hay alguien escuchando ya en ese puerto?"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def health_responds(base_url: str, timeout: float = 2.0) -> bool:
    """¿Contesta el servidor a ``/health``?

    Un 401/403 también cuenta: significa que el servidor está levantado y
    pidiendo credenciales, no que esté caído.
    """
    try:
        with urllib.request.urlopen(f"{base_url}{HEALTH_PATH}", timeout=timeout):
            return True
    except urllib.error.HTTPError as exc:
        return exc.code in (401, 403)
    except (urllib.error.URLError, OSError):
        return False


def _server_command(host: str, port: int) -> list[str]:
    """Cómo arrancar el servidor desde el mismo entorno que este proceso."""
    script = Path(sys.executable).parent / (
        "lightrag-server.exe" if os.name == "nt" else "lightrag-server"
    )
    if script.is_file():
        return [str(script), "--host", host, "--port", str(port)]
    # Sin el script instalado, el módulo sirve igual.
    return [
        sys.executable,
        "-m",
        "lightrag.api.lightrag_server",
        "--host",
        host,
        "--port",
        str(port),
    ]


def start_server(host: str, port: int, *, quiet: bool) -> subprocess.Popen:
    """Arranca el servidor como subproceso.

    ``PYTHONUTF8`` no es opcional en Windows: el banner de arranque de
    LightRAG lleva caracteres que una consola cp1252 no sabe escribir, y sin
    esto el servidor muere con ``UnicodeEncodeError`` antes de escuchar.
    """
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    # El motor hace ``load_dotenv(override=False)``: lo que ya está en el
    # entorno gana sobre el fichero. Así que si el lanzador lleva en el suyo
    # una copia vieja de estas variables —basta con que algún import suyo haya
    # cargado el ``.env`` alguna vez— el motor arranca con la configuración
    # anterior y nunca ve la que el usuario acaba de guardar.
    #
    # Eso hacía que «Guardar» + «Reiniciar» no sirviera de nada y solo
    # funcionase cerrar y volver a abrir BIMNEMO. Se quitan del entorno del
    # hijo para que las lea del fichero, que es donde las escribe la pantalla
    # de configuración y por tanto la única fuente que puede estar al día.
    for clave in CONFIGURABLE_ENV_KEYS:
        env.pop(clave, None)
    # Le dice al motor que hay un supervisor detrás, así la pantalla de
    # configuración puede prometer que la ventana vuelve sola tras reiniciar.
    env["BIMNEMO_SUPERVISED"] = "1"

    creation_flags = 0
    stdout = None
    if quiet and os.name == "nt":
        # Sin ventana de consola: es una aplicación, no un script.
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        stdout = subprocess.DEVNULL

    return subprocess.Popen(
        _server_command(host, port),
        env=env,
        stdout=stdout,
        stderr=subprocess.STDOUT if stdout is not None else None,
        creationflags=creation_flags,
    )


def wait_for_server(
    base_url: str, process: subprocess.Popen | None, timeout: float
) -> bool:
    """Espera a que el servidor conteste, vigilando que no se haya muerto.

    Sondear hasta agotar el plazo contra un proceso que ya terminó es esperar
    por nada: si el subproceso cae, se corta en el acto y se informa.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return False
        if health_responds(base_url):
            return True
        time.sleep(POLL_SECONDS)
    return False


# ---------------------------------------------------------------------------
# Ventana
# ---------------------------------------------------------------------------


def _profile_dir() -> Path:
    """Perfil propio de la aplicación, fuera del repositorio.

    Va en el directorio de datos del usuario y no en el repo para que
    actualizar o reinstalar BIMNEMO no borre su estado de ventana, y para que
    el repositorio no acumule un perfil de navegador de cientos de megas.
    """
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    path = Path(base) / "BIMNEMO" / "chromium-profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def launch_window(
    chromium: Path, url: str, *, width: int, height: int
) -> subprocess.Popen:
    """Abre la ventana de la aplicación y devuelve su proceso."""
    args = [
        str(chromium),
        f"--app={url}",
        f"--user-data-dir={_profile_dir()}",
        f"--window-size={width},{height}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-features=Translate,OptimizationHints",
    ]
    return subprocess.Popen(args)


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bimnemo",
        description="Abre BIMNEMO como aplicación de escritorio.",
    )
    parser.add_argument("--host", default=os.getenv("BIMNEMO_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("BIMNEMO_PORT", "9621"))
    )
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument(
        "--chromium",
        default=os.getenv("BIMNEMO_CHROMIUM"),
        help="Ruta a un Chromium concreto, si no quieres el que se detecte.",
    )
    parser.add_argument(
        "--consola",
        action="store_true",
        help="Deja visible la salida del servidor (para diagnosticar).",
    )
    parser.add_argument(
        "--navegador",
        action="store_true",
        help="No abre ventana propia: solo arranca el servidor.",
    )
    parser.add_argument(
        "--nativo",
        action="store_true",
        help="Abre la ventana nativa (en construcción) en vez de la de "
        "navegador.",
    )
    return parser.parse_args(argv)


def asegurar_env() -> None:
    """Crea el `.env` del ejemplo si no hay ninguno.

    Sin `.env`, LightRAG **pregunta por la consola** antes de arrancar
    (``utils_api.py``):

        response = input("Do you want to continue? (yes/NO): ")

    En una aplicación de escritorio esa pregunta no tiene quién la conteste:
    el motor revienta con ``EOFError`` y se cierra, y el lanzador se queda
    esperando hasta agotar su plazo. Desde fuera es «se queda arrancando».

    Le pasa a **toda instalación nueva**, porque el `.env` no viaja en el
    instalador —lleva las claves de quien empaqueta— así que es el primer
    arranque de todos los clientes.

    El fichero copiado no trae clave de API: el motor levanta y el panel se
    ve, pero indexar fallará hasta configurar un proveedor. Eso ya lo explica
    la pantalla de Configuración, y es mucho mejor que no arrancar.
    """
    raiz = _repo_root()
    env = raiz / ".env"
    if env.exists():
        return

    ejemplo = raiz / "env.example"
    try:
        if ejemplo.is_file():
            shutil.copyfile(ejemplo, env)
            print(
                "Primer arranque: se ha creado el fichero .env a partir de "
                "env.example. Configura tu proveedor de IA desde la pantalla "
                "de Configuración."
            )
        else:
            # Sin ejemplo del que partir, basta con que exista: lo único que
            # hay que evitar es la pregunta por consola.
            env.write_text(
                "# Creado por BIMNEMO en el primer arranque.\n"
                "HOST=127.0.0.1\n"
                "PORT=9621\n",
                encoding="utf-8",
            )
    except OSError as exc:
        # No poder escribirlo no debe impedir el arranque: el motor seguirá
        # avisando, y con consola se verá por qué.
        print(f"No se pudo crear el .env: {exc}", file=sys.stderr)


#: Nombre del mutex por el que el instalador reconoce que BIMNEMO está abierto.
#:
#: Tiene que coincidir **exactamente** con el que busca `installer\\BIMNEMO.iss`
#: (`AppMutex` y `CheckForMutexes`). Si cambia aquí, cambia allí.
MUTEX_EN_MARCHA = "BIMNEMO_EN_MARCHA"

#: El asa del mutex, viva mientras viva el proceso.
#:
#: Windows suelta un mutex cuando se cierra su última asa, así que **hay que
#: guardarla**: una variable local la recogería el recolector de basura y el
#: instalador dejaría de ver la aplicación a los pocos segundos de arrancar.
_asa_mutex: object | None = None


def marcar_en_marcha() -> None:
    """Publica una señal de «BIMNEMO está abierto» que el instalador ve.

    Instalar encima de una aplicación en marcha rompe la instalación a medias:
    Windows no deja sobrescribir un fichero en uso, así que `python.exe` y sus
    DLL se quedan con la versión vieja mientras el resto se actualiza.

    El instalador ya comprobaba este mutex, pero **nadie lo creaba**, así que
    la comprobación preguntaba por una señal que ningún proceso emitía y jamás
    saltaba. Esto es lo que faltaba.

    Se crea en el lanzador y no en el motor a propósito: el motor muere y
    renace en cada reinicio, y el mutex se apagaría durante esos segundos.
    """
    global _asa_mutex
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        asa = kernel32.CreateMutexW(None, False, MUTEX_EN_MARCHA)
        if asa:
            _asa_mutex = ctypes.c_void_p(asa)
    except (OSError, AttributeError) as exc:
        # Sin mutex la aplicación funciona igual; solo pierde el aviso del
        # instalador. No es motivo para no arrancar.
        print(f"No se pudo señalar que BIMNEMO está abierto: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    base_url = f"http://{args.host}:{args.port}"
    app_url = f"{base_url}{UI_PATH}"

    marcar_en_marcha()

    already_running = port_is_open(args.host, args.port) and health_responds(base_url)
    server: subprocess.Popen | None = None

    if already_running:
        print(f"BIMNEMO ya está en marcha en {base_url}; se abre otra ventana.")
    elif port_is_open(args.host, args.port):
        # Puerto ocupado por algo que no contesta a /health. Arrancar encima
        # fallaría con un error de socket que no dice nada útil.
        print(
            f"El puerto {args.port} está ocupado por otro programa.\n"
            f"Cierra ese programa o usa --port con otro número.",
            file=sys.stderr,
        )
        return 1
    else:
        asegurar_env()
        print(f"Arrancando el motor en {base_url} …")
        server = start_server(args.host, args.port, quiet=not args.consola)
        if not wait_for_server(base_url, server, SERVER_TIMEOUT_SECONDS):
            if server.poll() is not None:
                print(
                    "El motor se cerró al arrancar. Vuelve a lanzarlo con "
                    "--consola para ver el error.",
                    file=sys.stderr,
                )
            else:
                print(
                    f"El motor no respondió en {SERVER_TIMEOUT_SECONDS:.0f} s.",
                    file=sys.stderr,
                )
                server.terminate()
            return 1
        print("Motor listo.")

    if args.navegador:
        print(f"BIMNEMO  {app_url}\nSwagger  {base_url}/docs")
        print("Ctrl+C para detener.")
        try:
            if server is not None:
                server.wait()
        except KeyboardInterrupt:
            pass
        finally:
            _shutdown(server)
        return 0

    if args.nativo:
        # La ventana nativa está en construcción (ver
        # `docs/BIMNEMO_INTERFAZ_NATIVA.md`). Mientras no esté terminada hay
        # que pedirla a mano: así nunca hay una versión publicada en la que
        # el usuario se quede sin pantallas.
        from lightrag.api.bimnemo import BIMNEMO_VERSION, nativo

        if not nativo.disponible():
            print(
                "La ventana nativa necesita Qt (PySide6), que no está en "
                "este paquete.\nSe abre la de navegador.",
                file=sys.stderr,
            )
        else:
            return _con_ventana_nativa(nativo, base_url, args, server)

    chromium = find_chromium(args.chromium)
    if chromium is None:
        print(
            "No se encontró ningún Chromium para abrir la ventana.\n"
            f"Abre {app_url} en tu navegador, o vuelve a lanzarlo con\n"
            "--chromium <ruta a chrome.exe>.",
            file=sys.stderr,
        )
        if server is not None:
            # El motor queda en marcha: la aplicación sigue siendo usable
            # desde el navegador aunque no haya ventana propia.
            server.wait()
        return 1

    if is_chrome_for_testing(chromium):
        print(
            "AVISO: el único Chromium encontrado es el build de pruebas de "
            "Playwright.\nSu ventana puede quedarse en blanco y muestra un "
            f"cartel de versión de pruebas.\nSi pasa, abre {app_url} en tu "
            "navegador o instala Chrome o Edge.",
            file=sys.stderr,
        )

    print(f"Abriendo BIMNEMO con {chromium.name} …")
    window = launch_window(chromium, app_url, width=args.width, height=args.height)

    try:
        server = supervise(window, server, args.host, args.port, quiet=not args.consola)
    except KeyboardInterrupt:
        window.terminate()
    finally:
        _shutdown(server)

    return 0


# Freno de reinicios: si el motor se cae nada más arrancar varias veces
# seguidas, algo está mal de verdad (config rota, puerto robado, dependencia
# ausente) y reintentar en bucle solo esconde el error.
MAX_CONSECUTIVE_FAILURES = 3
FAST_FAILURE_SECONDS = 20.0
SUPERVISE_POLL_SECONDS = 0.5


class _CentinelaNativo:
    """Hace pasar la ventana nativa por un proceso ante el supervisor.

    `supervise` vigila la ventana preguntándole `poll()`, porque con la
    ventana de navegador la ventana **es** un proceso aparte. La nativa vive
    dentro de este mismo proceso, así que se le da algo con la misma forma.

    Es un adaptador de cinco líneas, y la alternativa era duplicar el
    supervisor entero para cambiar una condición del bucle.
    """

    def __init__(self) -> None:
        self._vivo = True

    def poll(self) -> int | None:
        return None if self._vivo else 0

    def terminate(self) -> None:
        self._vivo = False


def _con_ventana_nativa(nativo, base_url: str, args, server) -> int:
    """Abre la ventana nativa con el motor supervisado por detrás.

    **Sin esto el reinicio del motor no funciona**: la pantalla de
    configuración mata el proceso del motor a propósito, y si nadie lo
    levanta de nuevo la aplicación se queda sin motor para siempre. El
    supervisor va en un hilo porque Qt necesita el principal para sí.
    """
    import threading

    from lightrag.api.bimnemo import BIMNEMO_VERSION

    centinela = _CentinelaNativo()
    # En una caja para que el hilo pueda dejar ahí el motor vigente: tras un
    # reinicio, el que hay que cerrar al salir ya no es el de antes.
    caja = {"server": server}

    def vigilar() -> None:
        caja["server"] = supervise(
            centinela,
            server,
            args.host,
            args.port,
            quiet=not args.consola,
        )

    hilo = threading.Thread(target=vigilar, name="bimnemo-supervisor", daemon=True)
    hilo.start()

    try:
        return nativo.abrir(base_url, BIMNEMO_VERSION)
    finally:
        centinela.terminate()
        hilo.join(timeout=5)
        _shutdown(caja["server"])


def supervise(
    window: subprocess.Popen,
    server: subprocess.Popen | None,
    host: str,
    port: int,
    *,
    quiet: bool,
) -> subprocess.Popen | None:
    """Mantiene el motor en pie mientras la ventana siga abierta.

    Existe por la pantalla de configuración: cambiar de proveedor obliga a
    reiniciar el motor, y sin esto el usuario tendría que cerrar la aplicación
    y volver a abrirla cada vez. El motor se despide con
    :data:`RESTART_EXIT_CODE`, el supervisor lo vuelve a levantar y la ventana
    — que nunca se cerró — recarga sola.

    Devuelve el proceso de motor vigente, que es el que hay que cerrar al final.
    """
    base_url = f"http://{host}:{port}"
    consecutive_failures = 0

    while window.poll() is None:
        if server is None:
            time.sleep(SUPERVISE_POLL_SECONDS)
            continue

        code = server.poll()
        if code is None:
            time.sleep(SUPERVISE_POLL_SECONDS)
            continue

        requested = code == RESTART_EXIT_CODE
        print(
            "Reiniciando el motor …"
            if requested
            else f"El motor se cerró inesperadamente (código {code}); levantándolo …"
        )

        started_at = time.monotonic()
        server = start_server(host, port, quiet=quiet)
        if wait_for_server(base_url, server, SERVER_TIMEOUT_SECONDS):
            # Un reinicio pedido no cuenta como fallo aunque tarde: el freno
            # está para caídas, no para cambios de configuración.
            consecutive_failures = 0
            print("Motor listo.")
            continue

        if time.monotonic() - started_at < FAST_FAILURE_SECONDS:
            consecutive_failures += 1
        else:
            consecutive_failures = 1

        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            print(
                f"El motor no arranca tras {consecutive_failures} intentos.\n"
                "Revisa la configuración del .env y vuelve a lanzar BIMNEMO "
                "con --consola para ver el error.",
                file=sys.stderr,
            )
            window.terminate()
            break

    return server


def _shutdown(server: subprocess.Popen | None) -> None:
    """Cierra el motor si lo arrancamos nosotros.

    Si BIMNEMO ya estaba en marcha cuando se abrió esta ventana, ``server`` es
    ``None`` y no se toca: cerrar una ventana no debe tumbar el motor que otra
    ventana — o un agente conectado a la API — está usando.
    """
    if server is None or server.poll() is not None:
        return
    print("Cerrando el motor …")
    server.terminate()
    try:
        server.wait(timeout=15)
    except subprocess.TimeoutExpired:
        server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
