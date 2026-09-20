/* ==========================================================================
   BIMNEMO — Preguntar y avisar
   --------------------------------------------------------------------------
   Sustituye a `window.confirm` y `window.alert`.

   Los cuadros nativos del navegador no se pueden ajustar, no admiten formato,
   no distinguen lo grave de lo rutinario y se ven como una alerta del sistema
   **encima** de la aplicación, no como parte de ella. Además bloquean el hilo:
   mientras están abiertos, la ventana no pinta nada.

   Aquí hay un único diálogo reutilizable que devuelve una promesa, así que
   quien pregunta puede `await` la respuesta y seguir leyéndose de arriba
   abajo, igual que con `confirm`.
   ========================================================================== */

import { icon } from './icons.js';
import { escape } from './format.js';

/** Cómo se resuelve la promesa en curso. Solo hay un diálogo a la vez. */
let resolver = null;

const $ = (id) => document.getElementById(id);

function cerrar(respuesta) {
  const dlg = $('ask-dialog');
  if (dlg.open) dlg.close();
  if (resolver) {
    const fn = resolver;
    resolver = null;
    fn(respuesta);
  }
}

/**
 * Pregunta algo y espera la respuesta.
 *
 * @param {object} opciones
 * @param {string} opciones.titulo
 * @param {string} opciones.mensaje
 * @param {string} [opciones.aceptar]   Texto del botón que confirma.
 * @param {string} [opciones.cancelar]  Texto del que no. `null` lo oculta:
 *        entonces el diálogo es un aviso, no una pregunta.
 * @param {boolean} [opciones.peligro]  Pinta el filo rojo y el botón rojo.
 * @returns {Promise<boolean>}
 */
export function preguntar({
  titulo,
  mensaje,
  aceptar = 'Aceptar',
  cancelar = 'Cancelar',
  peligro = false,
}) {
  const dlg = $('ask-dialog');
  dlg.classList.toggle('dialog--peligro', Boolean(peligro));

  $('ask-title').textContent = titulo;
  $('ask-mark').innerHTML = icon(peligro ? 'triangle-alert' : 'info', 15);
  $('ask-text').innerHTML = escape(mensaje);

  const btnOk = $('ask-ok');
  const btnNo = $('ask-cancel');
  btnOk.textContent = aceptar;
  btnOk.className = peligro ? 'btn btn--peligro' : 'btn btn--primary';
  btnNo.textContent = cancelar || '';
  btnNo.hidden = cancelar === null;

  // Si ya había una pregunta abierta, se responde que no antes de sustituirla:
  // dejar una promesa sin resolver cuelga a quien la esperaba.
  if (resolver) cerrar(false);

  return new Promise((resolve) => {
    resolver = resolve;
    dlg.showModal();
    // El foco va al botón que NO destruye nada: pulsar Intro por inercia no
    // puede ser lo que confirme un borrado.
    (peligro && cancelar !== null ? btnNo : btnOk).focus();
  });
}

/** Un aviso sin pregunta: solo «Entendido». */
export function avisar(titulo, mensaje, peligro = false) {
  return preguntar({
    titulo,
    mensaje,
    aceptar: 'Entendido',
    cancelar: null,
    peligro,
  });
}

/** Registra los escuchadores del diálogo. Una vez, al arrancar. */
export function mountDialogo() {
  $('ask-ok').addEventListener('click', () => cerrar(true));
  $('ask-cancel').addEventListener('click', () => cerrar(false));
  // Escape cierra el `<dialog>` por su cuenta; hay que resolver igualmente o
  // quien esperaba se queda colgado para siempre.
  $('ask-dialog').addEventListener('close', () => cerrar(false));
}
