/* ==========================================================================
   BIMNEMO — NEMOs: memorias separadas
   --------------------------------------------------------------------------
   Mantiene cuál es la memoria activa, pinta su selector y su botón «+», y
   avisa a las vistas cuando cambia.

   La memoria activa se recuerda en `localStorage`, pero **nunca se confía en
   ella a ciegas**: si la NEMO guardada ya no existe —la borró otro, o es otro
   equipo— se vuelve a la de por defecto. Insistir en una memoria fantasma
   dejaría la aplicación mostrando errores en todas las vistas.
   ========================================================================== */

import { createNemo, listNemos } from './api.js';
import { abrirBorrado, mountBorrado } from './nemo-borrar.js';
import { icon } from './icons.js';
import { bytes, escape } from './format.js';

const STORAGE_KEY = 'bimnemo.nemo';

let state = { nemos: [], default: '', current: '' };
const listeners = new Set();

/* --- Estado --------------------------------------------------------------- */

export function currentNemo() {
  return state.current;
}

export function currentNemoName() {
  const nemo = state.nemos.find((n) => n.id === state.current);
  return nemo ? nemo.name : '—';
}

export function allNemos() {
  return state.nemos;
}

/** Se suscribe a los cambios de memoria activa. Devuelve cómo darse de baja. */
export function onNemoChange(callback) {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

function announce() {
  for (const callback of listeners) {
    try {
      callback(state.current);
    } catch (error) {
      // Un suscriptor roto no puede impedir que los demás se enteren: se
      // quedarían pintando datos de la memoria anterior.
      console.error('[BIMNEMO] suscriptor de NEMO falló:', error);
    }
  }
}

function remember(nemoId) {
  try {
    window.localStorage.setItem(STORAGE_KEY, nemoId);
  } catch {
    // Sin almacenamiento se sigue: solo se pierde la memoria entre sesiones.
  }
}

function recall() {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/* --- Carga ---------------------------------------------------------------- */

export async function loadNemos() {
  const payload = await listNemos();
  state.nemos = payload.nemos;
  state.default = payload.default;

  const guardada = recall();
  const existe = (id) => payload.nemos.some((n) => n.id === id);

  // El orden importa: lo recordado solo vale si sigue existiendo.
  if (guardada !== null && existe(guardada)) state.current = guardada;
  else if (existe(state.current)) {
    /* se conserva la actual */
  } else state.current = payload.default;

  renderSelector();
  return state;
}

export async function selectNemo(nemoId) {
  if (nemoId === state.current) return;
  state.current = nemoId;
  remember(nemoId);
  renderSelector();
  announce();
}

/* --- Selector ------------------------------------------------------------- */

export function renderSelector() {
  const host = document.getElementById('nemo-selector');
  if (!host) return;

  host.innerHTML = state.nemos
    .map(
      (n) =>
        `<option value="${escape(n.id)}"${n.id === state.current ? ' selected' : ''}>` +
        `${escape(n.name)}${n.id === state.default ? ' ·' : ''}</option>`
    )
    .join('');
}

/* --- Crear ---------------------------------------------------------------- */

function dialogo() {
  return document.getElementById('nemo-dialog');
}

function abrirCrear() {
  const dlg = dialogo();
  const input = document.getElementById('nemo-new-name');
  const error = document.getElementById('nemo-dialog-error');
  input.value = '';
  error.textContent = '';
  dlg.showModal();
  input.focus();
}

async function confirmarCrear(event) {
  event.preventDefault();
  const input = document.getElementById('nemo-new-name');
  const error = document.getElementById('nemo-dialog-error');
  const boton = document.getElementById('nemo-dialog-create');

  const nombre = input.value.trim();
  if (!nombre) {
    error.textContent = 'Escribe un nombre para la memoria.';
    return;
  }

  boton.disabled = true;
  try {
    const nemo = await createNemo(nombre);
    dialogo().close();
    await loadNemos();
    await selectNemo(nemo.id);
  } catch (err) {
    // 409 es el caso habitual —nombre repetido— y el servidor ya manda un
    // texto que explica cuál es el choque. Se enseña tal cual.
    error.textContent = err.detail || err.message;
  } finally {
    boton.disabled = false;
  }
}

/* --- Borrar --------------------------------------------------------------- */

/**
 * Abre el diálogo de borrado para la memoria activa.
 *
 * El diálogo y su resguardo viven en `nemo-borrar.js`; aquí solo se le dice a
 * quién apunta y qué hacer cuando termine.
 */
function borrarActual() {
  const nemo = state.nemos.find((n) => n.id === state.current);
  if (!nemo) return;
  abrirBorrado(nemo, async () => {
    await loadNemos();
    await selectNemo(state.default);
  });
}

/* --- Tarjeta del panel ---------------------------------------------------- */

/**
 * Pinta el desglose por memoria del panel.
 *
 * Una NEMO dormida no dice cuántos documentos tiene: el servidor no la abre
 * solo para contarlos, porque abrir seis memorias para pintar un panel serían
 * seis grafos en RAM. Se enseña «—», que es la verdad, en lugar de un cero
 * que parecería «está vacía».
 */
export function renderNemoBreakdown(detalle, total, onPick) {
  const host = document.getElementById('panel-nemos');
  if (!host) return;

  host.innerHTML = detalle
    .map((n) => {
      const porcentaje = total > 0 ? (n.size_bytes / total) * 100 : 0;
      const activa = n.id === state.current;
      return `
      <button type="button" class="nemorow${activa ? ' is-current' : ''}"
              data-nemo="${escape(n.id)}" title="Cambiar a ${escape(n.name)}">
        <span class="nemorow__dot" data-state="${n.live ? 'ok' : 'idle'}"
              title="${n.live ? 'Abierta' : 'En reposo'}"></span>
        <span class="nemorow__name truncate">${escape(n.name)}</span>
        <span class="nemorow__bar">
          <span class="nemorow__fill" style="width:${porcentaje}%"></span>
        </span>
        <span class="nemorow__num tabular">${escape(String(n.files))}</span>
        <span class="nemorow__size tabular">${escape(bytes(n.size_bytes))}</span>
        <span class="nemorow__docs tabular">${
          n.documents === null || n.documents === undefined
            ? '—'
            : escape(String(n.documents))
        }</span>
      </button>`;
    })
    .join('');

  host.onclick = (event) => {
    const fila = event.target.closest('[data-nemo]');
    if (fila) onPick(fila.dataset.nemo);
  };
}

/* --- Montaje -------------------------------------------------------------- */

export function mountNemo() {
  document.getElementById('nemo-selector').addEventListener('change', (event) => {
    selectNemo(event.target.value);
  });
  document.getElementById('btn-nemo-new').addEventListener('click', abrirCrear);
  document.getElementById('btn-nemo-delete').addEventListener('click', borrarActual);
  mountBorrado();
  document.getElementById('nemo-dialog-form').addEventListener('submit', confirmarCrear);
  document
    .getElementById('nemo-dialog-cancel')
    .addEventListener('click', () => dialogo().close());

  document.getElementById('btn-nemo-new').innerHTML = icon('plus', 15);
}
