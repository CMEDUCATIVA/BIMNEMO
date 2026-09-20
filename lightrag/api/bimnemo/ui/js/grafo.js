/* ==========================================================================
   BIMNEMO — Grafo de conocimiento (tarjeta del Panel)
   --------------------------------------------------------------------------
   Pide el subgrafo de la memoria activa, lo pinta con el lienzo y ofrece las
   opciones para recorrerlo: entidad de partida, profundidad, tope de nodos,
   búsqueda y ficha de la entidad seleccionada.
   ========================================================================== */

import { getGraph, getGraphStats } from './api.js';
import { currentNemo } from './nemo.js';
import { assignColors, createLienzo } from './grafo-lienzo.js';
import { LAYOUTS } from './grafo-disposicion.js';
import { icon } from './icons.js';
import { count, escape } from './format.js';

/** Entidades que se ofrecen en el selector de partida. */
const MAX_OPTIONS = 300;

const state = {
  label: '*',
  depth: 3,
  max: 250,
  layout: 'fuerzas',
  nodes: [],
  colors: new Map(),
};

let lienzo = null;
let loading = false;

/**
 * Algo cambió por detrás y lo dibujado ya no vale.
 *
 * No se recarga en el momento porque leer el grafo es la petición más cara del
 * Panel y no tiene sentido pagarla para una pestaña que nadie está mirando.
 */
let obsoleto = false;

const $ = (id) => document.getElementById(id);

/* --- Ficha de la entidad -------------------------------------------------- */

function renderInspector(node) {
  const box = $('graph-inspector');
  if (!node) {
    box.hidden = true;
    box.innerHTML = '';
    return;
  }

  const color = state.colors.get(node.type) || 'slate';
  box.hidden = false;
  box.innerHTML = `
    <div class="ficha__head">
      <span class="ficha__dot" data-color="${escape(color)}"></span>
      <span class="ficha__name truncate" title="${escape(node.label)}">${escape(node.label)}</span>
      <button type="button" class="btn btn--ghost btn--icon" id="graph-close"
              title="Cerrar la ficha" aria-label="Cerrar la ficha"></button>
    </div>
    <div class="ficha__meta">
      <span class="ficha__pill" data-color="${escape(color)}">${escape(node.type)}</span>
      <span>${escape(count(node.degree))} ${node.degree === 1 ? 'relación' : 'relaciones'}</span>
    </div>
    ${node.description
      ? `<p class="ficha__text">${escape(node.description)}</p>`
      : '<p class="ficha__text ficha__text--muted">Sin descripción.</p>'}
    ${node.file_path
      ? `<p class="ficha__source">${icon('file-text', 12)}<span class="truncate"
           title="${escape(node.file_path)}">${escape(node.file_path)}</span></p>`
      : ''}
    <button type="button" class="btn" id="graph-expand">
      ${icon('network', 13)}
      Explorar desde aquí
    </button>`;

  $('graph-close').innerHTML = icon('x', 13);
  $('graph-close').onclick = () => {
    renderInspector(null);
    lienzo.repaint();
  };
  // «Explorar desde aquí» re-consulta al motor con esta entidad como raíz: no
  // es un zoom, es traer los vecinos que el tope de nodos dejó fuera.
  $('graph-expand').onclick = () => {
    state.label = node.label;
    $('graph-label').value = node.label;
    load();
  };
}

/* --- Leyenda y selector --------------------------------------------------- */

function renderLegend(types) {
  $('graph-legend').innerHTML = types.length
    ? types
        .map(
          (t) => `
        <span class="legend__item" data-color="${escape(state.colors.get(t.type) || 'slate')}">
          <span class="legend__dot"></span>
          <span>${escape(t.type)}</span>
          <span class="legend__pct">${escape(count(t.count))}</span>
        </span>`
        )
        .join('')
    : '';
}

/**
 * Rellena el selector de entidad de partida.
 *
 * Se ofrecen las entidades del subgrafo que hay pintado, ordenadas por número
 * de relaciones. No es el catálogo completo de la memoria —para eso habría
 * que leerla entera— pero sí es el camino natural: se salta de lo que se ve a
 * lo que hay alrededor.
 */
function renderOptions() {
  const select = $('graph-label');
  const ordered = [...state.nodes].sort(
    (a, b) => b.degree - a.degree || a.label.localeCompare(b.label)
  );
  const seen = new Set();
  const options = ['<option value="*">Todo el grafo</option>'];

  ordered.slice(0, MAX_OPTIONS).forEach((node) => {
    if (seen.has(node.label)) return;
    seen.add(node.label);
    options.push(
      `<option value="${escape(node.label)}">${escape(node.label)}</option>`
    );
  });

  // Si la raíz elegida ya no sale entre las opciones, se añade: perderla del
  // selector haría que el desplegable contradijese a lo que está dibujado.
  if (state.label !== '*' && !seen.has(state.label)) {
    options.push(
      `<option value="${escape(state.label)}">${escape(state.label)}</option>`
    );
  }

  select.innerHTML = options.join('');
  select.value = state.label;
}

/* --- Vacíos y errores ----------------------------------------------------- */

function showEmpty(html) {
  const box = $('graph-empty');
  box.hidden = !html;
  box.innerHTML = html || '';
}

function emptyReason(total) {
  if (total.supported && total.entities > 0) {
    return `${icon('search', 22)}
      <p><strong>Sin resultados para esta partida.</strong></p>
      <p>La memoria tiene ${escape(count(total.entities))} entidades, pero
         «${escape(state.label)}» no llegó a ninguna. Vuelve a «Todo el grafo».</p>`;
  }
  return `${icon('network', 22)}
    <p><strong>Esta memoria todavía no tiene grafo.</strong></p>
    <p>El grafo lo construye el motor al indexar: extrae entidades y relaciones
       de cada documento con el modelo de lenguaje configurado. Sube archivos y
       aparecerá aquí.</p>`;
}

/* --- Carga ---------------------------------------------------------------- */

async function load() {
  if (loading) return;
  loading = true;
  obsoleto = false;
  const boton = $('graph-reload');
  boton.disabled = true;
  $('graph-hint').textContent = 'Leyendo el grafo…';

  try {
    // Dos lecturas distintas: el recuento total de la memoria y el subgrafo
    // acotado que se dibuja. Decir solo el segundo haría creer que la memoria
    // sabe menos de lo que sabe.
    const [data, total] = await Promise.all([
      getGraph(currentNemo(), {
        label: state.label,
        depth: state.depth,
        max: state.max,
      }),
      getGraphStats(currentNemo()).catch(() => ({
        supported: false,
        entities: 0,
        relations: 0,
      })),
    ]);

    state.nodes = data.nodes;
    state.colors = assignColors(data.types.map((t) => t.type));

    renderLegend(data.types);
    renderOptions();
    renderInspector(null);
    // El lienzo conserva la disposición elegida, así que los datos nuevos
    // entran ya colocados como el usuario los dejó.
    lienzo.setData(data, state.colors);

    if (!data.nodes.length) {
      showEmpty(emptyReason(total));
      $('graph-hint').textContent = 'Sin entidades que mostrar';
    } else {
      showEmpty('');
      const dibujado = `${count(data.nodes.length)} entidades · ${count(data.edges.length)} relaciones`;
      $('graph-hint').textContent =
        total.supported && total.entities > data.nodes.length
          ? `${dibujado} — de ${count(total.entities)}${total.truncated ? '+' : ''} en la memoria`
          : dibujado;
    }
  } catch (error) {
    showEmpty(`${icon('triangle-alert', 22)}
      <p><strong>No se pudo leer el grafo.</strong></p>
      <p>${escape(error.message || String(error))}</p>`);
    $('graph-hint').textContent = 'Error';
  } finally {
    loading = false;
    boton.disabled = false;
  }
}

/* --- Búsqueda ------------------------------------------------------------- */

function search(text) {
  const needle = text.trim().toLowerCase();
  if (!needle) {
    lienzo.setMatches([]);
    $('graph-search-hint').textContent = '';
    return;
  }
  const hits = state.nodes.filter((n) => n.label.toLowerCase().includes(needle));
  lienzo.setMatches(hits.map((n) => n.id));
  $('graph-search-hint').textContent = hits.length
    ? `${count(hits.length)} coincidencia${hits.length === 1 ? '' : 's'}`
    : 'Nada con ese nombre';
  // Una sola coincidencia no deja dudas: se centra y se abre su ficha.
  if (hits.length === 1) lienzo.select(hits[0].id);
}

/* --- Montaje -------------------------------------------------------------- */

/** Registra los escuchadores de la tarjeta. Se llama una vez al arrancar. */
export function mountGrafo() {
  lienzo = createLienzo($('graph-canvas'), {
    onPick: renderInspector,
    // `is-idle` enciende la pista y devuelve el cursor a normal: el estado
    // del lienzo tiene que verse, no adivinarse.
    onActive: (activo) => $('graph-stage').classList.toggle('is-idle', !activo),
  });
  $('graph-stage').classList.add('is-idle');

  // El selector se llena desde el módulo de disposiciones: una segunda lista
  // escrita a mano en el marcado acabaría discrepando de la primera.
  $('graph-layout').innerHTML = LAYOUTS.map(
    (l) => `<option value="${escape(l.key)}">${escape(l.label)}</option>`
  ).join('');
  $('graph-layout').value = state.layout;

  // Cambiar de disposición NO vuelve a consultar: son los mismos nodos puestos
  // de otra manera, y pedir otra vez el grafo por recolocarlo sería gastar una
  // lectura cara en algo que ya está en memoria.
  $('graph-layout').addEventListener('change', (event) => {
    state.layout = event.target.value;
    lienzo.setLayout(state.layout);
  });

  $('graph-label').addEventListener('change', (event) => {
    state.label = event.target.value;
    load();
  });
  $('graph-depth').addEventListener('change', (event) => {
    state.depth = Number(event.target.value);
    load();
  });
  $('graph-max').addEventListener('change', (event) => {
    state.max = Number(event.target.value);
    load();
  });
  $('graph-search').addEventListener('input', (event) => search(event.target.value));
  $('graph-reload').addEventListener('click', () => load());
  $('graph-fit').addEventListener('click', () => lienzo.fit());
  $('graph-zoom-in').addEventListener('click', () => lienzo.zoomIn());
  $('graph-zoom-out').addEventListener('click', () => lienzo.zoomOut());
}

/**
 * Pinta el grafo de la memoria activa.
 *
 * Al cambiar de memoria se vuelve a «Todo el grafo»: una entidad de la memoria
 * anterior no tiene por qué existir en la nueva, y arrancar con una raíz que
 * no está daría un lienzo vacío sin explicación.
 */
export async function renderGrafo({ reset = false } = {}) {
  if (!lienzo) return;
  if (reset) {
    state.label = '*';
    $('graph-search').value = '';
    $('graph-search-hint').textContent = '';
  }
  await load();
}

/**
 * Marca lo dibujado como caducado, sin leer nada.
 *
 * Lo llama el vigilante cuando la memoria cambia y el Panel **no** está a la
 * vista: la lectura se aplaza hasta que alguien vuelva a mirar.
 */
export function invalidarGrafo() {
  obsoleto = true;
}

/**
 * Repinta el grafo **solo si** algo lo dejó caducado.
 *
 * Se llama al entrar en el Panel. Sin marca no hace nada, así que cambiar de
 * pestaña de un lado a otro no dispara lecturas.
 */
export async function refrescarGrafoSiHaceFalta() {
  if (!obsoleto) return;
  await renderGrafo();
}
