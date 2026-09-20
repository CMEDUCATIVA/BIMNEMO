# Cómo actualizar BIMNEMO

BIMNEMO se actualiza solo desde un botón, **sin reinstalar nada y sin tocar tu
trabajo**.

---

## Lo primero, porque es lo que preocupa

> **Actualizar no toca tus datos.**

Tus documentos, tus memorias y tu configuración —incluidas tus claves— no
viajan a ninguna parte y la actualización no los modifica. Lo que se descarga
es el programa, no tu conocimiento.

Eso también quiere decir que **actualizar no es una copia de seguridad**. Si
quieres una, copia estas tres carpetas a otro sitio:

| Qué | Dónde |
|---|---|
| Tu configuración y tus claves | `.env` |
| Tus documentos | `inputs\` |
| Tus memorias indexadas | `rag_storage\` |

---

## El botón

Arriba a la derecha, al lado de **Motor activo**:

| Lo que ves | Qué significa | Qué hacer |
|---|---|---|
| **Actualizado** | Tienes la última versión | Nada |
| **Actualizar** *(parpadeando)* | Hay una versión nueva | Púlsalo |
| **Buscando…** | Está preguntando a GitHub | Esperar un momento |
| **Sin conexión** | No se pudo preguntar | Nada; se reintenta solo |

Al pulsarlo, BIMNEMO:

1. **Comprueba que no hay nada a medias.** Si está indexando un documento, se
   niega y te lo dice — cortar una indexación deja documentos incompletos.
2. **Descarga la versión nueva.**
3. **Reinicia el motor**, con una pantalla que va contando por dónde va.
4. **Recarga la ventana** cuando está listo.

Tarda entre diez segundos y un par de minutos. Normalmente unos ocho segundos.

### Si el botón no aparece

Significa que tu instalación no puede saber si hay versiones nuevas. Pasa si
descargaste BIMNEMO como ZIP en vez de instalarlo. **Instálalo con el
instalador** y el botón aparece.

---

## Cómo sabe que hay una versión nueva

Cada media hora le pregunta a GitHub cuál es la última versión publicada y la
compara con la tuya. Nada más: **no manda nada tuyo**, solo pregunta.

- Si no hay internet, el botón dice «Sin conexión» y ya está. **La aplicación
  funciona igual**; lo único que pierdes es el aviso.
- No consume datos apreciables: es una pregunta de unos pocos kilobytes.

---

## Cuando algo sale mal

### «El motor está indexando ahora mismo»

No es un error: es una negativa a propósito. Espera a que termine —la columna
**Estado** de la pestaña Archivos te dice por dónde va— y vuelve a pulsar.

### El botón se queda en «Sin conexión»

BIMNEMO no llega a internet. Suele ser el cortafuegos de la empresa o una red
sin salida. No afecta a nada más.

### La ventana no vuelve después de actualizar

Cierra BIMNEMO del todo y vuelve a abrirlo. Si sigue sin arrancar, ábrelo en
modo diagnóstico para ver el error:

```
BIMNEMO.bat --consola
```

Con lo que salga ahí, quien te da soporte sabrá qué pasó. **Tus memorias no se
pierden**: no dependen de la versión del programa.

### Quiero volver a la versión anterior

Descarga el instalador de la versión que quieras de
<https://github.com/CMEDUCATIVA/BIMNEMO/releases> y ejecútalo encima. Tus
datos siguen donde están.

---

## Lo que una actualización nunca hace

- **No borra memorias** ni documentos.
- **No cambia tu configuración** — ni tus claves, ni tu proveedor, ni tu idioma.
- **No sube nada tuyo.** Solo pregunta y descarga.
- **No se actualiza sola.** Avisa; pulsar lo decides tú.

---

## Para quien instaló BIMNEMO con `git clone`

Si eres de quien desarrolla y tienes el repositorio clonado, el botón funciona
igual pero por otro camino: compara commits contra `main` en vez de versiones
publicadas, y descarga con git.

**Cuidado con una diferencia:** si has modificado ficheros del programa,
actualizar los descarta. BIMNEMO te avisa antes y te deja elegir. Para
conservarlos:

```bash
git stash
git pull origin main
pip install -e .[api]
git stash pop
```

Después, **Motor → Reiniciar motor LightRAG**.

---

¿Eres quien **publica** BIMNEMO, no quien lo recibe? El ciclo completo —subir,
etiquetar y generar el instalador— está en
[`como_actualizar_bimnemo.md`](como_actualizar_bimnemo.md).
