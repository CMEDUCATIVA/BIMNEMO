# Mantener BIMNEMO

El ciclo completo, de un cambio a una versión que tus clientes reciben:
actualizar tu copia, subir a GitHub, etiquetar y generar el instalador.

> Si lo que quieres es **recibir** actualizaciones, no publicarlas, lee
> [`como_actualizar.md`](como_actualizar.md). Este documento es para quien
> mantiene BIMNEMO.

**Repositorio:** <https://github.com/CMEDUCATIVA/BIMNEMO> · **público**

---

## 0. La comprobación que no se salta

El repositorio es público. Todo lo que subas lo ve cualquiera, y **borrarlo
después no lo deshace**: quien ya lo clonó lo tiene.

```bash
# ¿Se cuela alguna copia del .env?
git ls-files | grep -cE "^\.env"

# ¿Hay credenciales dentro de lo que se sube?
git ls-files -z | xargs -0 grep -lIE \
  "sk-proj-[A-Za-z0-9_-]{20}|sk-svcacct-|ghp_[A-Za-z0-9]{36}|AIza[A-Za-z0-9_-]{30}" | wc -l
```

**Los dos tienen que dar `0`.**

> **No es teoría.** En la primera publicación apareció `.env.bimnemo.bak`
> —una copia del `.env` con la clave de OpenAI dentro— a punto de subirse.
> `.gitignore` cubría `.env` y `.env.backup.*`, pero no ese nombre. Ahora la
> regla es `.env.*` entera.

Y cuenta ficheros, no uses `| head`: **`head` devuelve éxito aunque no
encuentre nada**, así que un `grep … | head && echo PELIGRO` avisa siempre y
deja de significar nada.

Lo que nunca se sube, y está en `.gitignore`: el `.env` y cualquier copia,
`inputs/`, `rag_storage/`, `*.log`, `prompts/entity_type/`, `installer/salida/`.

---

## 1. Actualizar tu copia de desarrollo

Tu copia tiene `.git`, así que BIMNEMO se actualiza comparando commits contra
`main`. Basta con el botón **Actualizar** de la barra superior.

Si has tocado código, el botón avisa y te deja elegir. Para conservarlo:

```bash
git stash
git pull origin main
pip install -e .[api]
git stash pop
```

Después, **Motor → Reiniciar motor LightRAG**.

---

## 2. Subir los cambios

```bash
python -m pytest tests/api tests/bimnemo tests/workspace -q   # 16 fallan: es la línea base
git add -A
git status                    # míralo: última oportunidad de ver algo raro
git commit -m "Qué cambia y POR QUÉ"
git push origin main
```

En cuanto el commit está en `main`, **quien desarrolla lo recibe**: su
aplicación compara commits y el botón empieza a parpadear.

Tus **clientes no**: ellos comparan versiones publicadas. Para que les llegue,
hay que etiquetar (paso 3).

### El mensaje del commit

Una línea con qué cambia, y si hace falta un párrafo con el porqué. Lo que
importa es que dentro de seis meses se entienda **por qué** se tocó eso; qué
línea se movió ya lo dice el diff.

```
Barra de indexado dentro de la columna de estado

El banner flotaba sobre toda la aplicación hablando de una fila de la
tabla. Ahora el progreso va donde está el archivo del que habla.
```

---

## 3. Etiquetar una versión

Una etiqueta es un punto al que volver y **lo que hace que tus clientes se
enteren**.

**Se etiqueta cuando:** cambia algo que el usuario nota, se arregla algo que le
estaba costando datos o dinero, o se quiere un punto de retorno antes de una
tanda grande.

**No se etiqueta** un arreglo de comentarios ni un «sigo trabajando en ello».

```bash
# 1. El número, en el fichero que manda
echo v1.3.0 > VERSION
git add VERSION && git commit -m "VERSION: v1.3.0"

# 2. La etiqueta
git tag -a v1.3.0 -m "Lo que trae esta versión"
git push origin main v1.3.0
```

> **`VERSION` es la única fuente.** `BIMNEMO_VERSION` lo lee de ahí, así que la
> pestaña Motor, el carril y el actualizador dicen todos lo mismo. Antes era
> una constante aparte y se quedó en «1.0.0» mientras se publicaba la v1.1.0:
> una versión entera mintiendo sin que nadie lo notara.

Numeración, con el criterio de siempre:

| Cambio | Ejemplo |
|---|---|
| Rompe algo que ya funcionaba, o cambia el formato de los datos | `v2.0.0` |
| Añade algo sin romper nada | `v1.3.0` |
| Solo arregla | `v1.2.1` |

### Las notas de la versión

GitHub → *Releases* → *Draft a new release* → elige la etiqueta. Escríbelas
**para quien usa BIMNEMO**, no para quien lo programa: qué cambia para él, qué
se arregla, y qué sigue pendiente. Esto último importa: prefiero que lo lea a
que lo descubra probando.

---

## 4. Generar el instalador (.exe)

Tus clientes no instalan con git: instalan con un `.exe` que lleva el programa
**y su entorno virtual**, así que no tienen que instalar Python ni 127
paquetes.

```bat
scripts\release\construir_instalador.bat v1.3.0
```

Hace dos cosas:

1. `empaquetar.py` copia a `installer\salida\app` **lo que git versiona** —así
   la lista de lo que se publica es la misma que decide `.gitignore`— más el
   `.venv`, y escribe el fichero `VERSION`.
2. Inno Setup lo comprime en
   `installer\salida\BIMNEMO-1.3.0-instalador.exe`.

Medido: **292 MB sin comprimir, 69 MB de instalador.** Tarda unos dos minutos.

Hace falta [Inno Setup 6](https://jrsoftware.org/isdl.php).

### Comprobar antes de repartirlo

```bash
ls installer/salida/app/.env installer/salida/app/.env.bimnemo.bak 2>/dev/null
cat installer/salida/app/VERSION
```

El primero **no debe encontrar nada**. El segundo, la versión correcta.

### Adjuntarlo a la versión publicada

GitHub → *Releases* → edita la versión → *Attach binaries*, y sube el `.exe`.

> **Sin esto, quien instala por primera vez no tiene con qué.** El paquete de
> la etiqueta sirve para actualizar, no para instalar de cero.

Desde la terminal, si prefieres (hazlo con Python, no con `curl`: en esta
máquina `curl` falló dos veces con `HTTP 000` subiendo a GitHub):

```python
import io, json, urllib.request
ID = "392417913"   # el id de la versión, de la respuesta al crearla
datos = io.open("installer/salida/BIMNEMO-1.3.0-instalador.exe", "rb").read()
p = urllib.request.Request(
    f"https://uploads.github.com/repos/CMEDUCATIVA/BIMNEMO/releases/{ID}"
    "/assets?name=BIMNEMO-1.3.0-instalador.exe",
    data=datos,
    headers={"Authorization": "token TU_TOKEN",
             "Content-Type": "application/octet-stream",
             "User-Agent": "BIMNEMO"},
    method="POST")
print(json.load(urllib.request.urlopen(p, timeout=900))["browser_download_url"])
```

---

## Cómo se entera cada uno

| Quién | Compara | Le llega con |
|---|---|---|
| Tú, con `.git` | commits contra `origin/main` | **un `git push`** |
| Tus clientes, con instalador | el `VERSION` contra la última versión publicada | **una etiqueta** |

Mismo botón, misma pantalla. Por eso **etiquetar no es opcional** si quieres
que tus clientes reciban algo.

---

## El ciclo entero, de una vez

```bash
# 1. Que no haya nada roto
python -m pytest tests/api tests/bimnemo tests/workspace -q

# 2. Que no se cuele nada
git add -A
git ls-files | grep -cE "^\.env"            # 0

# 3. Subir
git commit -m "Instrucción para agentes con los endpoints resueltos"
git push origin main

# 4. Etiquetar
echo v1.3.0 > VERSION
git add VERSION && git commit -m "VERSION: v1.3.0"
git tag -a v1.3.0 -m "La API habla de la memoria abierta"
git push origin main v1.3.0

# 5. Notas de la versión en GitHub

# 6. El instalador
scripts\release\construir_instalador.bat v1.3.0

# 7. Adjuntarlo a la versión
```

---

## Credenciales

Para subir hace falta un token de GitHub con permiso `repo`.

- **Nunca en un fichero versionado**, y nunca en el `.env` que se publica.
- **Un token que ha pasado por un chat, un correo o una captura está
  quemado**: revócalo y genera otro. GitHub → *Settings* → *Developer
  settings* → *Personal access tokens*.
- Lo cómodo y seguro en Windows es dejar que lo guarde el sistema:

  ```bash
  git config --global credential.helper manager
  ```

  La primera vez lo pide; después ya no. Así no acaba en el historial del
  terminal.
