"""BIMNEMO como aplicación de escritorio.

Arranca el motor LightRAG y abre la **ventana nativa** de BIMNEMO (Qt). Para
quien lo usa es un programa; por debajo sigue siendo el mismo servidor, así
que la API y Swagger siguen disponibles para cualquier agente que se conecte.

Dos decisiones que conviene no deshacer:

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
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from lightrag.api.bimnemo.runtime import (
    CONFIGURABLE_ENV_KEYS,
    IDIOMA_POR_DEFECTO,
    RESTART_EXIT_CODE,
)

HEALTH_PATH = "/health"

# Cuánto se espera a que el servidor conteste antes de rendirse. La primera
# vez tarda más: importa el motor, crea los almacenes y valida la config.
SERVER_TIMEOUT_SECONDS = 180.0
POLL_SECONDS = 0.4


def _repo_root() -> Path:
    """Raíz del repositorio, subiendo desde este fichero."""
    return Path(__file__).resolve().parents[3]


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


def _somos_bimnemo() -> bool:
    """¿Corre esto dentro de un intérprete con la cara de BIMNEMO?"""
    return Path(sys.executable).stem.lower().startswith("bimnemo")


def _server_command(host: str, port: int, quiet: bool = True) -> list[str]:
    """Cómo arrancar el servidor desde el mismo entorno que este proceso.

    Si este proceso es `bimnemo.exe`, el motor también: con el script
    `lightrag-server.exe` salía un grupo aparte llamado «Python» en el
    Administrador de tareas —el script es un lanzador que arranca el Python
    del sistema—, y el usuario veía dos programas donde hay uno. Con
    `--consola` se deja el script, porque `bimnemo.exe` no tiene consola y
    la salida del motor es justo lo que se quiere ver.
    """
    if quiet and _somos_bimnemo():
        return [
            sys.executable,
            "-m",
            "lightrag.api.lightrag_server",
            "--host",
            host,
            "--port",
            str(port),
        ]
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
    if quiet:
        if os.name == "nt":
            # Sin ventana de consola: es una aplicación, no un script.
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        # A un fichero y no a la nada: sin consola, es lo único que queda para
        # saber por qué el motor no arrancó (ver avisar_fallo_de_arranque).
        try:
            stdout = open(registro_del_motor(), "w", encoding="utf-8", errors="replace")
        except OSError:
            stdout = subprocess.DEVNULL

    try:
        return subprocess.Popen(
            _server_command(host, port, quiet),
            env=env,
            stdout=stdout,
            stderr=subprocess.STDOUT if stdout is not None else None,
            creationflags=creation_flags,
        )
    finally:
        # El hijo ya tiene su copia del fichero; la nuestra sobra.
        if stdout not in (None, subprocess.DEVNULL):
            stdout.close()


#: Lo que el motor dijo en su último arranque. Se pisa en cada uno.
REGISTRO_DEL_MOTOR = "bimnemo_motor.log"


def registro_del_motor() -> Path:
    return _repo_root() / REGISTRO_DEL_MOTOR


def _leer_registro(maximo: int = 200_000) -> str:
    """El final del registro del motor, o vacío si no hay."""
    try:
        with registro_del_motor().open("rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - maximo))
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


_ERROR_FINAL = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception|Exit)\b.*$", re.MULTILINE)


def _ultimo_error(registro: str) -> str:
    """La línea del error con que terminó la traza, o la última que haya."""
    errores = _ERROR_FINAL.findall(registro)
    if errores:
        return errores[-1].strip()[:600]
    lineas = [l.strip() for l in registro.splitlines() if l.strip()]
    return lineas[-1][:600] if lineas else ""


TITULO_FALLO = "BIMNEMO no ha podido arrancar"


def _dialogo(texto: str, *, pregunta: bool = False) -> bool:
    """Un cuadro de Windows. Con ``pregunta``, Sí/No y devuelve si fue Sí.

    Es el de Windows y no uno de Qt a propósito: sirve antes de que exista la
    ventana y desde el hilo del supervisor, y la ventana corre sin consola,
    así que un ``print`` aquí no lo lee nadie.
    """
    print(texto, file=sys.stderr)
    if os.name != "nt":
        return False
    try:
        import ctypes

        ICONO_ERROR, ICONO_PREGUNTA, SI_NO, DELANTE = 0x10, 0x20, 0x4, 0x10000
        estilo = DELANTE | ((ICONO_PREGUNTA | SI_NO) if pregunta else ICONO_ERROR)
        respuesta = ctypes.windll.user32.MessageBoxW(None, texto, TITULO_FALLO, estilo)
    except (OSError, AttributeError):
        return False
    return pregunta and respuesta == 6  # IDYES


def avisar_fallo_de_arranque(motivo: str = "") -> bool:
    """Explica por qué el motor no arrancó. Devuelve True si quedó arreglado.

    El caso que más se da tiene arreglo en el acto: se cambió el modelo de
    embeddings y las memorias tienen vectores del anterior. Si ese anterior
    está apuntado, se ofrece volver a él.
    """
    from lightrag.api.bimnemo import embedding_anterior

    registro = _leer_registro()
    modelos = embedding_anterior.desajuste(registro)
    env = Path.cwd() / ".env"

    if modelos is not None:
        de_los_vectores, configurado = modelos
        explicacion = (
            "Tus memorias se hicieron con el modelo de embeddings "
            f"«{de_los_vectores or 'anterior'}», y ahora está configurado "
            f"«{configurado or 'otro'}».\n\n"
            "Los vectores de un modelo no sirven para otro, así que el motor no "
            "arranca para no darte resultados equivocados. Tus memorias no se "
            "han tocado."
        )
        if embedding_anterior.puede_volver(env, de_los_vectores):
            si = _dialogo(
                explicacion
                + f"\n\n¿Volver a «{de_los_vectores or 'el anterior'}»? "
                "BIMNEMO se abrirá como antes.\n\n"
                "Para cambiar de modelo de verdad hay que reconstruir los índices "
                "con el nuevo, y eso vuelve a enviar todo el texto al proveedor "
                "(gasta saldo).",
                pregunta=True,
            )
            if si:
                try:
                    embedding_anterior.restaurar(env)
                    return True
                except OSError as exc:
                    _dialogo(f"No se pudo escribir {env}:\n{exc}")
            return False
        _dialogo(
            explicacion
            + "\n\nPara abrirlas, vuelve a poner ese modelo en EMBEDDING_MODEL "
            f"(y su proveedor) en:\n{env}\n\n"
            "O reconstruye los índices con el modelo nuevo, lo que vuelve a "
            "enviar todo el texto al proveedor (gasta saldo)."
        )
        return False

    ultimo = _ultimo_error(registro)
    _dialogo(
        (motivo or "El motor de BIMNEMO se cerró al arrancar.")
        + (f"\n\nLo último que dijo:\n{ultimo}" if ultimo else "")
        + f"\n\nEl registro completo está en:\n{registro_del_motor()}"
    )
    return False


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
    parser.add_argument(
        "--consola",
        action="store_true",
        help="Deja visible la salida del servidor (para diagnosticar).",
    )
    parser.add_argument(
        "--solo-motor",
        "--navegador",  # el nombre de antes, para los accesos directos
        dest="solo_motor",
        action="store_true",
        help="Solo arranca el motor, sin ventana: para usarlo desde la API.",
    )
    parser.add_argument(
        "--esperar-pid",
        type=int,
        default=0,
        # Lo usa la propia aplicación al relanzarse tras actualizarse.
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--nativo",
        action="store_true",
        # Ya es lo normal. Se sigue aceptando para no romper los accesos
        # directos que lo llevan.
        help=argparse.SUPPRESS,
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
                "PORT=9621\n"
                # El idioma va aquí aunque este fichero sea el mínimo: es el
                # único ajuste que no se arregla después sin reindexar.
                f"SUMMARY_LANGUAGE={IDIOMA_POR_DEFECTO}\n",
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


def _relanzar_como_bimnemo(argv: list[str]) -> bool:
    """Se vuelve a abrir con `bimnemo.exe` si está al lado y no es éste.

    Al desarrollar se arranca con el `pythonw.exe` del entorno, que en
    Windows es un redirector: la ventana acaba en el Python del sistema y el
    Administrador de tareas dice «Python» con su icono. Si
    `scripts/release/cara_local.py` ha dejado un `bimnemo.exe` en la misma
    carpeta, se relanza con él y este proceso termina: así da igual cómo se
    abra —acceso directo, terminal, costumbre—, siempre sale «bimnemo».

    `BIMNEMO_SIN_CARA=1` lo desactiva, para depurar con el intérprete tal
    cual.
    """
    if os.name != "nt" or _somos_bimnemo() or os.getenv("BIMNEMO_SIN_CARA"):
        return False
    propio = Path(sys.executable).parent / "bimnemo.exe"
    if not propio.is_file():
        return False
    subprocess.Popen(
        [str(propio), "-m", "lightrag.api.bimnemo.desktop", *argv],
        close_fds=True,
    )
    return True


#: Cuánto espera una copia relanzada a que la anterior termine de cerrarse.
ESPERA_RELANZADO_SEGUNDOS = 60.0


def esperar_a_que_termine(pid: int, segundos: float = ESPERA_RELANZADO_SEGUNDOS) -> None:
    """Espera a que termine el proceso ``pid``, o a que pase el plazo.

    Existe para relanzarse después de actualizar. La copia vieja se está
    cerrando mientras la nueva arranca: si la nueva no esperase, encontraría
    el puerto ocupado por el motor viejo, se engancharía a él como «otra
    ventana» —sin supervisor— y ese motor moriría en cuanto la vieja
    terminase de cerrar, dejando la ventana nueva sin nada detrás.
    """
    if pid <= 0:
        return
    if os.name == "nt":
        import ctypes

        SINCRONIZAR = 0x00100000
        manija = ctypes.windll.kernel32.OpenProcess(SINCRONIZAR, False, pid)
        if not manija:
            return  # ya no existe
        try:
            ctypes.windll.kernel32.WaitForSingleObject(manija, int(segundos * 1000))
        finally:
            ctypes.windll.kernel32.CloseHandle(manija)
        return

    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.2)


def _arrancar(base_url: str, args) -> subprocess.Popen | None:
    """Arranca el motor; si no puede, lo explica y, si se arregla, reintenta."""
    for _ in range(2):
        print(f"Arrancando el motor en {base_url} …")
        server = start_server(args.host, args.port, quiet=not args.consola)
        if wait_for_server(base_url, server, SERVER_TIMEOUT_SECONDS):
            print("Motor listo.")
            return server
        if server.poll() is None:
            server.terminate()
            avisar_fallo_de_arranque(
                f"El motor no respondió en {SERVER_TIMEOUT_SECONDS:.0f} s."
            )
            return None
        if not avisar_fallo_de_arranque():
            return None
    return None


def main(argv: list[str] | None = None) -> int:
    if _relanzar_como_bimnemo(list(sys.argv[1:] if argv is None else argv)):
        return 0

    args = _parse_args(argv)
    esperar_a_que_termine(args.esperar_pid)
    base_url = f"http://{args.host}:{args.port}"

    marcar_en_marcha()

    already_running = port_is_open(args.host, args.port) and health_responds(base_url)
    server: subprocess.Popen | None = None

    if already_running:
        print(f"BIMNEMO ya está en marcha en {base_url}; se abre otra ventana.")
    elif port_is_open(args.host, args.port):
        # Puerto ocupado por algo que no contesta a /health. Arrancar encima
        # fallaría con un error de socket que no dice nada útil.
        _dialogo(
            f"El puerto {args.port} está ocupado por otro programa.\n"
            f"Cierra ese programa y vuelve a abrir BIMNEMO."
        )
        return 1
    else:
        asegurar_env()
        server = _arrancar(base_url, args)
        if server is None:
            return 1

    if args.solo_motor:
        print(f"BIMNEMO  {base_url}\nSwagger  {base_url}/docs")
        print("Ctrl+C para detener.")
        try:
            if server is not None:
                server.wait()
        except KeyboardInterrupt:
            pass
        finally:
            _shutdown(server)
        return 0

    from lightrag.api.bimnemo import nativo

    if not nativo.disponible():
        # Sin Qt no hay ventana. Antes se caía a la interfaz web en Chrome;
        # ya no existe, así que se dice qué falta en vez de abrir nada.
        _dialogo(
            "La ventana de BIMNEMO necesita Qt (PySide6) y no está instalado.\n"
            "    pip install pyside6-essentials"
        )
        _shutdown(server)
        return 1

    return _con_ventana_nativa(nativo, base_url, args, server)


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

        if server.poll() is not None and _es_desajuste_de_embeddings():
            # Reintentar no sirve: fallará igual hasta que cambie el .env.
            if avisar_fallo_de_arranque():
                consecutive_failures = 0
                continue
            window.terminate()
            break

        if time.monotonic() - started_at < FAST_FAILURE_SECONDS:
            consecutive_failures += 1
        else:
            consecutive_failures = 1

        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            avisar_fallo_de_arranque(
                f"El motor no arranca tras {consecutive_failures} intentos."
            )
            window.terminate()
            break

    return server


def _es_desajuste_de_embeddings() -> bool:
    from lightrag.api.bimnemo import embedding_anterior

    return embedding_anterior.desajuste(_leer_registro()) is not None


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
