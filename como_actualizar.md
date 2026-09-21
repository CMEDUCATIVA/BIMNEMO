# Cómo se actualiza BIMNEMO

> **Si has abierto esto desde el menú Inicio:** no tienes que hacer nada.
> Cuando hay una versión nueva, aparece **«Actualizar»** parpadeando en la
> barra de arriba de BIMNEMO. Púlsalo: se descarga, se instala encima y
> BIMNEMO vuelve a abrirse solo. Tus memorias, tus documentos y tu
> configuración no se tocan. Lo que sigue es para quien mantiene BIMNEMO.

Este documento explica, para una persona o una IA que tenga que mantenerlo,
cómo funciona la actualización de punta a punta: cómo se publica una versión
en GitHub, cómo se entera cada instalación y qué pasa en el ordenador del
cliente cuando pulsa el botón. Cómo se construye el instalador está en
[`instalador_bimnemo.md`](instalador_bimnemo.md).

**Repositorio:** <https://github.com/CMEDUCATIVA/BIMNEMO> · rama `main` · **público**

---

## La idea en una frase

Una instalación compara su fichero `VERSION` con la **última versión
publicada** en GitHub (`releases/latest`). Si la publicada es posterior, la
ventana lo avisa; al pulsar «Actualizar», el motor descarga el código de esa
etiqueta, lo copia encima de la instalación, se reinicia, y la ventana se
relanza.

```
  quien mantiene                 GitHub                        cliente
  ──────────────                 ──────                        ───────
  commit + VERSION ──push──▶  main + etiqueta vX.Y.Z
  publicar.py ─────────────▶  release vX.Y.Z  ◀── GET releases/latest (motor, cada ≤5 min)
                                    │                  │ ¿más nueva que VERSION?
                                    │                  ▼
                                    │           «Actualizar» parpadea
                                    │                  │ pulsa
                                    └── zipball ──▶ POST /bimnemo/update/apply
                                                       │ descarga, copia, pip si hace falta
                                                       │ se reinicia (código 77)
                                                       ▼
                                                la ventana se relanza
```

**Un `git push` solo no le llega a nadie instalado.** Lo que ven los
clientes son versiones **publicadas** (etiqueta + *release*). Un commit suelto
en `main` solo lo ve una copia de desarrollo (ver más abajo).

---

## Las piezas y dónde están

| Pieza | Fichero | Qué hace |
|---|---|---|
| Versión instalada | `VERSION` (raíz) | Única fuente del número. `vX.Y.Z`. Lo leen el motor, la ventana y el actualizador |
| Consulta y comparación | `lightrag/api/bimnemo/actualizacion.py` | `estado()`: ¿hay una más nueva? Elige estrategia, guarda la respuesta 5 min |
| Descarga y despliegue | `lightrag/api/bimnemo/paquete.py` | `ultima_version`, `es_mas_nueva`, `traer`, `desplegar`, `pyproject_cambio` |
| Qué no viaja al cliente | `lightrag/api/bimnemo/reparto.py` | `sobra_en_cliente()`: pruebas, Docker, `scripts/`… |
| Rutas del motor | `lightrag/api/routers/bimnemo_update_routes.py` | `GET /bimnemo/update`, `POST /bimnemo/update/apply`, `GET /bimnemo/update/progress` |
| Identidad del proceso | `lightrag/api/bimnemo/build.py` + `GET /bimnemo/app-build` | `boot_id`: cambia en cada arranque del motor |
| Aviso y diálogo | `lightrag/api/bimnemo/nativo/actualizar.py` | `Vigia`, `BotonActualizar`, `DialogoActualizar`, `Actualizando`, `relanzar` |
| Espera del reinicio | `lightrag/api/bimnemo/nativo/reinicio.py` | Sondea `boot_id` cada 400 ms hasta que cambia |
| Supervisor y relanzado | `lightrag/api/bimnemo/desktop.py` | Levanta el motor cuando sale con código 77; `--esperar-pid` |
| Publicar | `scripts/release/publicar.py` | Crea la *release* en GitHub y adjunta el instalador |

Constantes que conviene conocer (`actualizacion.py`): `REPO =
"CMEDUCATIVA/BIMNEMO"`, `RAMA = "main"`, `CACHE_SEGUNDOS = 300`. El código de
reinicio es `RESTART_EXIT_CODE = 77` (`bimnemo/runtime.py`).

---

## Cómo se entera una instalación

### Dos estrategias, elegidas por lo que hay en disco

`actualizacion.estrategia()` devuelve:

- **`"release"`** — no hay `.git`. Es **todo cliente** instalado con el
  instalador. Compara `VERSION` con `tag_name` de
  `https://api.github.com/repos/CMEDUCATIVA/BIMNEMO/releases/latest`.
- **`"git"`** — hay `.git` y git funciona. Es la copia de quien desarrolla.
  Compara el commit local con el último de `main`
  (`https://api.github.com/repos/CMEDUCATIVA/BIMNEMO/commits/main`), y se
  actualiza con `git fetch` + `reset`, negándose si hay cambios locales.

La pantalla no distingue: mismo botón, mismas rutas.

### «Más nueva», no «distinta»

`paquete.es_mas_nueva(publicada, instalada)` compara los números:
`v1.4.0-nativa` → `(1, 4, 0)`; el sufijo tras el guion se ignora. Si alguno
de los dos no se entiende como versión, contesta **que no**.

> **Por qué importa.** Antes se comparaba con `!=`. La última publicada era la
> v1.2.3 y quien tenía la 1.4 la veía como «nueva»: actualizar le habría
> devuelto a la interfaz web. Hay además una **segunda barrera** en
> `paquete.traer`: se niega a descargar nada que no sea posterior
> (`reason: "older"`), porque es el código que escribe en disco.

### Cuándo pregunta la ventana

`nativo/actualizar.py` → `Vigia`:

- 5 s después de abrir (`PRIMERA_MS`);
- cada 5 minutos (`INTERVALO_MS`);
- al volver a la ventana (`WindowActivate`), como mucho una vez por minuto
  (`MINIMO_ENTRE_CONSULTAS`).

Pregunta al **motor** (`GET /bimnemo/update`), no a GitHub. El motor guarda la
respuesta de GitHub 5 minutos: GitHub, sin credencial, admite **60 consultas
por hora por IP**, y así no pasa de 12. `?force=true` se salta la caché.

Sin red, el motor devuelve `reachable: false` y no es un error: la ventana no
avisa de nada.

### Qué devuelve `GET /bimnemo/update`

```json
{"supported": true, "reachable": true, "strategy": "release",
 "installed": "v1.4.3", "latest": "v1.4.4", "behind": true,
 "dirty": false, "message": "BIMNEMO v1.4.4", "date": "…", "repo": "CMEDUCATIVA/BIMNEMO"}
```

`behind: true` es lo único que enciende el botón.

---

## Qué pasa al pulsar «Actualizar»

1. **La ventana** (`DialogoActualizar` → `Actualizando`, que es un `Reinicio`
   con otra ruta) apunta el `boot_id` actual con `GET /bimnemo/app-build`.
2. Pide `POST /bimnemo/update/apply`. El motor:
   - se niega con **409** si está indexando (cortar una ingesta deja
     almacenes a medio escribir);
   - vuelve a consultar GitHub (forzado) y, si ya está al día, contesta
     `{"status": "up_to_date"}` **sin reiniciarse** — la ventana lo dice y no
     espera;
   - si no, contesta `{"status": "updating"}` enseguida y hace el trabajo en
     segundo plano.
3. **El trabajo del motor** (`actualizacion.aplicar` → `paquete.traer`):
   1. descarga el `zipball_url` de la última *release* a una carpeta temporal;
   2. comprueba que es un zip legible y que trae `pyproject.toml` y
      `lightrag/` (`SENALES`); si no, no toca nada;
   3. descarta lo que `sobra_en_cliente` y copia el resto **encima** de la
      instalación (`copytree(..., dirs_exist_ok=True)`: reemplaza fichero a
      fichero, no borra antes);
   4. escribe la etiqueta en `VERSION`;
   5. si cambió `pyproject.toml` —comparado **sin saltos de línea**—, ejecuta
      `pip install -e ".[api,escritorio]"` con el Python de la instalación
      (`python\python.exe`) **sin ventana** (`CREATE_NO_WINDOW`);
   6. cierra los almacenes y sale con **código 77**.
   Si algo falla, lo apunta en `GET /bimnemo/update/progress`
   (`{"state": "failed", "message": …}`) y **no** se reinicia.
4. **El supervisor** (`desktop.supervise`, en un hilo del proceso de la
   ventana) ve el código 77 y levanta el motor otra vez, ya con el código
   nuevo.
5. **La ventana** sondea `app-build` cada 400 ms (y `update/progress` a la
   vez). Mientras contesta el mismo `boot_id`, espera: es el motor viejo
   descargando. Cuando cambia, el motor nuevo está en pie. Plazo: 15 minutos.
   Si `progress` dice `failed`, lo cuenta al momento.
6. **Se relanza la aplicación** (`actualizar.relanzar`). El motor ya es nuevo,
   pero el código de la ventana está cargado en memoria y seguiría siendo el
   viejo. Se lanza
   `bimnemo.exe -m lightrag.api.bimnemo.desktop --esperar-pid <pid> --port <puerto>`
   (desacoplado del proceso actual) y la ventana se cierra. La copia nueva
   **espera a que la vieja termine** antes de arrancar: si no, encontraría el
   puerto ocupado, se engancharía al motor viejo como «otra ventana» y se
   quedaría sin motor cuando la vieja lo apagara al cerrar.

Medido en una actualización real (v1.2.0 → v1.2.3, sobre una copia del
paquete): **51 segundos** de principio a fin.

### Lo que no se toca

El `.env` (configuración y claves), `inputs/` (documentos) y `rag_storage/`
(memorias) **no están en el zip**: están en `.gitignore`, así que la etiqueta
no los contiene y no pueden pisarse. No hay una lista de exclusiones que
mantener; la garantía es `.gitignore`. Comprobado byte a byte en la prueba
real.

Consecuencia a tener en cuenta: **desplegar no borra**. Un fichero que una
versión nueva ya no trae se queda en la instalación. Si algún día hay que
retirar ficheros de los clientes, hay que borrarlos explícitamente (desde el
propio código o desde `[InstallDelete]` del instalador).

---

## Publicar una versión

Lo que hace falta para que los clientes reciban un cambio. Todo desde la raíz
del repositorio.

### 1. Que no haya nada roto

```bash
.venv/Scripts/python.exe -m pytest tests/bimnemo -q -p no:cacheprovider
```

Tiene que salir todo en verde (hoy, 221 pruebas).

### 2. Que no se cuele nada: el repositorio es público

```bash
git status --short                           # míralo entero
git ls-files | grep -cE "^\.env"             # 0
git log -p origin/main..HEAD | grep -cE 'sk-proj-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}|ghp_[A-Za-z0-9]{30,}'   # 0
```

Los dos contadores tienen que dar `0`. Cuenta, no uses `| head`: `head`
devuelve éxito aunque no encuentre nada. Lo publicado no se borra: quien lo
clonó ya lo tiene.

### 3. El número

`VERSION` es la única fuente. Formato `vX.Y.Z`, sin sufijos en las versiones
publicadas.

| Cambio | Ejemplo |
|---|---|
| Rompe algo que ya funcionaba o cambia el formato de los datos | `v2.0.0` |
| Añade algo sin romper nada | `v1.5.0` |
| Solo arregla o ajusta | `v1.4.5` |

```bash
printf 'v1.4.5\n' > VERSION
```

### 4. Commit, etiqueta y subida

```bash
git add <lo que cambia> VERSION
git commit -m "Qué cambia, y en el cuerpo POR QUÉ"
git tag -a v1.4.5 -m "BIMNEMO v1.4.5"
git push origin main v1.4.5
```

La etiqueta tiene que coincidir con `VERSION`: el despliegue copia el
`VERSION` de la etiqueta y luego escribe el nombre de la etiqueta encima.

### 5. La *release*

```bash
.venv/Scripts/python.exe scripts/release/publicar.py v1.4.5 notas.md
```

- **No borrador ni preliminar**: `releases/latest` no ve ninguna de las dos
  cosas, así que no le llegaría a nadie.
- **Las notas son para quien usa BIMNEMO**: qué cambia para él y qué se
  arregla, en su idioma. Al final, una línea que diga que se instala con el
  botón «Actualizar» y que sus datos no se tocan.
- **El instalador es opcional** para actualizar: los clientes solo
  necesitan la etiqueta. Pero la *release* que GitHub marca como «Latest» es
  a la que llega quien descarga BIMNEMO por primera vez. Si esa no lleva
  instalador, las notas tienen que apuntar a la última que sí lo lleva. Para
  adjuntarlo: tercer argumento de `publicar.py` (ver
  [`instalador_bimnemo.md`](instalador_bimnemo.md)).

### 6. Comprobar que llega

Con BIMNEMO abierto:

```bash
curl -s "http://127.0.0.1:9621/bimnemo/update?force=true"
```

Tiene que decir `"latest": "v1.4.5", "behind": true`. El botón aparece en la
siguiente consulta de la ventana: como mucho 5 minutos, o al volver a ella.

### El ciclo entero

```bash
.venv/Scripts/python.exe -m pytest tests/bimnemo -q -p no:cacheprovider
git status --short
git log -p origin/main..HEAD | grep -cE 'sk-proj-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}|ghp_[A-Za-z0-9]{30,}'
printf 'v1.4.5\n' > VERSION
git add <ficheros> VERSION && git commit -m "…"
git tag -a v1.4.5 -m "BIMNEMO v1.4.5"
git push origin main v1.4.5
.venv/Scripts/python.exe scripts/release/publicar.py v1.4.5 notas.md
curl -s "http://127.0.0.1:9621/bimnemo/update?force=true"
```

---

## La copia de desarrollo

Tiene `.git`, así que usa la estrategia `"git"`: el botón aparece en cuanto
hay un commit nuevo en `main` en GitHub, sin necesidad de etiqueta. Si hay
cambios locales sin subir, `apply` se niega (409) antes de borrarlos; con
`{"discard_local_changes": true}` los descarta.

Para trabajar con cambios propios, lo normal es `git pull` a mano:

```bash
git stash && git pull origin main && .venv/Scripts/python.exe -m pip install -e ".[api,escritorio]" && git stash pop
```

---

## Reglas que no se rompen

- **Nunca se ofrece ni se instala una versión anterior.** Las dos barreras
  (`es_mas_nueva` en la consulta y en `traer`) están cubiertas por pruebas.
- **`VERSION` es la única fuente del número**, y la etiqueta coincide con él.
- **Los datos del cliente no viajan en el código.** Todo lo que sea del
  usuario va en `.gitignore`. Si se añade una carpeta de datos nueva, va ahí
  antes que en ningún otro sitio.
- **Nada de ventanas de consola.** BIMNEMO corre sin consola; todo programa
  de consola que lance (`pip`, `git`) va con `CREATE_NO_WINDOW`.
- **No se reinicia con el motor indexando.** `apply` usa la misma
  comprobación que el reinicio.
- **El repositorio es público.** Ni tokens ni claves en nada versionado. La
  credencial de GitHub la guarda el administrador de credenciales de Windows
  y `publicar.py` se la pide a git en memoria.

---

## Problemas conocidos y lo que se aprendió

- **Las versiones 1.2 y 1.3 tienen el actualizador viejo.** Compara con `!=` y
  su instalación no lleva Qt. Si alguien con la 1.2 o la 1.3 pulsa su botón,
  se descarga la última (1.4.x), `pip` instala sin Qt y BIMNEMO **no llega a
  abrir** (y no se ve el aviso, porque corre sin consola). Las notas de las
  versiones 1.4.x lo advierten: esos usuarios tienen que reinstalar con el
  instalador. Arreglo pendiente, si hiciera falta: que `desktop.py` instale
  `pyside6-essentials` solo cuando le falte y lo diga con un mensaje visible.
- **Saltos de línea.** El `pyproject.toml` instalado sale de una copia de
  Windows (CRLF) y el de GitHub trae LF. Comparando bytes parecía distinto y
  cada actualización pasaba ~40 s en `pip` para nada. Por eso
  `pyproject_cambio` normaliza.
- **La ventana negra.** Era `pip` lanzado con `python\python.exe` desde un
  proceso sin consola: Windows le daba una propia, encima de todo.
- **«No me aparece el botón».** Con una consulta cada media hora, una
  versión publicada justo después de abrir tardaba en verse. Hoy son 5
  minutos y al volver a la ventana.
- **La caché solo existía en la estrategia git.** En las instalaciones cada
  pregunta de la ventana era una consulta a GitHub. Ahora las dos guardan la
  respuesta 5 minutos.

---

## Diagnóstico

En la carpeta de la instalación (por defecto
`%LOCALAPPDATA%\Programs\BIMNEMO`):

- `VERSION` — qué versión cree tener.
- `lightrag.log` — busca estas líneas:
  ```
  BIMNEMO: desplegada la versión v1.4.5
  BIMNEMO: cambiaron las dependencias; instalando…
  BIMNEMO: actualizado a v1.4.5; reiniciando
  BIMNEMO: la actualización falló (<motivo>): <mensaje>
  ```

Con BIMNEMO abierto:

```bash
curl -s "http://127.0.0.1:9621/bimnemo/update?force=true"   # qué ve
curl -s  http://127.0.0.1:9621/bimnemo/update/progress      # en qué va
curl -s  http://127.0.0.1:9621/bimnemo/app-build            # qué proceso contesta
```

Motivos de fallo de `traer`: `github` (no se pudo consultar), `release`
(publicada sin zip), `older` (no es más nueva), `download` (se cortó la
descarga), `deploy` (el zip no tiene la forma esperada o no se pudo copiar).
