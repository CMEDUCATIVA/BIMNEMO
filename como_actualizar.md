# Cómo actualizar BIMNEMO

BIMNEMO se actualiza desde GitHub, sin reinstalar nada y sin tocar tus
memorias. Este documento cuenta las dos formas de hacerlo —desde la ventana y
desde la terminal—, qué ocurre por debajo y qué hacer si algo sale mal.

**Repositorio:** <https://github.com/CMEDUCATIVA/BIMNEMO>

---

## Lo primero, porque es lo que más preocupa

> **Actualizar no toca tus datos.**

Tus documentos (`inputs/`), tus memorias indexadas (`rag_storage/`) y tu
configuración (`.env`) **no están en GitHub** y la actualización no los
modifica. Están excluidos a propósito en `.gitignore`: lo que viaja es el
programa, no tu conocimiento.

Eso también significa que **actualizar no es una copia de seguridad**. Si
quieres una, copia esas tres cosas a otro sitio.

---

## Forma 1 — desde la ventana (la normal)

En la barra superior, a la derecha, hay un botón de estado:

| Lo que ves | Qué significa |
|---|---|
| **Actualizado** | Tienes la última versión publicada |
| **Actualizar** *(parpadeando)* | Hay una versión nueva esperando |
| **Buscando…** | Está preguntando a GitHub |
| **Sin conexión** | No se pudo preguntar; se reintenta solo |

Pulsa **Actualizar** y BIMNEMO hace lo siguiente, en este orden:

1. **Comprueba que no hay nada a medias.** Si está indexando, se niega y te lo
   dice: cortar una ingesta deja documentos a medio procesar.
2. **Descarga los cambios** (`git fetch` + `git reset --hard` al commit
   publicado). Esto **descarta modificaciones locales** en los ficheros del
   programa; tus datos no se tocan.
3. **Actualiza las dependencias** si cambiaron (`pip install -e .[api]`).
4. **Reinicia el motor**, con la cortina de progreso de siempre.
5. **Recarga la ventana** cuando el motor nuevo está en pie.

Tarda entre quince segundos y un par de minutos, según si hay dependencias
nuevas.

### Si has cambiado código a mano

El paso 2 **borra esos cambios**. BIMNEMO lo avisa antes de empezar si detecta
modificaciones locales, y te deja elegir entre guardarlas (`git stash`) o
descartarlas. Si trabajas sobre el código, usa la forma 2.

---

## Forma 2 — desde la terminal (si tocas el código)

```bash
cd "C:/Users/Administrador/Downloads/MEMORIA/LightRAG-main/LightRAG-main"

git stash            # guarda tus cambios locales, si los hay
git pull origin main
pip install -e .[api]
git stash pop        # los recupera encima de la versión nueva
```

Después, reinicia el motor desde **Motor → Reiniciar motor LightRAG**, o
cierra y abre `BIMNEMO.bat`.

---

## Cómo sabe que hay una versión nueva

Cada cierto tiempo BIMNEMO le pregunta a GitHub por el último commit de la
rama `main` y lo compara con el que tiene instalado. Si difieren, el botón
empieza a parpadear.

- **Se consulta la API pública de GitHub**, sin credenciales. Eso basta para
  un repositorio público y evita guardar un token en tu ordenador.
- **El límite de GitHub sin credenciales son 60 consultas por hora.** BIMNEMO
  pregunta **una vez al arrancar y luego cada 30 minutos**, así que ni se
  acerca.
- **Si no hay internet, no pasa nada.** El botón dice «Sin conexión» y se
  vuelve a intentar más tarde. Nunca bloquea la aplicación.

---

## Publicar una versión nueva (para quien mantiene BIMNEMO)

Ver [`docs/BIMNEMO_PUBLICAR.md`](docs/BIMNEMO_PUBLICAR.md): cómo subir los
cambios, cuándo poner una etiqueta y qué escribir en ella.

---

## Cuando algo sale mal

### «El motor está indexando ahora mismo»

No es un error: es una negativa a propósito. Espera a que termine la ingesta
—la barra de la columna *Estado* en Archivos te dice por dónde va— y vuelve a
pulsar.

### El botón se queda en «Sin conexión»

BIMNEMO no llega a `api.github.com`. Causas habituales: no hay internet, o un
cortafuegos corporativo bloquea la salida. **No afecta a nada más**: la
aplicación funciona igual, solo que no sabrá avisarte de versiones nuevas.

### La ventana no vuelve después de actualizar

El motor no arrancó, casi siempre por una dependencia nueva que no se instaló
bien. Ciérralo todo y arranca con consola para ver el error:

```bash
BIMNEMO.bat --consola
```

Y si hace falta, reinstala las dependencias a mano:

```bash
pip install -e .[api]
```

### Quiero volver a la versión anterior

```bash
git log --oneline -10        # busca el commit al que quieres volver
git reset --hard <commit>
pip install -e .[api]
```

Tus memorias siguen intactas: no dependen de la versión del programa.

---

## Lo que nunca hace una actualización

- **No borra memorias** ni documentos.
- **No cambia tu `.env`** — ni tus claves, ni tu proveedor, ni tu idioma.
- **No sube nada tuyo a GitHub.** La comprobación solo lee.
- **No se actualiza sola.** Avisa; actualizar lo decides tú.
