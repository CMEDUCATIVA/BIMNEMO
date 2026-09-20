/* ==========================================================================
   BIMNEMO — Encender y apagar la clave de acceso
   --------------------------------------------------------------------------
   Vive aparte de `apiview.js` porque es otra cosa: aquél enseña cómo usar la
   API, y esto **escribe el `.env` y reinicia el motor**.

   ## Por qué esto no puede ser un interruptor sin más

   La clave no la decide el navegador: la decide el servidor. El guardia de
   las rutas solo existe si `LIGHTRAG_API_KEY` está en el entorno, y eso se lee
   **al arrancar**. Así que «activar» significa de verdad: escribir la clave en
   el fichero y levantar el motor de nuevo.

   ## El orden no es negociable

   Si se escribe la clave y se reinicia sin que **esta ventana** la tenga
   guardada, el usuario se queda **fuera de su propia aplicación**: la interfaz
   se sigue sirviendo —es estática— pero todas sus peticiones darían 401. Se
   saldría editando el `.env` a mano.

   Por eso: **primero el navegador, después el fichero, y al final el
   reinicio.** Si algo falla por el camino, se deshace lo que se hizo.
   ========================================================================== */

import { getApiKey, setAccess, setApiKey } from './api.js';
import { doRestart } from './configuracion-reinicio.js';
import { icon } from './icons.js';
import { escape } from './format.js';

/** Longitud de la clave generada. 32 caracteres del alfabeto de abajo. */
const LARGO = 32;

/**
 * Alfabeto sin caracteres que se confunden al leerlos en voz alta o al
 * copiarlos a mano: nada de `0/O`, `1/l/I`. Una clave que se teclea mal es una
 * clave que parece rota.
 */
const ALFABETO = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789';

/** Una clave nueva, del generador criptográfico del navegador. */
export function generarClave() {
  const bytes = new Uint8Array(LARGO);
  window.crypto.getRandomValues(bytes);
  return [...bytes].map((b) => ALFABETO[b % ALFABETO.length]).join('');
}

/** Dónde escribir los avisos de esta ficha: lo pone `apiview.js`. */
let avisar = () => {};

export function usarAviso(fn) {
  avisar = fn;
}

function decir(tipo, html) {
  avisar(`
    <div class="notice notice--${tipo}">
      <span class="notice__icon">${icon(
        tipo === 'error' ? 'triangle-alert' : 'info',
        14,
      )}</span>
      <span>${html}</span>
    </div>`);
}

/* --- Encender ------------------------------------------------------------- */

/**
 * Pasa a exigir clave.
 *
 * @param {string} clave  La que se va a exigir. Ya validada por quien llama.
 */
export async function protegerApi(clave) {
  const anterior = getApiKey();

  // 1. El navegador primero. Si el reinicio ocurre y esta ventana no la tiene,
  //    se queda fuera de la aplicación.
  setApiKey(clave);

  // 2. El fichero.
  try {
    await setAccess(true, clave);
  } catch (error) {
    // No se llegó a escribir: se devuelve el navegador a como estaba, porque
    // mandar una clave que el servidor no conoce rompería las peticiones.
    setApiKey(anterior);
    decir('error', `No se pudo guardar la clave: ${escape(error.detail || error.message)}`);
    return false;
  }

  // 3. El reinicio, con la cortina de siempre.
  await doRestart({ avisar, boton: 'btn-acceso' });
  return true;
}

/* --- Apagar --------------------------------------------------------------- */

/**
 * Deja la API abierta.
 *
 * Aquí el orden se invierte, y hay un detalle que cuesta ver: **el motor sigue
 * pidiendo la clave hasta que reinicia**. Quitarla del `.env` no desprotege
 * nada todavía. Así que esta ventana tiene que seguir presentándola —también
 * al pedir el propio reinicio, que es una ruta protegida como las demás—.
 *
 * Borrarla antes de tiempo deja el reinicio rechazado con un 403, el motor en
 * pie con la clave vieja, y el fichero ya sin ella: nadie puede volver a
 * reiniciarlo, porque la clave que haría falta se acaba de borrar. Se sale
 * cerrando el proceso del motor, que el supervisor levanta de nuevo.
 *
 * Por eso se borra **en el último instante**, con el motor nuevo ya en pie.
 */
export async function abrirApi() {
  try {
    await setAccess(false, null);
  } catch (error) {
    decir('error', `No se pudo retirar la clave: ${escape(error.detail || error.message)}`);
    return false;
  }
  await doRestart({
    avisar,
    boton: 'btn-acceso',
    antesDeRecargar: () => setApiKey(''),
  });
  return true;
}
