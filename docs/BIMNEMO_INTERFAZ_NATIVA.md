# La interfaz nativa de BIMNEMO

Plan de la reestructuración que sustituye la ventana de navegador por una
ventana de Windows de verdad.

---

## Por qué

BIMNEMO enseñaba su interfaz abriendo **una segunda copia completa de Chrome**
con un perfil aparte. Medido en una máquina real: **8 procesos y 487 MB**, al
lado de los 40 procesos y 5,4 GB del Chrome que el usuario ya tenía abierto.
En el Administrador de tareas la aplicación aparecía como *Google Chrome*, no
como BIMNEMO.

Se evaluaron cuatro salidas. La decisión fue la más cara: **interfaz nativa,
sin motor web**. Conviene dejar escrito lo que cuesta, porque dentro de tres
meses no se recordará:

- Se rehacen **10.751 líneas** de interfaz ya escrita y en funcionamiento
  (30 módulos JS, 10 hojas CSS, `index.html`).
- **No se gana ninguna función.** La aplicación hará exactamente lo mismo.
- Lo que se gana es esto: un proceso en vez de diez, ~80 MB en vez de 487, y
  que Windows diga «BIMNEMO».

## Lo que NO se toca

> **Actualización (1.4):** la interfaz web se retiró cuando la ventana nativa
> tuvo sus seis pantallas y pasó a ser la de por defecto. Lo que sigue en este
> apartado es el plan tal como se escribió.

**La interfaz web se queda** mientras se construye la nativa: se sigue
sirviendo en `/bimnemo-app/` y es el modo `--navegador`, el plan B si la
ventana nativa falla en el ordenador de alguien.

**La API tampoco.** Es la superficie de integración y la parte que un cliente
puede automatizar. La interfaz nativa es **otro cliente más** de esa API.

---

## Arquitectura

```
   bimnemo.exe                          bimnemo.exe
   ┌──────────────────────┐             ┌────────────────────┐
   │  ventana nativa (Qt) │   HTTP      │  motor LightRAG    │
   │  lightrag/api/       │ ──────────► │  127.0.0.1:9621    │
   │    bimnemo/nativo/   │             │                    │
   └──────────────────────┘             └────────────────────┘
                                                 │
                                                 └─ /bimnemo-app/  (interfaz
                                                    web, sigue viva)
```

**La ventana habla con el motor por HTTP, no lo importa.** Podría importar
LightRAG directamente y ahorrarse el salto, y sería un error:

- El **reinicio del motor** —una de las cosas más estables que tiene, 148
  reinicios medidos entre 3,5 y 4,8 segundos— funciona *porque* el motor es
  un proceso aparte que se puede matar y levantar. Importándolo, habría que
  reiniciar la ventana entera.
- Un fallo del motor tumbaría la ventana con él, y el usuario se quedaría sin
  la pantalla que le explica qué pasó.
- Son **los mismos endpoints** que usa la interfaz web. Un solo camino que
  mantener, no dos.

### Nada de hilos para las peticiones

Se usa `QNetworkAccessManager`, que es asíncrono y de Qt. La alternativa
—`urllib` dentro de un `QThread`— obliga a vigilar en cada sitio que nadie
toque un widget desde el hilo equivocado, y ese error no se ve hasta que se
ve: la aplicación se cierra sola, sin rastro, en el ordenador de otro.

---

## Etapas

Cada una termina con la aplicación **arrancando y verificada**, no a medias.

| | Etapa | Qué entra |
|---|---|---|
| 1 | **Armazón** | Ventana, barra superior, navegación lateral, tema, versión. Sin contenido |
| 2 | **Motor y Configuración IA** | Las dos más simples, y prueban el reinicio de punta a punta |
| 3 | **Archivos** | Tabla, arrastrar y soltar, estado con barra de progreso, borrado |
| 4 | **Panel** | Cifras y **el grafo de conocimiento** — con diferencia lo más difícil |
| 5 | **Chat** | Conversación y envío |
| 6 | **API** | Lista de endpoints, agrupada, con copiar |

Hasta terminar la etapa 6, la ventana nativa se pedía con `--nativo` y la de
navegador era la de por defecto. Cambiar el valor por defecto fue lo último,
no lo primero: así nunca hubo una versión publicada en la que el usuario se
quedara sin pantallas. Hecho en la 1.4; `--nativo` se sigue aceptando.

---

## Qt: lo que añade al paquete

`PySide6-Essentials` ocupa **205 MB** instalado. Sin podar, el paquete pasaría
de 287 a ~492 MB y el instalador de 71 a ~150 MB.

Se poda igual que la biblioteca estándar, porque una aplicación de ventanas
(Widgets) no usa casi nada de eso:

| Fuera | |
|---|---|
| `qml/`, `Qt6Qml`, `Qt6Quick*`, `qmlls.exe` | 19 MB — es el otro juego de interfaces de Qt, el declarativo |
| `translations/` menos el español | 13 MB |
| `Qt6Designer*` | 7 MB — el editor visual, herramienta de desarrollo |
| `metatypes/`, `include/`, `typesystems/`, `scripts/` | 8 MB — para compilar contra Qt, no para ejecutar |

Objetivo: **60-70 MB**, instalador en torno a 95 MB.

`opengl32sw.dll` son 19,7 MB y **se queda**: es el dibujado por software, el
que salva a las máquinas virtuales, los escritorios remotos y los ordenadores
sin controlador de vídeo decente. Quitarlo ahorra 20 MB y deja la ventana en
negro en el sitio menos oportuno.

---

## El tema

Los colores **no se inventaron**: salieron de `ui/css/tokens.css` de la web.
Retirada la web, la tabla vive en `nativo/tema.py` y es la única fuente.

| | Claro | Oscuro |
|---|---|---|
| Azul de marca | `#2563eb` | `#3b82f6` |
| Fondo | `#ffffff` | `#020617` |
| Superficie elevada | — | `#0f172a` |
| Texto principal | — | `#f1f5f9` |
| Borde | — | `#1e293b` |

Se traducen a una hoja de estilo de Qt (`QSS`) generada desde esa tabla, no
copiada a mano en cada widget.

---

## Riesgos, por orden de probabilidad

**El grafo de conocimiento (etapa 4).** En la web es un lienzo con una
simulación de fuerzas ya escrita. En Qt hay que rehacerla sobre
`QGraphicsView`: distribución, zoom, arrastre, selección. Es la etapa que
puede costar más que las otras cinco juntas.

**El paquete deja de ser Python puro.** Qt son DLL nativas. La comprobación de
que el paquete funciona fuera de su carpeta —la que ya salvó dos versiones—
pasa a ser obligatoria en cada construcción, no recomendable.

**La poda de Qt.** Quitar una DLL que hacía falta da un error al arrancar en
el ordenador de un cliente, no aquí. Cada poda se verifica copiando el paquete
a una ruta ajena y arrancándolo, igual que se hace con el intérprete.
