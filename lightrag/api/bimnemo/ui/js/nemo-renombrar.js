/* ==========================================================================
   BIMNEMO — Renombrar una memoria
   --------------------------------------------------------------------------
   El servidor sabía hacerlo desde el principio; lo que faltaba era poder
   pedírselo.

   ## Por qué NO pide confirmación escrita, a diferencia del borrado

   Renombrar no destruye nada y siempre se puede volver a cambiar. Exigir que
   escribas el nombre para algo reversible enseña a confirmar sin leer — y
   entonces la confirmación del borrado, que sí importa, deja de servir.

   ## Por qué el nombre viene ya escrito y seleccionado

   Renombrar casi siempre es **corregir**, no empezar de cero. Escribes
   directamente si quieres sustituirlo, o pulsas una flecha si solo querías
   retocar una palabra.

   ## Y por qué la casilla de «por defecto» está aquí

   `POST /bimnemo/nemos/default` existía y tampoco tenía pantalla. Es el
   punto `·` que aparece junto a un nombre en el selector. Como el diálogo ya
   está abierto y habla de esa memoria, cerrar los dos huecos a la vez sale
   gratis; abrirle una ventana propia, no.
   ========================================================================== */

import { renameNemo, setDefaultNemo } from './api.js';

/** Lo que acepta el registro. Enterarse al pulsar «Guardar» es tarde. */
const MAXIMO = 60;

/** La memoria que se está renombrando, y su estado de partida. */
let objetivo = null;
let alTerminar = null;

const $ = (id) => document.getElementById(id);

/* --- Estado del formulario ------------------------------------------------ */

function refrescar() {
  const campo = $('nemo-rename-name');
  const guardar = $('nemo-rename-confirm');
  const contador = $('nemo-rename-count');
  const casilla = $('nemo-rename-default');
  if (!campo || !objetivo) return;

  const valor = campo.value.trim();
  const quedan = MAXIMO - campo.value.length;

  contador.textContent =
    quedan <= 10 ? `Quedan ${quedan} caracteres` : `Hasta ${MAXIMO} caracteres`;

  // Nada que guardar si no cambió ni el nombre ni la casilla. Un botón activo
  // que no va a hacer nada es una promesa que no se cumple.
  const cambioNombre = valor !== '' && valor !== objetivo.name;
  const cambioDefecto = casilla.checked !== objetivo.eraDefecto;
  guardar.disabled = !(cambioNombre || cambioDefecto);
}

function error(texto) {
  const hueco = $('nemo-rename-error');
  if (hueco) hueco.textContent = texto || '';
}

/* --- Abrir ---------------------------------------------------------------- */

/**
 * Abre el diálogo para la memoria indicada.
 *
 * @param {{id: string, name: string, esDefecto: boolean}} nemo
 * @param {() => void} cuandoCambie  Qué repintar al terminar.
 */
export function abrirRenombrado(nemo, cuandoCambie) {
  objetivo = { id: nemo.id, name: nemo.name, eraDefecto: !!nemo.esDefecto };
  alTerminar = cuandoCambie;

  const campo = $('nemo-rename-name');
  const casilla = $('nemo-rename-default');
  error('');
  campo.value = nemo.name;
  casilla.checked = !!nemo.esDefecto;
  // Ya es la de por defecto: quitarle la marca no es una operación que exista,
  // así que la casilla se apaga en vez de ofrecer algo que no se puede hacer.
  casilla.disabled = !!nemo.esDefecto;

  $('nemo-rename-confirm').textContent = 'Guardar';
  refrescar();
  $('nemo-rename-dialog').showModal();

  // Seleccionado, no solo enfocado: escribir sustituye, una flecha retoca.
  campo.focus();
  campo.select();
}

/* --- Guardar -------------------------------------------------------------- */

async function guardar(event) {
  event.preventDefault();
  if (!objetivo) return;

  const boton = $('nemo-rename-confirm');
  const nuevo = $('nemo-rename-name').value.trim();
  const quierePorDefecto = $('nemo-rename-default').checked;

  boton.disabled = true;
  boton.textContent = 'Guardando…';
  error('');

  try {
    // El nombre primero: es a lo que vino el usuario. Si la casilla falla
    // después, al menos lo principal quedó hecho y se puede decir qué no.
    if (nuevo && nuevo !== objetivo.name) {
      await renameNemo(objetivo.id, nuevo);
    }

    if (quierePorDefecto && !objetivo.eraDefecto) {
      try {
        await setDefaultNemo(objetivo.id);
      } catch (fallo) {
        error(
          `El nombre se guardó, pero no se pudo marcar por defecto: ${
            fallo.detail || fallo.message
          }`
        );
        boton.textContent = 'Guardar';
        if (alTerminar) await alTerminar();
        return;
      }
    }

    $('nemo-rename-dialog').close();
    if (alTerminar) await alTerminar();
  } catch (fallo) {
    // 409 es lo esperable: nombre repetido o vacío. Se dice bajo el campo,
    // que es donde el usuario está mirando.
    error(fallo.detail || fallo.message || 'No se pudo renombrar.');
    boton.textContent = 'Guardar';
    refrescar();
  }
}

/* --- Montaje -------------------------------------------------------------- */

export function mountRenombrado() {
  const dialogo = $('nemo-rename-dialog');
  if (!dialogo) return;

  $('nemo-rename-form').addEventListener('submit', guardar);
  $('nemo-rename-name').addEventListener('input', () => {
    error('');
    refrescar();
  });
  $('nemo-rename-default').addEventListener('change', refrescar);
  $('nemo-rename-cancel').addEventListener('click', () => dialogo.close());
}
