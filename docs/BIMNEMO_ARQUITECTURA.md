# BIMNEMO por dentro

Para quien vaya a mantener o ampliar BIMNEMO. Si lo que quieres es usarlo,
mira [`BIMNEMO_INSTALAR.md`](BIMNEMO_INSTALAR.md); si publicarlo,
[`BIMNEMO_PUBLICAR.md`](BIMNEMO_PUBLICAR.md).

---

## Qué es, en una frase

**LightRAG con una aplicación de escritorio encima.** LightRAG es el motor
—trocea, extrae entidades, construye el grafo, responde—; BIMNEMO es todo lo
que hace falta para que eso sea usable sin abrir una terminal.

La regla que ordena el código: **no se reimplementa nada del motor.** Si
LightRAG ya sabe hacer algo, BIMNEMO importa su función y la usa. Reescribirla
produce dos versiones que acaban discrepando justo cuando importa.

---

## Dónde está cada cosa

```
lightrag/api/bimnemo/
├── __init__.py          nombre y versión del producto
├── catalog.py           extensión de fichero -> categoría (8 fijas)
├── desktop.py           el lanzador: abre la ventana y supervisa el motor
├── runtime.py           constantes compartidas, SIN imports (ver abajo)
├── envfile.py           leer y escribir el .env conservando el resto
├── stats.py             qué hay guardado, para el Panel
├── manifiesto.py        los endpoints que se le cuentan a una IA
├── actualizacion.py     ¿hay versión nueva? dos estrategias
├── paquete.py           traer una versión sin git (clientes)
├── provider_catalog*.py proveedores de LLM y embeddings
└── ui/                  la interfaz: HTML, CSS y módulos ES, sin compilar

lightrag/api/routers/
├── bimnemo_routes.py            memorias, grafo, búsqueda, manifiesto
├── bimnemo_engine_routes.py     con qué está corriendo
├── bimnemo_settings_routes.py   configuración, reinicio, clave de acceso
├── bimnemo_documents_routes.py  progreso, borrado, reintento
├── bimnemo_update_routes.py     actualización
└── nemo_query_routes.py         las rutas /nemo/{nemo}/…
```

### Por qué `runtime.py` no importa nada

Once módulos de LightRAG llaman a `load_dotenv(override=False)` al
importarse. El lanzador necesita dos constantes del servidor; importarlas de
donde vivían arrastraba `load_dotenv` al proceso supervisor, que entonces se
quedaba con una copia vieja del `.env` y **se la pasaba al motor al
reiniciar**.

Síntoma: «Guardar + Reiniciar» no aplicaba nada y solo funcionaba cerrar y
volver a abrir. Por eso `runtime.py` es un fichero sin un solo `import`.

---

## Las memorias (NEMO)

Cada memoria es un **workspace** de LightRAG: su directorio de almacenes, su
grafo, su estado de documentos. Un registro las lista y un gestor las
instancia bajo demanda.

**Lo que hay que saber al tocar esto:** `pipeline_status` es **por
workspace**. Las rutas oficiales de LightRAG (`/documents/pipeline_status`,
`/documents/delete_document`, `/graphs`) leen siempre la instancia **por
defecto**. Por eso existen equivalentes en `bimnemo_documents_routes.py`: no
por gusto, porque las oficiales contestan de otra memoria.

---

## La interfaz

**Sin compilación.** Módulos ES nativos y CSS con variables. Se edita un
fichero, se recarga la página. No hay `npm`, ni empaquetador, ni paso de
build que pueda romperse.

**Tope de 600 líneas por fichero.** Cuando uno lo pasa, se parte por función,
no por tamaño: `configuracion.js` se dividió porque *«reiniciar el motor»* y
*«montar un formulario»* son dos cosas distintas que estaban en el mismo
sitio.

### Cómo se mantiene viva la pantalla

Un solo vigilante (`archivos-progreso.js`) pregunta por `/bimnemo/progress`
cada 2 s mientras hay trabajo y cada 6 s en reposo, y **se para del todo con
la ventana oculta**.

La respuesta trae un **sello** —un resumen corto del estado de la memoria—.
Cuando cambia, la vista abierta se repinta. Una petición cubre las dos cosas:
la barra de progreso y el refresco.

> **Por qué no WebSockets ni SSE.** El servidor no tiene eventos que empujar:
> LightRAG no emite nada cuando cambia `doc_status`, el estado vive en un
> diccionario compartido. Un canal tendría que sondear ese diccionario por
> dentro — se pagaría toda la maquinaria (conexión persistente, reconexión,
> contrapresión) para acabar haciendo el mismo sondeo del lado del servidor.

---

## El reinicio del motor

Cambiar de proveedor o de modelo **obliga a reiniciar**: las funciones de LLM
y embeddings se construyen al arrancar y no hay forma honesta de sustituirlas
en caliente.

El motor sale con el código `77`, el lanzador lo levanta de nuevo, y la
ventana —que nunca se cerró— recarga sola. Entre 3,5 y 5 segundos, medido
sobre 148 reinicios.

> **La trampa que costó cuatro veces caer en ella:** la ruta de reinicio
> espera medio segundo antes de matarse, para que la respuesta salga por el
> socket. Durante ese rato **el proceso moribundo sigue contestando**. Quien
> espere a que `/health` responda vuelve demasiado pronto.
>
> Por eso el motor publica un `boot_id`, distinto en cada arranque, y la
> espera termina cuando ese valor **cambia**. No cuando alguien responde:
> cuando responde **otro**.

---

## La actualización

Un actualizador, **dos estrategias**, elegidas por lo que hay en el disco:

| Si hay… | Compara | Trae los ficheros con |
|---|---|---|
| `.git` y git funciona | commits contra `origin/main` | `git reset --hard` |
| lo demás | `VERSION` contra `/releases/latest` | el zipball de la versión |

La pantalla no se entera de cuál es: mismo botón, misma cortina, mismos
endpoints.

**Lo que nunca se toca** —`.env`, `inputs/`, `rag_storage/`, `.venv/`— no se
excluye con una lista: **no está en el paquete**, porque el paquete es lo que
git versiona. Una lista de exclusiones es algo que alguien olvida actualizar.

Eso además resuelve el problema de los ficheros bloqueados en Windows: como el
`.venv` no viaja, `python.exe` y las DLL no se tocan nunca, y los `.py` se
reemplazan en caliente.

---

## La API para agentes

`GET /bimnemo/memory/manifest` describe la memoria para que una IA la use sin
leer el OpenAPI entero. La lista vive en `manifiesto.py` —datos, no rutas— con
grupo, propósito y **el cuerpo de ejemplo** de cada llamada.

De las 32 rutas de BIMNEMO se publican **15**. Fuera quedan `restart`,
`settings`, `access` y `DELETE /bimnemo/nemos/{id}`: eso no es la memoria, es
el panel de mandos. Un agente que se equivoca borrando un documento pierde un
documento; borrando una memoria pierde meses.

La instrucción que el usuario copia **se genera del manifiesto**, no se
escribe aparte: dos listas acabarían discrepando, y la que discreparía sin que
nadie lo note es justo la que se pega en una skill y se olvida.

---

## Cómo se prueba

- **Batería de Python**: `pytest tests/api tests/bimnemo tests/workspace`.
  Línea base conocida: **16 fallan / 1404 pasan** — los 16 son de LightRAG y
  vienen de antes.
- **Navegador de verdad**, con Playwright. No vale asumir que un cambio de
  CSS funciona.

Tres lecciones que costaron tiempo y están escritas para no repetirlas:

1. **Cuando la captura y el número no coinciden, manda la captura.** Cuatro
   mediciones dieron falso negativo por medir en el sitio o el momento
   equivocados.
2. **La prueba tiene que costarle al programa lo mismo que al usuario.** Un
   PDF en blanco «demostró» que los PDF fallaban; un acta de un fragmento
   «demostró» que la barra no avanzaba; un documento de tres entidades
   «demostró» que borrar era instantáneo. Los tres eran la entrada, no el
   programa.
3. **Dos cosas que reinician el mismo proceso no pueden correr a la vez.**

---

## Lo que falta

- **El chat no recuerda la conversación.** `QueryRequest` acepta
  `conversation_history` y BIMNEMO nunca lo manda: cada pregunta se responde
  como si fuera la primera. Es el arreglo pequeño con más efecto pendiente.
- **Las conversaciones no se archivan.** Se pueden guardar con
  `POST /bimnemo/memory/remember`, pero hay que mandarlas.
- **`odt` y `epub`** se anuncian y no se indexan: faltan `odfpy` y
  `ebooklib`, que no vienen en el extra `[api]`.
- **Nombre duplicado al subir.** La ruta oficial responde 409; la de NEMO
  sobrescribe.
- **Sin icono propio** ni firma de código: Windows avisa al instalar.
- **`REPO` es una constante.** Si alguien bifurca, el aviso mira un
  repositorio y la descarga usa otro.
