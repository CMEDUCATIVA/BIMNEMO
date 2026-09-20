/* ==========================================================================
   BIMNEMO — Gestos del grafo
   --------------------------------------------------------------------------
   Ratón y rueda sobre el lienzo. Vive aparte del dibujo porque responde a otra
   pregunta —qué hace el usuario— y porque `grafo-lienzo.js` ya pasaba de 600
   líneas con esto dentro.

   ## El lienzo no se activa solo

   Antes, con solo pasar por encima el grafo ya reaccionaba, y la rueda hacía
   zoom en lugar de desplazar el panel. Eso convierte al lienzo en una trampa:
   el grafo ocupa casi toda la primera vista, así que bajar por el panel con la
   rueda era imposible sin acabar ampliando el grafo sin querer.

   Ahora hay dos estados:

   - **En reposo** — la rueda desplaza la página como en cualquier otro sitio y
     el grafo no responde al paso del ratón. Es un dibujo.
   - **Activo** — tras pulsar sobre él. Entonces sí: rueda para acercar, paso
     del ratón para resaltar vecinos, arrastre para mover.

   Se sale pulsando fuera o con Escape. Es el mismo trato que dan los mapas
   incrustados, y por el mismo motivo.
   ========================================================================== */

/** Cuánto acerca o aleja un golpe de rueda. */
const ZOOM_RUEDA = 1.12;

/**
 * Conecta ratón y rueda a un lienzo.
 *
 * @param {HTMLCanvasElement} canvas
 * @param {object} api  Lo que el lienzo deja hacer: consultar, mover y avisar.
 * @returns {{isActive: () => boolean, deactivate: () => void, destroy: () => void}}
 */
export function attachGestures(canvas, api) {
  const {
    pointer, // coordenadas del evento dentro del lienzo
    nodeAt, // qué nodo hay en un punto
    getHovered,
    setHovered,
    startDrag,
    dragTo,
    startPan,
    panTo,
    endGesture,
    zoomBy,
    onActiveChange,
  } = api;

  let activo = false;
  let arrastrando = false;
  let desplazando = false;
  let movido = false;

  function setActivo(valor) {
    if (activo === valor) return;
    activo = valor;
    if (!valor) setHovered(null);
    canvas.style.cursor = valor ? 'grab' : 'default';
    onActiveChange(valor);
  }

  /* --- Ratón -------------------------------------------------------------- */

  canvas.addEventListener('pointerdown', (event) => {
    // El primer clic activa Y empieza el gesto: obligar a pulsar dos veces
    // para arrastrar sería una ceremonia sin motivo.
    setActivo(true);
    canvas.setPointerCapture(event.pointerId);
    const p = pointer(event);
    movido = false;

    const node = nodeAt(p.x, p.y);
    if (node) {
      arrastrando = true;
      startDrag(node);
    } else {
      desplazando = true;
      startPan(p);
    }
  });

  canvas.addEventListener('pointermove', (event) => {
    const p = pointer(event);
    if (arrastrando) {
      movido = true;
      dragTo(p);
      return;
    }
    if (desplazando) {
      movido = true;
      panTo(p);
      return;
    }
    // En reposo el grafo no reacciona al paso del ratón: es lo que hacía que
    // «agarrase» sin haberlo pedido.
    if (!activo) return;

    const node = nodeAt(p.x, p.y);
    canvas.style.cursor = node ? 'pointer' : 'grab';
    if (node !== getHovered()) setHovered(node);
  });

  /**
   * Fin del gesto.
   *
   * Un clic es un arrastre que no llegó a moverse; distinguirlos aquí evita
   * tener que decidirlo por tiempo, que falla con la mano temblorosa.
   */
  function soltar(event) {
    const fueClic = !movido && (arrastrando || desplazando);
    endGesture({ clic: fueClic, sobreNodo: arrastrando });
    arrastrando = false;
    desplazando = false;
    if (event && canvas.hasPointerCapture?.(event.pointerId)) {
      canvas.releasePointerCapture(event.pointerId);
    }
  }

  canvas.addEventListener('pointerup', soltar);
  canvas.addEventListener('pointercancel', soltar);
  canvas.addEventListener('pointerleave', () => {
    if (getHovered()) setHovered(null);
  });

  /* --- Rueda -------------------------------------------------------------- */

  canvas.addEventListener(
    'wheel',
    (event) => {
      // En reposo NO se llama a preventDefault: el navegador desplaza la
      // página, que es lo que el usuario está pidiendo al girar la rueda
      // sobre un panel largo. Con Ctrl se amplía aunque esté en reposo,
      // porque ese gesto ya significa «zoom» en todas partes.
      if (!activo && !event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      zoomBy(event.deltaY < 0 ? ZOOM_RUEDA : 1 / ZOOM_RUEDA, pointer(event));
    },
    { passive: false }
  );

  /* --- Salir del lienzo --------------------------------------------------- */

  const fuera = (event) => {
    if (!canvas.contains(event.target)) setActivo(false);
  };
  const escape = (event) => {
    if (event.key === 'Escape') setActivo(false);
  };

  document.addEventListener('pointerdown', fuera, true);
  document.addEventListener('keydown', escape);

  canvas.style.cursor = 'default';

  return {
    isActive: () => activo,
    deactivate: () => setActivo(false),
    destroy() {
      document.removeEventListener('pointerdown', fuera, true);
      document.removeEventListener('keydown', escape);
    },
  };
}
