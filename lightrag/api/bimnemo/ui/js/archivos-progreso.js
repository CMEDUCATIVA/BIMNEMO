/* ==========================================================================
   BIMNEMO — Vigilante de la memoria activa
   --------------------------------------------------------------------------
   Hace dos cosas con **una sola** petición cada pocos segundos:

   1. **La barra de indexado**, que vive **dentro de la columna de estado de
      cada fila** — no en un recuadro aparte. Existe por una pregunta que la
      pantalla no sabía contestar: «¿está bloqueado o no?».
   2. **Mantener la pantalla viva.** Cada vista pedía sus datos al entrar y se
      quedaba con ellos: si terminaba un indexado o se borraba un archivo, la
      pantalla no se enteraba hasta pulsar «Actualizar».

   ## Por qué se sondea y no se abre un canal

   La tentación es SSE o WebSockets. No compensan aquí, y el motivo es
   concreto: **el servidor no tiene eventos que empujar**. LightRAG no emite
   nada cuando cambia `doc_status`; el estado vive en un diccionario
   compartido. Un canal tendría que sondear ese diccionario por dentro para
   saber qué mandar — se pagaría toda la maquinaria (conexión persistente,
   reconexión, contrapresión) para acabar haciendo el mismo sondeo, solo que
   del lado del servidor.

   Lo que sí se hace para que salga barato:

   - una petición cubre las dos cosas;
   - cada 2 s mientras hay trabajo, cada 6 s en reposo;
   - **se para del todo con la ventana oculta**, que en un escritorio es la
     mitad del tiempo.
   ========================================================================== */

import { getProgress } from './api.js';
import { currentNemo } from './nemo.js';

/** Cadencia mientras el motor trabaja, y cuando no. */
const CADENCIA_ACTIVA = 2000;
const CADENCIA_REPOSO = 6000;

/**
 * Cuánto se espera sin que nadie trabaje antes de decir que algo va mal.
 *
 * Documentos en cola y la tubería parada es normal un instante —acaban de
 * encolarse— y sospechoso a los veinte segundos. Avisar al primer sondeo
 * sería gritar por nada.
 */
const PACIENCIA = 20000;

let temporizador = null;
let cadencia = CADENCIA_REPOSO;
let paradoDesde = null;
let alCambiar = null;
let revision = null;

/**
 * El último sondeo.
 *
 * Cuando la tabla se repinta, las barras nacen vacías y habría que esperar al
 * siguiente sondeo —hasta dos segundos— para verlas avanzar. Con el último
 * valor guardado, `repintarBarras()` las deja puestas en el mismo instante en
 * que aparecen.
 */
let ultimo = null;

/* --- Las barras de las filas ---------------------------------------------- */

/** Las barras que haya ahora mismo en la tabla. */
const barras = () => document.querySelectorAll('#files-body .estado-barra');

function limpiar() {
  paradoDesde = null;
  barras().forEach((n) => {
    n.dataset.modo = 'espera';
    n.querySelector('.estado-barra__pct').textContent = '';
  });
}

/**
 * Escribe el avance sobre las barras que ya están en el DOM.
 *
 * Se escribe el ancho a mano en vez de repintar la tabla porque repintarla
 * cada dos segundos perdería el hover, el foco y lo que el usuario esté
 * señalando. La tabla se repinta solo cuando el sello cambia.
 *
 * El motor publica **un** recuento de fragmentos para toda la tubería, así que
 * el número se le pone a la fila que de verdad está `processing`. Las demás se
 * quedan indeterminadas: enseñarles un porcentaje ajeno sería peor que no
 * enseñar ninguno.
 */
function pintar(p) {
  const atascado = p.stalled && paradoDesde && Date.now() - paradoDesde > PACIENCIA;
  const hayNumero = p.busy && p.chunk_total > 0;

  barras().forEach((n) => {
    const relleno = n.querySelector('.estado-barra__fill');
    const texto = n.querySelector('.estado-barra__pct');

    if (atascado) {
      n.dataset.modo = 'parado';
      texto.textContent = 'Sin avanzar';
      n.title =
        'El motor lleva un rato sin procesar. Puede que el modelo no ' +
        'responda o que falte configuración.';
      return;
    }

    n.title = '';
    if (n.dataset.estado === 'processing' && hayNumero) {
      const pct = Math.min(100, Math.round((p.chunk_done / p.chunk_total) * 100));
      n.dataset.modo = 'avance';
      relleno.style.width = `${pct}%`;
      texto.textContent = `${pct}% · ${p.chunk_done}/${p.chunk_total}`;
    } else {
      n.dataset.modo = 'espera';
      relleno.style.width = '';
      texto.textContent = '';
    }
  });
}

/* --- El sondeo ------------------------------------------------------------ */

function reprogramar(ms) {
  if (cadencia === ms && temporizador) return;
  cadencia = ms;
  if (temporizador) window.clearInterval(temporizador);
  temporizador = window.setInterval(mirar, ms);
}

async function mirar() {
  let p;
  try {
    p = await getProgress(currentNemo());
  } catch {
    // El motor puede estar reiniciándose: no es momento de alarmar a nadie.
    return;
  }

  ultimo = p;

  if (p.busy || p.working > 0) {
    if (p.stalled) {
      if (paradoDesde === null) paradoDesde = Date.now();
    } else {
      paradoDesde = null;
    }
    pintar(p);
    reprogramar(CADENCIA_ACTIVA);
  } else {
    limpiar();
    reprogramar(CADENCIA_REPOSO);
  }

  // Refrescar solo cuando algo cambió de verdad. El primer sondeo únicamente
  // toma la referencia: repintar al arrancar sería trabajo por nada.
  if (revision !== null && p.revision && p.revision !== revision && alCambiar) {
    alCambiar();
  }
  if (p.revision) revision = p.revision;
}

/**
 * Vuelve a poner el avance sobre unas barras recién creadas.
 *
 * Lo llama la tabla al terminar de pintarse. Sin sondeo previo no hace nada.
 */
export function repintarBarras() {
  if (ultimo && (ultimo.busy || ultimo.working > 0)) pintar(ultimo);
}

/* --- Arranque y parada ---------------------------------------------------- */

/**
 * Empieza a vigilar la memoria activa.
 *
 * @param {() => void} cuandoCambie  Qué hacer cuando el estado de la memoria
 *        cambie: lo decide quien llama, porque depende de la vista abierta.
 */
export function watchProgress(cuandoCambie) {
  if (cuandoCambie) alCambiar = cuandoCambie;
  if (temporizador) return;
  mirar();
  temporizador = window.setInterval(mirar, cadencia);
}

/**
 * Mira **ahora** y pasa a cadencia activa.
 *
 * `watchProgress()` no sirve para esto: si ya hay temporizador se sale en la
 * primera línea, así que tras un borrado se podían perder hasta los seis
 * segundos de la cadencia en reposo antes de la primera mirada. Lo llaman las
 * acciones que cambian la memoria de golpe: borrar y reintentar.
 */
export function despertar() {
  reprogramar(CADENCIA_ACTIVA);
  mirar();
}

/** Deja de vigilar. */
export function detener() {
  if (temporizador) {
    window.clearInterval(temporizador);
    temporizador = null;
  }
}

/**
 * Reinicia la vigilancia al cambiar de memoria.
 *
 * El estado de la tubería y el sello son **por NEMO**: dejar los de la
 * anterior contaría el trabajo de otra memoria y dispararía un refresco falso.
 */
export function resetProgress() {
  detener();
  limpiar();
  revision = null;
  watchProgress();
}

/**
 * Deja de sondear con la ventana oculta.
 *
 * En un escritorio la ventana pasa oculta la mitad del tiempo, y preguntar
 * cada pocos segundos por algo que nadie mira es trabajo regalado. Al volver
 * se mira enseguida, para no enseñar datos de hace un rato.
 */
export function mountProgressVisibility() {
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) detener();
    else watchProgress();
  });
}
