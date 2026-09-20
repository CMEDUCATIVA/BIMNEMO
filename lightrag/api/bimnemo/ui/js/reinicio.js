/* ==========================================================================
   BIMNEMO — La cortina del reinicio
   --------------------------------------------------------------------------
   Reiniciar el motor tarda entre cinco y ocho segundos, y durante ese rato
   **no hay motor detrás**. Antes se decía con un aviso de una línea dentro de
   Configuración mientras el resto de la ventana seguía pareciendo usable: una
   invitación a pulsar botones que iban a fallar.

   Así que ocupa la pantalla entera. No por dramatismo: porque es la verdad de
   lo que está pasando.

   ## Las fases son reales

   La barra no es un temporizador disfrazado. Cada fase se deduce de algo que
   se puede comprobar:

   | Fase          | Cómo se sabe                                      |
   |---------------|---------------------------------------------------|
   | `pidiendo`    | La petición está en vuelo                         |
   | `cerrando`    | El servidor aceptó, pero todavía responde         |
   | `arrancando`  | Ya **no** responde: el proceso murió              |
   | `comprobando` | Responde otra vez; falta ver si es otro `boot_id` |

   Dentro de una fase la barra **se acerca al siguiente hito sin llegar**. Se
   mueve —hay algo vivo— pero no promete un porcentaje que nadie está midiendo.
   El número que sí es cierto, los segundos transcurridos, va al lado.
   ========================================================================== */

import { icon } from './icons.js';

/** Hasta dónde llega la barra en cada fase. */
const HITOS = {
  pidiendo: 10,
  cerrando: 30,
  arrancando: 65,
  comprobando: 90,
  listo: 100,
};

const TITULOS = {
  pidiendo: 'Pidiendo el reinicio',
  cerrando: 'Cerrando el motor',
  arrancando: 'Arrancando el motor',
  comprobando: 'Comprobando que ya responde',
  listo: 'Listo',
};

const DETALLES = {
  pidiendo: 'Avisando al motor de que tiene que reiniciarse.',
  cerrando: 'Guardando los almacenes y cerrando el proceso actual.',
  arrancando: 'El proceso anterior ya terminó. Levantando el nuevo.',
  comprobando: 'El motor responde. Comprobando que es el proceso nuevo.',
  listo: 'Recargando la ventana con el motor nuevo.',
};

/** Lo que suele tardar, para que los segundos tengan con qué compararse. */
const HABITUAL = 8;

let caja = null;
let reloj = null;
let inicio = 0;
let fase = 'pidiendo';
let avance = 0;

const $ = () => document.getElementById('restart-curtain');

/* --- Pintado -------------------------------------------------------------- */

function pintar(extra = '') {
  if (!caja) return;
  const segundos = Math.round((Date.now() - inicio) / 1000);

  caja.innerHTML = `
    <div class="cortina__panel" role="status" aria-live="polite">
      <span class="cortina__icon">${icon('refresh-cw', 26)}</span>
      <h2 class="cortina__title">${TITULOS[fase]}</h2>
      <p class="cortina__detail">${DETALLES[fase]}</p>

      <div class="cortina__track">
        <span class="cortina__fill" style="width:${avance.toFixed(1)}%"></span>
      </div>

      <p class="cortina__meta">
        <span class="tabular">${segundos}s</span>
        <span class="cortina__sep">·</span>
        <span>suele tardar unos ${HABITUAL}s</span>
      </p>
      ${extra}
    </div>`;
}

/**
 * Acerca la barra al hito de la fase sin alcanzarlo.
 *
 * Que se mueva importa —una barra quieta parece un cuelgue— pero llegar al
 * hito sería anunciar un paso que todavía no ha ocurrido. Se recorre un
 * quinto de lo que falta en cada tic: rápido al principio, casi parada al
 * final, que es justo la forma de una espera de la que no se sabe el largo.
 */
function acercar() {
  const techo = HITOS[fase] ?? 0;
  avance += (techo - avance) / 5;
  pintar();
}

/* --- Vida de la cortina --------------------------------------------------- */

/** Abre la cortina y empieza a contar. */
export function abrirCortina() {
  caja = $();
  if (!caja) return;
  inicio = Date.now();
  fase = 'pidiendo';
  avance = 0;
  // Un reinicio anterior que falló dejó la cortina teñida de ámbar; abrir en
  // ese estado diría «fallo» antes de que pase nada.
  caja.classList.remove('cortina--fallo');
  caja.hidden = false;
  document.body.classList.add('con-cortina');
  pintar();
  reloj = window.setInterval(acercar, 400);
}

/** Cambia de fase. Lo llama la espera cuando averigua algo nuevo. */
export function faseCortina(nueva) {
  if (!caja || !(nueva in HITOS)) return;
  fase = nueva;
  // «Listo» es el único hito que sí se alcanza: ya no se está esperando nada,
  // así que dejar la barra a media asta sería raro justo en el buen final.
  if (nueva === 'listo') avance = 100;
  pintar();
}

/** Cierra la cortina y deja la ventana como estaba. */
export function cerrarCortina() {
  if (reloj) window.clearInterval(reloj);
  reloj = null;
  if (caja) {
    caja.hidden = true;
    caja.innerHTML = '';
    caja.classList.remove('cortina--fallo');
  }
  document.body.classList.remove('con-cortina');
  caja = null;
}

/**
 * El motor no volvió.
 *
 * Seguir animando la barra sería mentir, así que la cortina se queda quieta y
 * dice qué hacer. El mensaje es el mismo que ya daba el aviso antiguo: abrir
 * con consola es la única forma de ver por qué no arrancó.
 */
export function fallarCortina(mensaje) {
  if (reloj) window.clearInterval(reloj);
  reloj = null;
  if (!caja) return;
  fase = 'arrancando';
  caja.classList.add('cortina--fallo');
  caja.innerHTML = `
    <div class="cortina__panel" role="alert">
      <span class="cortina__icon cortina__icon--fallo">${icon('triangle-alert', 26)}</span>
      <h2 class="cortina__title">El motor no volvió</h2>
      <p class="cortina__detail">${mensaje}</p>
      <p class="cortina__meta">
        Cierra BIMNEMO y ábrelo con <code>BIMNEMO.bat --consola</code> para ver
        el error.
      </p>
      <button type="button" class="btn btn--primary" id="cortina-recargar">
        Recargar la ventana
      </button>
    </div>`;
  document
    .getElementById('cortina-recargar')
    ?.addEventListener('click', () => window.location.reload());
}
