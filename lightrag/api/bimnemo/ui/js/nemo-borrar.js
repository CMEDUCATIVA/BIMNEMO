/* ==========================================================================
   BIMNEMO — Borrar una memoria
   --------------------------------------------------------------------------
   Vive aparte del resto de `nemo.js` porque es la única operación
   irreversible de la aplicación y tiene su propio resguardo.

   **Por qué un diálogo propio y no el del navegador.** Antes se usaban
   `window.prompt` y `window.alert`: el cuadro nativo de Chrome no se puede
   ajustar, no admite formato, no distingue lo grave de lo rutinario y se ve
   como una alerta del sistema encima de la aplicación, no como parte de ella.
   En una acción que borra archivos del disco, la forma importa.

   Lo que **no** cambia es el resguardo: se sigue exigiendo escribir el nombre
   exacto. Un «¿seguro?» se contesta que sí sin leerlo.
   ========================================================================== */

import { deleteNemo } from './api.js';
import { icon } from './icons.js';
import { escape } from './format.js';

/** Qué memoria se está borrando mientras el diálogo está abierto. */
let objetivo = null;

/** Se inyectan desde nemo.js: recargar la lista y saltar a la de por defecto. */
let despues = null;

const $ = (id) => document.getElementById(id);

/* --- Apertura ------------------------------------------------------------- */

/**
 * Abre el diálogo para la memoria indicada.
 *
 * Una memoria protegida no se puede borrar, y eso se dice en el mismo sitio
 * donde se iba a borrar: mandarlo a otra ventana obligaría al usuario a
 * cerrar dos cosas para enterarse de una.
 */
export function abrirBorrado(nemo, alTerminar) {
  if (!nemo) return;
  objetivo = nemo;
  despues = alTerminar;

  const protegida = Boolean(nemo.protected);
  $('nemo-delete-title').textContent = protegida
    ? 'Esta memoria no se puede borrar'
    : `Borrar «${nemo.name}»`;

  $('nemo-delete-warning').innerHTML = protegida
    ? `<span class="notice__icon">${icon('info', 14)}</span>
       <span>«${escape(nemo.name)}» es la memoria base: es donde vive todo lo
       que se indexó antes de que existieran las demás. Puedes vaciarla, pero
       no quitarla.</span>`
    : `<span class="notice__icon">${icon('triangle-alert', 14)}</span>
       <span>Se borrarán <strong>sus archivos, su índice y su grafo</strong>.
       No se puede deshacer y no pasa por la papelera.</span>`;

  // En una memoria protegida no hay nada que confirmar: sobra el campo y
  // sobra el botón de borrar.
  $('nemo-delete-field').hidden = protegida;
  $('nemo-delete-confirm').hidden = protegida;
  $('nemo-delete-cancel').textContent = protegida ? 'Entendido' : 'Cancelar';

  $('nemo-delete-name').value = '';
  $('nemo-delete-error').textContent = '';
  $('nemo-delete-confirm').disabled = true;

  $('nemo-delete-dialog').showModal();
  if (!protegida) $('nemo-delete-name').focus();
}

/* --- Confirmación --------------------------------------------------------- */

/**
 * El botón solo se enciende cuando lo escrito coincide.
 *
 * Es mejor que dejarlo pulsable y reprochar después: el estado del botón dice
 * en todo momento si lo escrito vale, sin tener que intentarlo.
 */
function comprobarNombre() {
  const escrito = $('nemo-delete-name').value.trim();
  $('nemo-delete-confirm').disabled = !objetivo || escrito !== objetivo.name;
  $('nemo-delete-error').textContent = '';
}

async function confirmar(event) {
  event.preventDefault();
  if (!objetivo) return;

  const escrito = $('nemo-delete-name').value.trim();
  if (escrito !== objetivo.name) {
    $('nemo-delete-error').textContent = 'El nombre no coincide.';
    return;
  }

  const boton = $('nemo-delete-confirm');
  boton.disabled = true;
  boton.textContent = 'Borrando…';

  try {
    await deleteNemo(objetivo.id, objetivo.name, true);
    $('nemo-delete-dialog').close();
    if (despues) await despues();
  } catch (error) {
    // El fallo se queda EN el diálogo: cerrarlo y avisar en otro sitio
    // dejaría al usuario sin saber si la memoria sigue ahí.
    $('nemo-delete-error').textContent =
      `No se pudo borrar: ${error.detail || error.message}`;
    boton.disabled = false;
  } finally {
    boton.textContent = 'Borrar definitivamente';
    if (!$('nemo-delete-dialog').open) objetivo = null;
  }
}

/* --- Montaje -------------------------------------------------------------- */

/** Registra los escuchadores del diálogo. Se llama una vez al arrancar. */
export function mountBorrado() {
  $('nemo-delete-name').addEventListener('input', comprobarNombre);
  $('nemo-delete-form').addEventListener('submit', confirmar);
  $('nemo-delete-cancel').addEventListener('click', () =>
    $('nemo-delete-dialog').close()
  );
  // Cerrar con Escape o con el botón deja el diálogo listo para la próxima.
  $('nemo-delete-dialog').addEventListener('close', () => {
    objetivo = null;
    $('nemo-delete-name').value = '';
    $('nemo-delete-error').textContent = '';
  });
}
