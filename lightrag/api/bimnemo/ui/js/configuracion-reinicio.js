/* ==========================================================================
   BIMNEMO — Aplicar la configuración: el reinicio del motor
   --------------------------------------------------------------------------
   Vive aparte de `configuracion.js` porque es otra cosa: aquel monta un
   formulario y lo guarda; esto **mata un proceso y espera a otro**. Mezclarlos
   dejaba el fichero por encima del tope de líneas y, peor, mezclaba una
   pantalla con una maniobra.

   Lo que hay aquí es la maniobra: el aviso con su botón, y la secuencia que
   pide el reinicio, tapa la ventana mientras dura y recarga cuando el motor
   que responde **ya es otro**.
   ========================================================================== */

import { getBootId, restartEngine, waitForEngine } from './api.js';
import { icon } from './icons.js';
import { escape } from './format.js';
import {
  abrirCortina,
  cerrarCortina,
  fallarCortina,
  faseCortina,
} from './reinicio.js';

/** Dónde escribir los avisos: lo pone `configuracion.js` al montarse. */
let setBanner = () => {};

/** Le dice a este módulo dónde pintar sus avisos. */
export function usarBanner(fn) {
  setBanner = fn;
}

/** El aviso de «hay que reiniciar», con su botón. */
export function restartBanner(message) {
  setBanner(`
    <div class="notice notice--warn">
      <span class="notice__icon">${icon('triangle-alert', 14)}</span>
      <span>
        ${escape(message)}
        <button type="button" class="btn btn--primary cfgbanner__btn" id="btn-restart">
          ${icon('refresh-cw', 13)} Reiniciar el motor
        </button>
      </span>
    </div>`);
  document.getElementById('btn-restart')?.addEventListener('click', doRestart);
}

/**
 * Pide el reinicio, tapa la ventana mientras dura y recarga al volver.
 *
 * @param {object}   [opciones]
 * @param {(html: string) => void} [opciones.avisar]  Dónde escribir un fallo
 *        que **no** es del motor —por ejemplo un 409 porque está indexando—.
 *        Por defecto, el banner de Configuración. Motor pasa el suyo: un
 *        aviso pintado en una vista que no se está mirando es un botón que
 *        parece no hacer nada.
 * @param {string}   [opciones.boton]  Id del botón que hay que volver a
 *        habilitar si la maniobra no llega a empezar.
 * @param {() => void} [opciones.antesDeRecargar]  Lo último que se hace antes
 *        de recargar, cuando el motor nuevo ya está en pie. Existe para quien
 *        necesita mantener algo hasta el final de la maniobra —la clave de
 *        acceso, sin ir más lejos: hasta que el motor no vuelve abierto, esta
 *        ventana sigue teniendo que presentarla.
 */
export async function doRestart({
  avisar = null,
  boton = 'btn-restart',
  antesDeRecargar = null,
} = {}) {
  const escribir = avisar || setBanner;
  const button = document.getElementById(boton);
  if (button) button.disabled = true;

  // Quién está respondiendo AHORA. Sin esta referencia no hay forma de
  // distinguir al motor nuevo del que se está muriendo, que sigue
  // contestando durante medio segundo largo.
  let antes = null;
  try {
    antes = await getBootId();
  } catch {
    // Sin referencia se espera igual, solo que a la primera respuesta.
  }

  abrirCortina();

  try {
    const result = await restartEngine();

    if (!result.supervised) {
      // Lanzado a mano, el motor no vuelve solo: no hay nada que esperar.
      fallarCortina(escape(result.message));
      return;
    }

    faseCortina('cerrando');
    const back = await waitForEngine(antes, { alCambiarFase: faseCortina });

    if (back) {
      faseCortina('listo');
      if (antesDeRecargar) antesDeRecargar();
      // Recargar es lo correcto: el motor es otro proceso y todas las vistas
      // están mostrando datos del anterior.
      window.location.reload();
    } else {
      fallarCortina(
        'Se pidió el reinicio y el motor no ha vuelto a responder a tiempo.',
      );
    }
  } catch (error) {
    cerrarCortina();
    const conflict = error.status === 409;
    escribir(`
      <div class="notice notice--${conflict ? 'warn' : 'error'}">
        <span class="notice__icon">${icon('triangle-alert', 14)}</span>
        <span>${
          conflict
            ? 'El motor está indexando ahora mismo. Espera a que termine y vuelve a reiniciar.'
            : `No se pudo reiniciar: ${escape(error.detail || error.message)}`
        }</span>
      </div>`);
    if (button) button.disabled = false;
  }
}
