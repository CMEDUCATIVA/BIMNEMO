# Instalar BIMNEMO

BIMNEMO es una memoria de conocimiento que funciona **en tu ordenador**. Subes
documentos, los entiende, y después le preguntas. Tus documentos no salen de
tu máquina.

---

## Lo que necesitas

| | |
|---|---|
| Windows | 10 u 11, de 64 bits |
| Espacio en disco | **1 GB** (el programa ocupa 300 MB; el resto es para tus documentos y memorias) |
| Internet | Solo para instalar, para actualizar y para el modelo de IA |
| Una clave de API | De OpenAI, Google u otro proveedor. Es lo único que tiene coste |

**No hace falta instalar Python ni nada más.** El instalador lo lleva todo
dentro.

---

## Instalar

1. Descarga el instalador de
   <https://github.com/CMEDUCATIVA/BIMNEMO/releases> — el fichero
   `BIMNEMO-x.y.z-instalador.exe` de la versión más reciente.

2. Ejecútalo.

   > **Windows te va a avisar** con una pantalla azul que dice *«Windows
   > protegió tu PC»*. Es porque el instalador no está firmado con un
   > certificado comercial, no porque tenga nada malo. Pulsa **Más
   > información** → **Ejecutar de todas formas**.

3. Acepta la carpeta que propone. Se instala en tu carpeta personal a
   propósito: así BIMNEMO puede actualizarse solo, sin pedirte permisos de
   administrador cada vez.

4. Al terminar, se abre.

---

## Configurar el modelo de IA

BIMNEMO necesita un modelo de IA para entender tus documentos. La primera vez
hay que decirle cuál y darle tu clave.

1. Ve a **Configuración IA**.
2. Elige el proveedor (OpenAI, Google, Anthropic…) y el modelo.
3. Pega tu clave de API.
4. **Guardar** y después **Reiniciar el motor**. La ventana vuelve sola.

### ¿Dónde consigo una clave?

Depende del proveedor. Para OpenAI: <https://platform.openai.com/api-keys>.
Necesitas una cuenta con saldo — **una clave sin saldo parece que no funciona
pero está bien**; lo que falla es la cuenta.

### ¿Cuánto cuesta?

Se paga por documento indexado y por pregunta, al proveedor, no a BIMNEMO.
Indexar es lo que más cuesta: un documento de diez páginas son unos pocos
céntimos. Preguntar es mucho más barato.

BIMNEMO guarda en caché las respuestas del modelo, así que repetir una
pregunta parecida no se vuelve a pagar.

---

## Primeros pasos

1. **Archivos** → arrastra un documento. Admite 41 formatos: PDF, Word, Excel,
   PowerPoint, Markdown, CSV, texto y código.
2. La columna **Estado** te dice por dónde va: *En cola* → *Indexando 3/6* →
   *En memoria*.
3. **Panel** → mira el grafo: las personas, obras, plazos y conceptos que
   encontró, y cómo se relacionan.
4. **Chat** → pregúntale.

### Varias memorias

Arriba hay un selector. Cada memoria es independiente: sus documentos, su
grafo, sus respuestas. Útil para separar proyectos — una obra no contamina las
respuestas de otra.

El botón **+** crea una; la papelera borra la que está abierta, pidiendo que
escribas su nombre para confirmar.

---

## Dónde queda todo

Dentro de la carpeta de instalación:

| Carpeta | Qué hay |
|---|---|
| `inputs\` | Tus documentos, tal como los subiste |
| `rag_storage\` | Lo que el motor aprendió de ellos |
| `.env` | Tu configuración y tus claves |

**Haz copia de esas tres cosas** si tu trabajo importa. Ni el instalador ni las
actualizaciones las tocan, pero un disco que se rompe sí.

---

## Actualizar

Un botón en la barra superior avisa cuando hay versión nueva. Ver
[`como_actualizar.md`](../como_actualizar.md).

---

## Desinstalar

Desde *Configuración de Windows → Aplicaciones*, o el acceso directo
**Desinstalar BIMNEMO**.

> **Desinstalar NO borra tus datos.** Tus documentos, memorias y configuración
> se quedan en la carpeta de instalación. Si quieres borrarlos de verdad,
> elimina esa carpeta a mano después.
>
> Es a propósito: un desinstalador que se lleva por delante meses de trabajo
> es un desastre del que nadie se recupera.

---

## Si algo no va

**No arranca.** Ábrelo en modo diagnóstico y guarda lo que salga:

```
BIMNEMO.bat --consola
```

**Dice que el modelo falla.** Casi siempre es la cuenta, no la clave: sin
saldo, el proveedor rechaza las peticiones. La pestaña **Panel** te enseña el
motivo exacto que devolvió el proveedor.

**Un documento se queda en «Fallido».** Pasa el ratón por encima del estado:
ahí está la razón. Los formatos `odt` y `epub` no se indexan todavía aunque
aparezcan en la lista.
