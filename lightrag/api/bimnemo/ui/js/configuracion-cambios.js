/* ==========================================================================
   BIMNEMO — ¿Ha cambiado la configuración?
   --------------------------------------------------------------------------
   Vive aparte porque no es parte del formulario: es la pregunta que le hace
   la navegación antes de dejarte salir. Y porque `configuracion.js` llegaba a
   605 líneas con esto dentro.
   ========================================================================== */

let dirty = false;

/** Retrato del formulario tal y como se cargó. La vara de medir. */
let referencia = null;

/** Cómo leer el formulario. Lo inyecta `configuracion.js` al montarse. */
let leer = null;

/** Registra cómo se toma el retrato del formulario. */
export function setLector(fn) {
  leer = fn;
}

/**
 * Cómo está el formulario **ahora**, en texto comparable.
 *
 * La clave de API no sale de aquí: `readSection` devuelve el centinela
 * «sin cambios» mientras el campo esté vacío, así que solo cuenta si el
 * usuario escribe una nueva.
 */
export function retrato() {
  if (!leer) return null;
  try {
    return JSON.stringify(leer());
  } catch {
    // El formulario todavía no está pintado: nada que comparar.
    return null;
  }
}

/**
 * Marca si hay cambios **comparando con lo que se cargó**, no con una bandera.
 *
 * Antes bastaba con que saltara un evento `input` en la tarjeta para darlo
 * por sucio — y saltan solos: el combo del modelo emite uno al elegir, el
 * gestor de contraseñas del navegador rellena la clave, un `change` del
 * selector… Resultado: el aviso de «tienes cambios sin guardar» salía
 * **siempre** al salir de la pantalla, aunque no se hubiera tocado nada, y
 * acababa siendo ruido que se contesta sin leer.
 *
 * Comparando dos retratos eso no puede pasar: si el formulario dice lo mismo
 * que cuando se cargó, no hay cambios, haya saltado el evento que haya
 * saltado.
 */
export function markDirty() {
  const ahora = retrato();
  dirty = referencia !== null && ahora !== null && ahora !== referencia;
  document.getElementById('nav-config-flag').textContent = dirty ? '●' : '';
}

/** Fija la referencia con lo que hay ahora. Tras pintar y tras guardar. */
export function setReferencia() {
  referencia = retrato();
  markDirty();
}

/** Olvida la referencia: el formulario se va a repintar entero. */
export function olvidarReferencia() {
  referencia = null;
}

/** ¿Hay cambios sin guardar? Lo usa la navegación para avisar al salir. */
export function hasUnsavedChanges() {
  return dirty;
}
