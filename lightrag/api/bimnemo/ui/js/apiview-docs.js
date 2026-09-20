/* ==========================================================================
   BIMNEMO — Swagger y ReDoc, dentro de la aplicación
   --------------------------------------------------------------------------
   Antes eran dos enlaces con `target="_blank"`: para leer la documentación
   había que irse a una pestaña del navegador y salir de BIMNEMO. Ahora se
   abren aquí, en sus propias solapas.

   ## Dos documentos con dos problemas distintos

   | | Swagger | ReDoc |
   |---|---|---|
   | Sus ficheros | `/static/swagger-ui/` — **locales** | `cdn.jsdelivr.net` — **de internet** |
   | Sin conexión | Funciona | **Se queda en blanco** |

   BIMNEMO es una aplicación de escritorio y puede estar sin conexión. Un
   marco en blanco parece una avería del programa, así que cuando ReDoc no
   carga **se dice**, con la salida de abrirlo fuera. Un rectángulo vacío sin
   explicación es lo peor que se puede enseñar.

   ## Se cargan al entrar, no antes

   Cada marco se crea cuando se pulsa su solapa. Cargar dos documentos
   completos —uno de ellos yendo a internet— para que quizá nadie los mire es
   pagar por nada.
   ========================================================================== */

import { ROOT } from './api.js';
import { icon } from './icons.js';
import { escape } from './format.js';

/** Cuánto se espera a que ReDoc dé señales antes de dar por hecho que no viene. */
const PACIENCIA_REDOC = 12000;

const DOCS = {
  swagger: {
    ruta: '/docs',
    titulo: 'Swagger',
    // Swagger trae sus ficheros del propio servidor, así que nunca falla por
    // falta de conexión y no hace falta vigilarlo.
    vigilar: false,
  },
  redoc: {
    ruta: '/redoc',
    titulo: 'ReDoc',
    vigilar: true,
  },
};

const caja = () => document.getElementById('api-doc');

/** Lo ya cargado, para no rehacer el marco cada vez que se vuelve. */
const montados = new Set();

function direccion(ruta) {
  return `${window.location.origin}${ROOT}${ruta}`;
}

function marcaje(clave) {
  const doc = DOCS[clave];
  const url = direccion(doc.ruta);
  return `
    <div class="doc" data-doc="${escape(clave)}">
      <div class="doc__barra">
        <span class="doc__url tabular" title="${escape(url)}">${escape(url)}</span>
        <a class="btn btn--ghost" href="${escape(url)}" target="_blank" rel="noopener">
          ${icon('external-link', 12)} Abrir fuera
        </a>
      </div>
      <div class="doc__aviso" hidden></div>
      <iframe class="doc__frame" src="${escape(url)}"
              title="${escape(doc.titulo)}" loading="lazy"></iframe>
    </div>`;
}

/**
 * Vigila que ReDoc llegue a pintar algo.
 *
 * No basta con el evento `load` del marco: la página carga igual sin internet
 * y se queda vacía, porque lo que falta es el guion que baja del CDN. Así que
 * se mira **el contenido** del documento pasado un rato.
 *
 * Si el navegador no deja leerlo, se calla: no poder comprobarlo no es motivo
 * para acusar a nadie de estar roto.
 */
function vigilar(nodo) {
  const frame = nodo.querySelector('.doc__frame');
  const aviso = nodo.querySelector('.doc__aviso');

  window.setTimeout(() => {
    let vacio = false;
    try {
      const doc = frame.contentDocument;
      vacio = !!doc && doc.body && doc.body.innerText.trim().length < 20;
    } catch {
      return; // otro origen: no se puede saber, y no pasa nada
    }
    if (!vacio) return;

    aviso.hidden = false;
    aviso.innerHTML = `
      <div class="notice notice--warn">
        <span class="notice__icon">${icon('triangle-alert', 14)}</span>
        <span>
          <strong>ReDoc no ha cargado.</strong> Se descarga de internet
          (<code>cdn.jsdelivr.net</code>), así que sin conexión no puede
          dibujarse. <strong>Swagger sí funciona sin conexión</strong>: sus
          ficheros vienen de este mismo ordenador.
        </span>
      </div>`;
  }, PACIENCIA_REDOC);
}

/**
 * Enseña una de las dos documentaciones.
 *
 * @param {'swagger'|'redoc'} clave
 */
export function mostrarDoc(clave) {
  const host = caja();
  if (!host || !DOCS[clave]) return;

  if (!montados.has(clave)) {
    host.insertAdjacentHTML('beforeend', marcaje(clave));
    montados.add(clave);
    const nodo = host.querySelector(`[data-doc="${clave}"]`);
    if (DOCS[clave].vigilar) vigilar(nodo);
  }

  host.hidden = false;
  host.querySelectorAll('.doc').forEach((n) => {
    n.hidden = n.dataset.doc !== clave;
  });
}

/** Esconde las documentaciones sin descargarlas: volver debe ser instantáneo. */
export function ocultarDocs() {
  const host = caja();
  if (host) host.hidden = true;
}
