/* ==========================================================================
   BIMNEMO — El botón de actualizar, en el encabezado
   --------------------------------------------------------------------------
   Contesta una pregunta que la aplicación no sabía contestar: **¿estoy al
   día?**. Hasta ahora, enterarse de que había una versión nueva dependía de
   que a alguien se le ocurriera mirar el repositorio.

   ## Va al lado del estado del motor, no en su lugar

   El punto de «Motor activo» es la única señal de que la aplicación respira.
   Cambiarlo por uno de versiones dejaría al usuario sin saber si está viva.

   Son dos preguntas distintas y merecen dos sitios: el punto contesta
   «¿funciona?»; esto contesta «¿está al día?».

   ## Por qué parpadea, y por qué está bien que parpadee

   Lo pidió el usuario, y es correcto **solo porque es raro**: una versión
   nueva no aparece cada hora. Un elemento que parpadea siempre deja de verse
   a los dos días. Con `prefers-reduced-motion` no parpadea: se resalta.
   ========================================================================== */

import {
  applyUpdate,
  getBootId,
  getUpdateStatus,
  waitForEngine,
} from './api.js';
import { preguntar } from './dialogo.js';
import {
  abrirCortina,
  cerrarCortina,
  fallarCortina,
  faseCortina,
} from './reinicio.js';
import { icon } from './icons.js';

/**
 * Cada media hora.
 *
 * GitHub permite 60 consultas por hora sin credenciales y el servidor cachea
 * la respuesta cinco minutos, así que esto no se acerca al límite ni con
 * varias ventanas abiertas. Preguntar más a menudo no descubriría nada: una
 * versión no aparece cada minuto.
 */
const CADA = 30 * 60 * 1000;

let estado = null;
let temporizador = null;

const caja = () => document.getElementById('update-button');

/* --- Pintado -------------------------------------------------------------- */

function pintar() {
  const boton = caja();
  if (!boton) return;

  // Sin git detrás no hay nada que actualizar, y un botón que no puede hacer
  // su trabajo es peor que no tenerlo.
  if (estado && estado.supported === false) {
    boton.hidden = true;
    return;
  }
  boton.hidden = false;

  const cargando = estado === null;
  const sinRed = estado && estado.reachable === false;
  const atrasado = estado && estado.behind;

  boton.dataset.estado = cargando
    ? 'buscando'
    : sinRed
      ? 'sin-red'
      : atrasado
        ? 'hay'
        : 'al-dia';

  const rotulo = cargando
    ? 'Buscando…'
    : sinRed
      ? 'Sin conexión'
      : atrasado
        ? 'Actualizar'
        : 'Actualizado';

  boton.innerHTML = `
    <span class="actualizar__icon">${icon(
      cargando
        ? 'loader-circle'
        : sinRed
          ? 'triangle-alert'
          : atrasado
            ? 'refresh-cw'
            : 'check',
      13,
    )}</span>
    <span>${rotulo}</span>`;

  boton.title = cargando
    ? 'Preguntando a GitHub si hay una versión nueva…'
    : sinRed
      ? 'No se pudo consultar GitHub. Se reintenta solo; no afecta a nada más.'
      : atrasado
        ? `Hay una versión nueva: ${estado.message || 'pulsa para traerla'}`
        : 'Tienes la última versión publicada.';

  // Con la API al día no hay nada que pulsar, pero el botón sigue siendo útil
  // como indicador: se deja activo para poder forzar una comprobación.
  boton.disabled = cargando;
}

/* --- Consulta ------------------------------------------------------------- */

async function mirar(forzar = false) {
  try {
    estado = await getUpdateStatus(forzar);
  } catch {
    // El motor puede estar reiniciándose. No es momento de decir nada.
    estado = { supported: true, reachable: false };
  }
  pintar();
}

/* --- La maniobra ---------------------------------------------------------- */

async function actualizar() {
  // Con la versión al día, pulsar vuelve a preguntar: es lo que espera quien
  // acaba de publicar algo y quiere verlo ya.
  if (!estado || !estado.behind) {
    estado = null;
    pintar();
    await mirar(true);
    return;
  }

  let descartar = false;
  if (estado.dirty) {
    // `git reset --hard` borra los cambios locales. Se pregunta antes, con el
    // diálogo de la aplicación, no con el del navegador.
    descartar = await preguntar({
      titulo: 'Hay cambios locales en el código',
      mensaje:
        'Alguien ha modificado ficheros del programa en este ordenador. ' +
        'Actualizar los descarta y no se pueden recuperar. Tus documentos y ' +
        'tus memorias no se tocan.',
      aceptar: 'Descartar y actualizar',
      cancelar: 'Cancelar',
      peligro: true,
    });
    if (!descartar) return;
  }

  const antes = await getBootId().catch(() => null);
  abrirCortina();
  faseCortina('cerrando');

  try {
    const resultado = await applyUpdate(descartar);
    if (resultado.status === 'up_to_date') {
      cerrarCortina();
      await mirar(true);
      return;
    }
  } catch (error) {
    cerrarCortina();
    const ocupado = error.status === 409;
    await preguntar({
      titulo: ocupado ? 'Ahora no se puede' : 'No se pudo actualizar',
      mensaje:
        error.detail ||
        error.message ||
        'GitHub no respondió. Inténtalo dentro de un rato.',
      aceptar: 'Entendido',
      cancelar: 'Cerrar',
    });
    return;
  }

  // A partir de aquí es el mismo camino que el reinicio: esperar a que el
  // motor sea OTRO proceso, no a que algo conteste.
  const vuelto = await waitForEngine(antes, { alCambiarFase: faseCortina });
  if (vuelto) {
    faseCortina('listo');
    window.location.reload();
  } else {
    fallarCortina(
      'Se descargó la versión nueva y el motor no ha vuelto a tiempo. ' +
        'Puede que faltara instalar una dependencia.',
    );
  }
}

/* --- Montaje -------------------------------------------------------------- */

/** Monta el botón y empieza a vigilar si hay versión nueva. */
export function mountActualizar() {
  const boton = caja();
  if (!boton) return;
  boton.addEventListener('click', actualizar);
  pintar();
  mirar();
  if (temporizador) window.clearInterval(temporizador);
  temporizador = window.setInterval(() => mirar(), CADA);
}
