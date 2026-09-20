/* ==========================================================================
   BIMNEMO — Acciones sobre un archivo
   --------------------------------------------------------------------------
   Lo que se puede hacer con una fila de la tabla: borrarla o reintentarla.

   Vive aparte de `archivos.js` porque es otra cosa: aquel **enseña** lo que
   hay, este **lo cambia**, y una de las dos acciones es irreversible.

   ## Qué acciones hay, y por qué no más

   - **Borrar** — siempre. Si el documento llegó a indexarse, se va con su
     índice, sus fragmentos y su parte del grafo; si solo estaba subido, se
     borra el fichero. Son dos endpoints distintos porque son dos cosas
     distintas: un fichero sin indexar no tiene identificador de documento.
   - **Reintentar** — solo en los fallidos. Es la acción que faltaba justo
     donde se ve el fallo.

   No hay «ver detalles» —la fila ya enseña todo lo que el servidor sabe— ni
   «descargar», que no existe en la API. Inventar un endpoint para completar
   una barra de botones es peor que dejarla corta.
   ========================================================================== */

import { deleteDocuments, deleteStoredFile, retryFailed } from './api.js';
import { despertar } from './archivos-progreso.js';
import { currentNemo } from './nemo.js';
import { icon } from './icons.js';
import { escape } from './format.js';

/** La fila que se va a borrar mientras el diálogo está abierto. */
let objetivo = null;

/**
 * Los archivos cuyo borrado está en marcha.
 *
 * El servidor responde en cuanto lanza el trabajo, no cuando termina: purgar
 * los fragmentos de un documento y rehacer el grafo lleva segundos. Sin esta
 * marca la fila se quedaría intacta fingiendo que no pasa nada, que es justo
 * lo que se sentía como «tarda en borrarse».
 *
 * Vive solo en el navegador: si se recarga la página, la fila vuelve a su
 * estado real y desaparece igual cuando el motor acaba.
 */
const borrandose = new Set();

/** ¿Está este archivo en mitad de un borrado? */
export function seEstaBorrando(nombre) {
  return borrandose.has(nombre);
}

/**
 * Olvida las marcas de los archivos que ya no están en la lista.
 *
 * Un borrado termina con la fila desapareciendo, así que la marca deja de
 * tener a quién describir. Sin esto, subir otro archivo con el mismo nombre lo
 * pintaría «Borrando…» nada más llegar.
 */
export function olvidarBorrados(nombresVivos) {
  const vivos = new Set(nombresVivos);
  for (const nombre of borrandose) {
    if (!vivos.has(nombre)) borrandose.delete(nombre);
  }
}

/** Qué hacer cuando algo cambia de verdad: lo pone `archivos.js`. */
let alCambiar = null;

const $ = (id) => document.getElementById(id);

/* --- Botones de la fila --------------------------------------------------- */

/**
 * Los botones de una fila, según en qué estado esté.
 *
 * Devuelve marcado, no elementos: la tabla se pinta de una vez con
 * `innerHTML` y un escuchador delegado, en lugar de colgar uno por botón.
 */
export function rowActions(row) {
  // Pedir dos veces el mismo borrado no rompe nada —el servidor responde
  // «ocupado»— pero enseñar un botón que solo puede dar esa respuesta es
  // ofrecer algo que no existe.
  const borrando = seEstaBorrando(row.name);

  const reintentar =
    row.status === 'failed' && !borrando
      ? `<button type="button" class="btn btn--ghost btn--icon" data-accion="reintentar"
                 title="Volver a intentar el indexado" aria-label="Reintentar">
           ${icon('refresh-cw', 13)}
         </button>`
      : '';

  return `
    <td class="table__acciones">
      <span class="acciones">
        ${reintentar}
        <button type="button" class="btn btn--ghost btn--icon acciones__borrar"
                data-accion="borrar"
                data-doc="${escape(row.doc_id || '')}"
                data-nombre="${escape(row.name)}"
                ${borrando ? 'disabled' : ''}
                title="${borrando ? 'Borrándose…' : 'Borrar este archivo'}" aria-label="Borrar">
          ${icon('trash-2', 13)}
        </button>
      </span>
    </td>`;
}

/* --- Diálogo de borrado --------------------------------------------------- */

function abrirBorrado(nombre, docId) {
  objetivo = { nombre, docId };
  $('file-delete-title').textContent = `Borrar «${nombre}»`;
  $('file-delete-error').textContent = '';

  // Lo que se pierde no es lo mismo en los dos casos, y decirlo importa: un
  // documento indexado se lleva por delante lo que el motor aprendió de él.
  $('file-delete-warning').innerHTML = docId
    ? `<span class="notice__icon">${icon('triangle-alert', 14)}</span>
       <span>Se borrarán <strong>el archivo y lo que el motor aprendió de
       él</strong>: sus fragmentos y sus entidades en el grafo. No se puede
       deshacer.</span>`
    : `<span class="notice__icon">${icon('triangle-alert', 14)}</span>
       <span>Se borrará <strong>el archivo</strong>. Todavía no estaba
       indexado, así que no afecta al grafo. No pasa por la papelera.</span>`;

  $('file-delete-dialog').showModal();
}

async function confirmarBorrado(event) {
  event.preventDefault();
  if (!objetivo) return;

  const boton = $('file-delete-confirm');
  boton.disabled = true;
  boton.textContent = 'Borrando…';

  try {
    const resultado = objetivo.docId
      ? await deleteDocuments(currentNemo(), [objetivo.docId])
      : await deleteStoredFile(currentNemo(), objetivo.nombre);

    if (resultado?.status === 'busy') {
      // Ocupado no es un fallo: es «ahora no». Se dice y se deja reintentar.
      $('file-delete-error').textContent = resultado.message;
      boton.disabled = false;
      return;
    }

    $('file-delete-dialog').close();
    // El servidor ya lanzó el trabajo; la fila lo dice mientras dura.
    if (resultado?.status === 'deleting') borrandose.add(objetivo.nombre);
    if (alCambiar) await alCambiar();
    // Y se mira enseguida, en vez de esperar a la cadencia en reposo.
    despertar();
  } catch (error) {
    $('file-delete-error').textContent =
      `No se pudo borrar: ${error.detail || error.message}`;
    boton.disabled = false;
  } finally {
    boton.textContent = 'Borrar';
  }
}

/* --- Reintento ------------------------------------------------------------ */

async function reintentar(boton) {
  boton.disabled = true;
  try {
    await retryFailed(currentNemo());
    if (alCambiar) await alCambiar();
    despertar();
  } catch (error) {
    console.error('[BIMNEMO] no se pudo reintentar:', error);
  } finally {
    boton.disabled = false;
  }
}

/* --- Montaje -------------------------------------------------------------- */

/**
 * Registra el escuchador de la tabla y el del diálogo.
 *
 * Un solo escuchador delegado en el cuerpo de la tabla, no uno por botón: la
 * tabla se repinta entera en cada refresco y los botones de antes dejarían de
 * existir con sus escuchadores dentro.
 */
export function mountAcciones(onChanged) {
  alCambiar = onChanged;

  document.getElementById('files-body').addEventListener('click', (event) => {
    const boton = event.target.closest('[data-accion]');
    if (!boton) return;
    if (boton.dataset.accion === 'borrar') {
      abrirBorrado(boton.dataset.nombre, boton.dataset.doc || '');
    } else if (boton.dataset.accion === 'reintentar') {
      reintentar(boton);
    }
  });

  $('file-delete-form').addEventListener('submit', confirmarBorrado);
  $('file-delete-cancel').addEventListener('click', () =>
    $('file-delete-dialog').close()
  );
  $('file-delete-dialog').addEventListener('close', () => {
    objetivo = null;
    $('file-delete-error').textContent = '';
    $('file-delete-confirm').disabled = false;
  });
}
