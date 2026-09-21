<div align="center">

# BIMNEMO

**Memoria de conocimiento local para Windows.**

Le das tus documentos, construye con ellos un grafo de conocimiento y
responde preguntas sobre lo que contienen. Cualquier IA puede conectarse por
su API. Todo corre en tu ordenador: los documentos no salen de él.

[Descargar para Windows](https://github.com/CMEDUCATIVA/BIMNEMO/releases) ·
[Instalar](docs/BIMNEMO_INSTALAR.md) ·
[Cómo está hecho](docs/BIMNEMO_ARQUITECTURA.md)

</div>

---

## Qué hace

- **Memorias separadas.** Cada proyecto tiene la suya, con sus documentos y su
  grafo, sin mezclarse con las demás. Se crean, se renombran y se cambia de
  una a otra desde la barra superior.
- **Lee lo que ya tienes.** Documentos (PDF, Word…), hojas de cálculo,
  presentaciones, datos, texto y código: los extrae, los trocea y saca de
  ellos entidades y relaciones.
- **Un grafo que se puede recorrer.** Las entidades y sus relaciones, dentro de
  la silueta de un cerebro, con búsqueda, zoom y la ficha de cada entidad. Los
  impulsos que recorren las relaciones se encienden también cuando alguien
  consulta la memoria por la API.
- **Chat con fuentes.** Las respuestas dicen de qué documentos salen. Se puede
  preguntar a una memoria o a todas a la vez, y pedir solo el contexto
  recuperado sin que el modelo redacte.
- **Hecho para que otras IA lo usen.** La pantalla API enseña las rutas ya
  resueltas para la memoria abierta, y un botón copia todo lo que un agente
  necesita para empezar a usarla.
- **Tu proveedor de IA.** OpenAI, Anthropic (Claude), Google Gemini, Azure,
  DeepSeek, o un modelo local con Ollama o LM Studio, entre otros. Se
  configura desde la propia aplicación, sin editar ficheros.

## Las pantallas

| | |
|---|---|
| **Panel** | Las cifras de la memoria y el grafo de conocimiento |
| **Archivos** | Subir documentos, ver en qué punto está cada uno y borrarlos |
| **Chat** | Preguntar a la memoria |
| **Motor** | Qué modelos y almacenes está usando, y reiniciarlo |
| **Configuración IA** | Proveedor, modelos e idioma de la memoria |
| **API** | Cómo conectar una IA: rutas, ejemplos y acceso con clave |

Es una aplicación de escritorio de verdad, con ventana propia (Qt): no abre
un navegador. En el Administrador de tareas aparece como `bimnemo`.

## Instalar

### Con el instalador

Descarga `BIMNEMO-<versión>-instalador.exe` de
[Releases](https://github.com/CMEDUCATIVA/BIMNEMO/releases) y ejecútalo. Lleva
Python dentro: no hay que instalar nada más. La primera vez, entra en
**Configuración IA** y pon la clave de tu proveedor.

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

El extra `escritorio` es la ventana (Qt). Sin él arranca el motor y avisa de
que falta. El primer arranque crea el `.env` a partir de `env.example`; el
proveedor de IA se configura después desde la aplicación.

`BIMNEMO.bat --consola` enseña la salida del motor, para diagnosticar.
`BIMNEMO.bat --solo-motor` arranca el motor sin ventana, para usarlo solo
desde la API.

## Conectar una IA

El motor escucha en `http://127.0.0.1:9621`, solo en tu ordenador. Recuperar
contexto de la memoria abierta, sin gastar el modelo que redacta:

```bash
curl -X POST "http://127.0.0.1:9621/bimnemo/memory/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "¿Qué dicen los pliegos sobre plazos?", "mode": "mix"}'
```

Lo más cómodo es la pantalla **API**. **Copiar para la IA** copia la dirección,
los endpoints de la memoria abierta con sus cuerpos y los modos de
recuperación: se pega en la skill o en el agente y funciona. La documentación
interactiva completa está en `/docs` (Swagger) y `/redoc`.

Por defecto la API está abierta a los programas de tu ordenador. Desde la
pantalla API se puede exigir una clave: se genera, se guarda y se reinicia el
motor para que la pida.

## Documentación

| Quiero… | Documento |
|---|---|
| Instalarlo y empezar | [`docs/BIMNEMO_INSTALAR.md`](docs/BIMNEMO_INSTALAR.md) |
| Actualizarlo | [`como_actualizar.md`](como_actualizar.md) |
| Entender cómo está hecho | [`docs/BIMNEMO_ARQUITECTURA.md`](docs/BIMNEMO_ARQUITECTURA.md) |
| La ventana nativa: por qué y cómo | [`docs/BIMNEMO_INTERFAZ_NATIVA.md`](docs/BIMNEMO_INTERFAZ_NATIVA.md) |
| Mantenerlo: publicar, etiquetar, generar el instalador | [`como_actualizar_bimnemo.md`](como_actualizar_bimnemo.md) |
| El motor, LightRAG, en detalle | [`docs/LIGHTRAG_README.md`](docs/LIGHTRAG_README.md) |

## Créditos y licencia

BIMNEMO está construido sobre [LightRAG](https://github.com/HKUDS/LightRAG),
del equipo HKUDS, que hace la extracción, el grafo y la recuperación. Este
repositorio es LightRAG con BIMNEMO encima; el README original del motor está
en [`docs/LIGHTRAG_README.md`](docs/LIGHTRAG_README.md).

Licencia MIT, la misma de LightRAG: ver [`LICENSE`](LICENSE). Los iconos de la
interfaz son de [Bootstrap Icons](https://icons.getbootstrap.com/) (MIT).
