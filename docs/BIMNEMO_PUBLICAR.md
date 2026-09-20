# Publicar una versión de BIMNEMO

Para quien mantiene BIMNEMO: cómo subir cambios a GitHub y cuándo poner una
etiqueta. Si lo que quieres es **recibir** actualizaciones, no publicarlas,
mira [`como_actualizar.md`](../como_actualizar.md).

**Repositorio:** <https://github.com/CMEDUCATIVA/BIMNEMO> (público)

---

## Antes de cada subida: la comprobación que no se salta

Este repositorio es **público**. Todo lo que subas lo ve cualquiera, y borrarlo
después no lo deshace: quien ya lo clonó lo tiene.

```bash
# 1. ¿Se cuela alguna copia del .env?
git ls-files | grep -E "^\.env"          # tiene que salir vacío

# 2. ¿Hay credenciales dentro de lo que se sube?
git ls-files -z | xargs -0 grep -lIE \
  "sk-proj-[A-Za-z0-9_-]{20}|sk-svcacct-|ghp_[A-Za-z0-9]{36}|AIza[A-Za-z0-9_-]{30}"
# tiene que salir vacío
```

> **Esto no es teoría.** En la primera publicación apareció
> `.env.bimnemo.bak` —una copia del `.env` con la clave de OpenAI dentro— a
> punto de subirse. `.gitignore` cubría `.env` y `.env.backup.*`, pero no ese
> nombre. Ahora la regla es `.env.*` entera.

Lo que **nunca** se sube, y está en `.gitignore`: `.env` y cualquier copia,
`inputs/`, `rag_storage/`, `*.log`, `prompts/entity_type/`.

---

## Subir cambios

```bash
git add -A
git status                    # míralo: es la última oportunidad de ver algo raro
git commit -m "Mensaje que diga QUÉ cambia y POR QUÉ"
git push origin main
```

En cuanto el commit está en `main`, **BIMNEMO lo ofrece a todo el mundo**: la
aplicación compara su commit instalado con el último de `main` y empieza a
parpadear. No hace falta etiquetar para que llegue.

### El mensaje del commit

Una línea que diga qué cambia, y si hace falta un párrafo con el porqué. Lo
que importa es que dentro de seis meses se entienda **por qué** se tocó eso,
no qué línea se movió — eso ya lo dice el diff.

```
Barra de indexado dentro de la columna de estado

El banner flotaba sobre toda la aplicación hablando de una fila de la
tabla. Ahora el progreso va donde está el archivo del que habla.
```

---

## Etiquetar una versión

Una etiqueta es un punto al que se puede volver y un nombre que se puede
citar. **No hace falta para actualizar**, así que no se pone en cada subida.

**Se etiqueta cuando:**

- cambia algo que el usuario nota (una pantalla, un flujo, un formato nuevo);
- se arregla algo que le estaba costando datos o dinero;
- se quiere un punto de retorno seguro antes de una tanda grande.

**No se etiqueta** un arreglo de comentarios, un cambio de estilo, ni un
«sigo trabajando en ello».

### Cómo

```bash
git tag -a v1.1.0 -m "Barra de progreso por fila y reinicio con cortina"
git push origin v1.1.0
```

Numeración, con el criterio de siempre:

| Cambio | Ejemplo |
|---|---|
| Rompe algo que ya funcionaba, o cambia el formato de los datos | `v2.0.0` |
| Añade algo sin romper nada | `v1.1.0` |
| Solo arregla | `v1.0.1` |

### Notas de la versión

En GitHub → Releases → *Draft a new release* → elige la etiqueta. Escríbelas
**para quien usa BIMNEMO**, no para quien lo programa:

```markdown
## Qué cambia para ti

- La barra de progreso ahora va **dentro de la columna Estado** de cada
  archivo, en vez de un recuadro aparte.
- El Panel se entera solo de lo que borras: ya no hay que pulsar «Actualizar».
- Botón **Reiniciar motor LightRAG** en la pestaña Motor.

## Arreglos

- Al reiniciar, la ventana ya no se recargaba antes de tiempo contra el motor
  que se estaba cerrando.
- Borrar un documento ya no bloquea la aplicación mientras se purga.

## Si actualizas desde una versión anterior

Nada que hacer: pulsa **Actualizar** en la barra superior.
```

---

## Ejemplo completo: de un cambio a una versión publicada

```bash
# 1. Comprobar que no hay nada roto
python -m pytest tests/api tests/bimnemo tests/workspace -q

# 2. Revisar lo que se sube
git add -A
git ls-files | grep -E "^\.env"          # vacío
git status

# 3. Subir
git commit -m "Instrucción para agentes con los 15 endpoints de la memoria"
git push origin main

# 4. Etiquetar, si toca
git tag -a v1.2.0 -m "La API se documenta sola para agentes"
git push origin v1.2.0
```

---

## Credenciales

Para subir hace falta un token de GitHub con permiso `repo`.

- **No se guarda en el repositorio.** Nunca en un fichero versionado, nunca en
  el `.env` que se publica.
- **Un token que ha pasado por un chat, un correo o una captura está
  quemado**: revócalo y genera otro. GitHub → *Settings* → *Developer
  settings* → *Personal access tokens*.
- Lo cómodo y seguro en Windows es dejar que lo guarde el gestor de
  credenciales:

  ```bash
  git config --global credential.helper manager
  ```

  La primera vez lo pide; después ya no.
