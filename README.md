<div align="center">

# BIMNEMO

**La memoria de tus proyectos, en tu ordenador.**

Le das la documentación de un proyecto y la convierte en una memoria a la que
puedes preguntar: qué dicen los pliegos sobre plazos, quién aprobó un cambio,
qué se acordó en un acta. Responde citando los documentos de donde sale cada
dato, y cualquier IA puede consultarla igual que tú.

Todo corre en tu ordenador. Los documentos no salen de él.

[Descargar para Windows](https://github.com/CMEDUCATIVA/BIMNEMO/releases) ·
[Instalar](docs/BIMNEMO_INSTALAR.md) ·
[Cómo está hecho](docs/BIMNEMO_ARQUITECTURA.md)

</div>

---

## Para qué sirve

La documentación de un proyecto crece más rápido de lo que nadie puede leerla:
pliegos, memorias, actas, informes, normativa, correos convertidos en PDF. La
respuesta a una pregunta concreta suele estar ahí, repartida entre varios
documentos, y encontrarla es cuestión de horas.

BIMNEMO la lee entera una vez y la organiza. Después:

- **Preguntas y responde con fuentes.** «¿Qué plazo de ejecución fija el
  contrato?» devuelve la respuesta y de qué documentos sale, para poder
  comprobarla.
- **Ves cómo se relaciona todo.** Personas, empresas, documentos, fases,
  requisitos: BIMNEMO los reconoce y dibuja un grafo con sus relaciones. Se
  recorre, se busca y se abre la ficha de cada elemento.
- **Tus herramientas de IA lo usan.** Un asistente, un agente o una skill se
  conectan a la memoria por su API y la consultan antes de responder, en vez
  de inventar.

## Cómo funciona

1. **Creas una memoria por proyecto.** Cada una guarda sus documentos y su
   grafo aparte, sin mezclarse con las demás. Se cambia de una a otra desde la
   barra superior.
2. **Subes los documentos.** Documentos (PDF, Word…), hojas de cálculo,
   presentaciones, datos, texto y código. BIMNEMO los lee, los trocea y saca
   de ellos lo que importa y cómo se relaciona.
3. **Preguntas.** Desde el chat, a una memoria o a todas a la vez. O pides
   solo los fragmentos que encontró, sin que el modelo redacte nada.
4. **Conectas otras IA.** La pantalla API te da las rutas ya preparadas para
   la memoria abierta y un botón que copia todo lo que un agente necesita.

El trabajo de entender los documentos lo hace un modelo de IA del proveedor
que elijas: OpenAI, Anthropic (Claude), Google Gemini, Azure, DeepSeek, o un
modelo local con Ollama o LM Studio, entre otros. Con un modelo local, nada
sale de tu ordenador en ningún momento.

## Las pantallas

| | |
|---|---|
| **Panel** | Lo que hay en la memoria y el grafo de conocimiento, con la silueta de un cerebro |
| **Archivos** | Subir documentos, ver en qué punto está cada uno y borrarlos |
| **Chat** | Preguntar a la memoria |
| **Motor** | Qué modelos y almacenes está usando, y reiniciarlo |
| **Configuración IA** | Proveedor, modelos e idioma de la memoria |
| **API** | Cómo conectar una IA: rutas, ejemplos y acceso con clave |

Es una aplicación de escritorio con ventana propia; no abre un navegador. En
el Administrador de tareas aparece como `bimnemo`.

## Instalar

### Con el instalador

Descarga `BIMNEMO-<versión>-instalador.exe` de
[Releases](https://github.com/CMEDUCATIVA/BIMNEMO/releases) y ejecútalo. No
hay que instalar nada más. La primera vez, entra en **Configuración IA** y pon
la clave de tu proveedor.

Los detalles, y qué hacer si algo falla, están en
[`docs/BIMNEMO_INSTALAR.md`](docs/BIMNEMO_INSTALAR.md).

### Desde el código

Hace falta Python 3.10 o posterior.

```bat
git clone https://github.com/CMEDUCATIVA/BIMNEMO.git
cd BIMNEMO
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[api,escritorio]"
BIMNEMO.bat
```

El extra `escritorio` es la ventana. Sin él arranca solo el motor y avisa de
lo que falta. El proveedor de IA se configura después desde la aplicación.

`BIMNEMO.bat --consola` enseña la salida del motor, para diagnosticar.
`BIMNEMO.bat --solo-motor` arranca el motor sin ventana, para usarlo solo
desde la API.

## Conectar una IA

BIMNEMO escucha en `http://127.0.0.1:9621`, solo en tu ordenador. Así se
recupera contexto de la memoria abierta, sin gastar el modelo que redacta:

```bash
curl -X POST "http://127.0.0.1:9621/bimnemo/memory/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "¿Qué dicen los pliegos sobre plazos?", "mode": "mix"}'
```

Lo más cómodo es la pantalla **API**. **Copiar para la IA** copia la dirección,
las rutas de la memoria abierta con lo que hay que mandar a cada una y los
modos de búsqueda: se pega en la skill o en el agente y funciona. La
documentación interactiva completa está en `/docs` (Swagger) y `/redoc`.

Por defecto la API está abierta a los programas de tu ordenador. Desde la
pantalla API se puede exigir una clave: se genera, se guarda y BIMNEMO se
reinicia para empezar a pedirla.

## Documentación

| Quiero… | Documento |
|---|---|
| Instalarlo y empezar | [`docs/BIMNEMO_INSTALAR.md`](docs/BIMNEMO_INSTALAR.md) |
| Actualizarlo | [`como_actualizar.md`](como_actualizar.md) |
| Entender cómo está hecho | [`docs/BIMNEMO_ARQUITECTURA.md`](docs/BIMNEMO_ARQUITECTURA.md) |
| La ventana de escritorio: por qué y cómo | [`docs/BIMNEMO_INTERFAZ_NATIVA.md`](docs/BIMNEMO_INTERFAZ_NATIVA.md) |
| Mantenerlo: publicar, etiquetar, generar el instalador | [`como_actualizar_bimnemo.md`](como_actualizar_bimnemo.md) |

## Licencia

MIT: ver [`LICENSE`](LICENSE).
