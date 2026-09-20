/* ==========================================================================
   BIMNEMO — Lienzo del grafo
   --------------------------------------------------------------------------
   Simulación de fuerzas y dibujo sobre <canvas>. No sabe de endpoints ni de
   memorias: recibe nodos y aristas ya aplanados y los pinta.

   Está escrito a mano y sin dependencias a propósito. BIMNEMO funciona sin
   conexión y sin paso de compilación: traer una librería de grafos por CDN
   rompería lo primero, y empaquetarla rompería lo segundo. Un grafo de unos
   cientos de nodos no necesita más que esto.
   ========================================================================== */

import { applyLayout, isSim, radiusOf } from './grafo-disposicion.js';
import { attachGestures } from './grafo-gestos.js';

/** Los ocho colores de categoría del Lookbook, en el orden en que se reparten. */
export const PALETTE = [
  'sky',
  'violet',
  'emerald',
  'orange',
  'teal',
  'rose',
  'amber',
  'slate',
];

/**
 * Reparte colores entre los tipos de entidad.
 *
 * El orden lo decide quien llama (por frecuencia), así que el tipo más común
 * se lleva siempre el primer color y el grafo no cambia de aspecto entre dos
 * lecturas seguidas de los mismos datos.
 */
export function assignColors(types) {
  const map = new Map();
  types.forEach((type, index) => map.set(type, PALETTE[index % PALETTE.length]));
  return map;
}

/* --- Constantes de la simulación ----------------------------------------- */

const REPULSION = 2400; // Empuje entre nodos; subirlo abre el grafo.
const SPRING = 0.05; // Tirón de cada arista.
const SPRING_LEN = 96; // Longitud en reposo de una arista, en píxeles.
const GRAVITY = 0.015; // Atracción hacia el centro, para que no se escape.
const DAMPING = 0.82; // Rozamiento; sin él el grafo oscila y no se asienta.
const ALPHA_DECAY = 0.984;
const ALPHA_MIN = 0.008;
const MAX_STEP = 40; // Tope de desplazamiento por paso, contra explosiones.

// Force Atlas reparte distinto: la repulsión crece con el número de
// relaciones de CADA extremo, así que los concentradores se apartan entre sí y
// arrastran a sus vecinos; y la atracción es lineal con la distancia, sin
// longitud en reposo. El resultado son cúmulos marcados en vez del reparto
// parejo de las fuerzas normales.
//
// Las dos constantes están calibradas para que un par unido se equilibre en
// `10 * raíz((ga+1)(gb+1))` píxeles: unos 40 entre dos nodos corrientes y unos
// 140 entre dos concentradores. Con los valores «naturales» de la fórmula, la
// repulsión salía cien veces mayor que la atracción y el grafo se deshacía.
const ATLAS_REPULSION = 2;
const ATLAS_ATTRACTION = 0.02;

//: Cuántas entidades llevan rótulo, de más conectadas a menos. Con todas, un
//: grafo mediano se convierte en una mancha de texto; sin ninguna, es un
//: adorno. Las más conectadas son las que dan sentido a lo demás.
const LABELLED = 40;

/** Lee los colores vigentes del tema. */
function readPalette(element) {
  const style = getComputedStyle(element);
  const value = (name, fallback) =>
    style.getPropertyValue(name).trim() || fallback;

  const cat = {};
  PALETTE.forEach((name) => {
    cat[name] = value('--cat-' + name, '#64748b');
  });
  return {
    cat,
    font: style.fontFamily,
    text: value('--content-primary', '#0f172a'),
    muted: value('--content-tertiary', '#64748b'),
    line: value('--border-medium', '#cbd5e1'),
    surface: value('--surface-elevated', '#ffffff'),
    accent: value('--oe-blue', '#2563eb'),
  };
}

/**
 * Crea el lienzo del grafo.
 *
 * @param {HTMLCanvasElement} canvas
 * @param {{onPick: (node: object|null) => void}} handlers
 */
export function createLienzo(canvas, { onPick, onActive = () => {} }) {
  const ctx = canvas.getContext('2d');

  let nodes = [];
  let edges = [];
  let colorOf = new Map();
  let view = { x: 0, y: 0, k: 1 };
  let alpha = 0;
  let frame = 0;
  let hovered = null;
  let selected = null;
  let matches = new Set(); // Resultados de la búsqueda, resaltados.
  let dragging = null;
  let panning = null;
  let moved = false;
  let layout = 'fuerzas';

  /* --- Tamaño ------------------------------------------------------------ */

  const size = () => ({
    w: canvas.clientWidth || 1,
    h: canvas.clientHeight || 1,
  });

  let lastW = 0;
  let lastH = 0;

  function resize() {
    const { w, h } = size();

    // Una vista oculta mide cero, y el observador de tamaño avisa igualmente.
    // Redimensionar el mapa de bits a cero ahí no aporta nada y sí destruye lo
    // dibujado, así que se sale sin tocarlo — solo se anota que estuvo oculto,
    // para volver a encuadrar cuando reaparezca.
    if (w <= 1 || h <= 1) {
      lastW = 0;
      lastH = 0;
      return;
    }

    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.round(w * ratio);
    canvas.height = Math.round(h * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

    const wasHidden = lastW <= 1;
    const prevW = lastW;
    const prevH = lastH;
    lastW = w;
    lastH = h;

    // El panel puede estar oculto cuando llegan los datos, y una vista oculta
    // mide cero: el encuadre calculado entonces no vale para nada. Al recuperar
    // tamaño se vuelve a encuadrar, que es lo que el usuario espera ver.
    if (wasHidden && w > 1 && nodes.length) {
      fit();
      return;
    }

    // Al cambiar de tamaño la vista se queda anclada a la esquina y el grafo se
    // sale de cuadro. Ante un cambio grande —redimensionar la ventana es un
    // gesto deliberado— se vuelve a encuadrar; ante uno pequeño basta con
    // mover la vista media diferencia, que respeta el zoom del usuario.
    //
    // Se miran los DOS lados. Mirando solo el ancho, bajar la ventana dejaba
    // el grafo cortado por abajo: el lienzo encogía de alto y nadie volvía a
    // encuadrarlo.
    if (prevW > 1) {
      const cambio = Math.max(
        Math.abs(w - prevW) / prevW,
        prevH > 1 ? Math.abs(h - prevH) / prevH : 0
      );
      if (nodes.length && cambio > 0.2) {
        fit();
        return;
      }
      view.x += (w - prevW) / 2;
      view.y += (h - prevH) / 2;
    }
    schedule();
  }

  /* --- Coordenadas ------------------------------------------------------- */

  const toScreen = (n) => ({ x: n.x * view.k + view.x, y: n.y * view.k + view.y });

  const toWorld = (px, py) => ({
    x: (px - view.x) / view.k,
    y: (py - view.y) / view.k,
  });

  function pointer(event) {
    const box = canvas.getBoundingClientRect();
    return { x: event.clientX - box.left, y: event.clientY - box.top };
  }

  /** Nodo bajo el cursor, o null. Se recorre al revés: se dibuja en orden. */
  function nodeAt(px, py) {
    for (let i = nodes.length - 1; i >= 0; i -= 1) {
      const node = nodes[i];
      const p = toScreen(node);
      const r = Math.max(6, radiusOf(node.degree) * view.k);
      if ((p.x - px) ** 2 + (p.y - py) ** 2 <= r * r) return node;
    }
    return null;
  }

  /* --- Simulación -------------------------------------------------------- */

  function step() {
    const n = nodes.length;
    for (let i = 0; i < n; i += 1) {
      const a = nodes[i];
      for (let j = i + 1; j < n; j += 1) {
        const b = nodes[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1) {
          // Dos nodos exactamente encima: se separan con un empujón al azar,
          // porque dividir por esa distancia los mandaría al infinito.
          dx = (Math.random() - 0.5) * 2;
          dy = (Math.random() - 0.5) * 2;
          d2 = 1;
        }
        const d = Math.sqrt(d2);
        const force =
          layout === 'atlas'
            ? (ATLAS_REPULSION * (a.degree + 1) * (b.degree + 1)) / d
            : REPULSION / d2;
        const fx = (dx / d) * force;
        const fy = (dy / d) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
    }

    edges.forEach((edge) => {
      const a = edge.from;
      const b = edge.to;
      if (!a || !b) return;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const pull =
        layout === 'atlas' ? d * ATLAS_ATTRACTION : (d - SPRING_LEN) * SPRING;
      const fx = (dx / d) * pull;
      const fy = (dy / d) * pull;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    });

    // La gravedad es elíptica, con la forma del lienzo: con una gravedad
    // redonda el grafo se agrupa en un círculo y deja vacíos los laterales de
    // una tarjeta que es mucho más ancha que alta.
    const { w, h } = size();
    const aspect = Math.max(1, Math.min(2.4, w / (h || 1)));

    nodes.forEach((node) => {
      node.vx -= (node.x * GRAVITY) / aspect;
      node.vy -= node.y * GRAVITY * aspect;
      if (node === dragging) {
        // El nodo que el usuario tiene cogido no se mueve solo.
        node.vx = 0;
        node.vy = 0;
        return;
      }
      node.vx *= DAMPING;
      node.vy *= DAMPING;
      node.x += Math.max(-MAX_STEP, Math.min(MAX_STEP, node.vx * alpha));
      node.y += Math.max(-MAX_STEP, Math.min(MAX_STEP, node.vy * alpha));
    });

    alpha *= ALPHA_DECAY;
  }

  /* --- Dibujo ------------------------------------------------------------ */

  function draw() {
    const colors = readPalette(canvas);
    const { w, h } = size();
    ctx.clearRect(0, 0, w, h);

    // Con un nodo enfocado, lo que no toca se apaga: en un grafo denso, ver
    // sus vecinos es justo lo que no se puede hacer a ojo.
    const focus = hovered || selected;
    const near = new Set();
    if (focus) {
      near.add(focus.id);
      edges.forEach((edge) => {
        if (edge.source === focus.id) near.add(edge.target);
        if (edge.target === focus.id) near.add(edge.source);
      });
    }

    // Aristas primero: las líneas van por debajo de los círculos.
    edges.forEach((edge) => {
      const a = edge.from;
      const b = edge.to;
      if (!a || !b) return;
      const linked =
        focus && (edge.source === focus.id || edge.target === focus.id);
      const p = toScreen(a);
      const q = toScreen(b);
      ctx.strokeStyle = linked ? colors.accent : colors.line;
      ctx.globalAlpha = focus ? (linked ? 0.95 : 0.14) : 0.5;
      ctx.lineWidth = linked ? 1.6 : 1;
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
      ctx.lineTo(q.x, q.y);
      ctx.stroke();
    });
    ctx.globalAlpha = 1;

    nodes.forEach((node) => {
      const p = toScreen(node);
      const r = Math.max(2, radiusOf(node.degree) * view.k);
      const dim = focus && !near.has(node.id);
      const marked = matches.has(node.id) || node === selected;

      ctx.globalAlpha = dim ? 0.2 : 1;
      ctx.beginPath();
      ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fillStyle = colors.cat[colorOf.get(node.type) || 'slate'];
      ctx.fill();
      ctx.strokeStyle = marked ? colors.accent : colors.surface;
      ctx.lineWidth = marked ? 2.5 : 1.5;
      ctx.stroke();

      // Rótulo para las entidades con más relaciones, siempre que el círculo
      // no se haya quedado en un punto. El nodo enfocado o buscado lo lleva
      // aunque no entre en ese grupo: es justo el que se está mirando.
      if (!dim && ((node.rank < LABELLED && r >= 5) || node === focus || marked)) {
        ctx.globalAlpha = 1;
        ctx.fillStyle = node === focus ? colors.text : colors.muted;
        ctx.font = (node === focus ? '600 ' : '400 ') + '11px ' + colors.font;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        const label =
          node.label.length > 26 ? node.label.slice(0, 25) + '…' : node.label;
        ctx.fillText(label, p.x, p.y + r + 3);
      }
      ctx.globalAlpha = 1;
    });
  }

  function schedule() {
    if (frame) return;
    frame = window.requestAnimationFrame(tick);
  }

  /**
   * Un fotograma.
   *
   * Mientras la simulación tiene energía se encadenan solos; cuando se
   * asienta, se deja de pedir fotogramas y el lienzo no consume nada hasta
   * que alguien lo toca.
   */
  function tick() {
    frame = 0;
    if (isSim(layout) && alpha > ALPHA_MIN) {
      step();
      draw();
      schedule();
    } else {
      draw();
    }
  }

  /* --- Encuadre ---------------------------------------------------------- */

  function fit() {
    const { w, h } = size();
    if (!nodes.length) {
      view = { x: w / 2, y: h / 2, k: 1 };
      schedule();
      return;
    }

    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    nodes.forEach((n) => {
      minX = Math.min(minX, n.x);
      minY = Math.min(minY, n.y);
      maxX = Math.max(maxX, n.x);
      maxY = Math.max(maxY, n.y);
    });

    const margin = 64;
    const k = Math.min(
      2.5,
      Math.max(
        0.12,
        Math.min(
          (w - margin) / (maxX - minX || 1),
          (h - margin) / (maxY - minY || 1)
        )
      )
    );
    view = {
      k,
      x: w / 2 - ((minX + maxX) / 2) * k,
      y: h / 2 - ((minY + maxY) / 2) * k,
    };
    schedule();
  }

  /** Zoom manteniendo fijo el punto señalado. */
  function zoomBy(factor, at) {
    const point = at || { x: size().w / 2, y: size().h / 2 };
    const before = toWorld(point.x, point.y);
    view.k = Math.max(0.1, Math.min(4, view.k * factor));
    view.x = point.x - before.x * view.k;
    view.y = point.y - before.y * view.k;
    schedule();
  }

  /* --- Interacción ------------------------------------------------------- */

  // Los gestos viven en `grafo-gestos.js`: el lienzo le presta lo que puede
  // consultar y mover, y recibe de vuelta lo que el usuario hace.
  const gestos = attachGestures(canvas, {
    pointer,
    nodeAt,
    getHovered: () => hovered,
    setHovered(node) {
      hovered = node;
      schedule();
    },
    startDrag(node) {
      dragging = node;
      // Arrastrar un nodo reanima la simulación: el resto se recoloca solo.
      alpha = Math.max(alpha, 0.35);
      schedule();
    },
    dragTo(p) {
      const world = toWorld(p.x, p.y);
      dragging.x = world.x;
      dragging.y = world.y;
      schedule();
    },
    startPan(p) {
      panning = { x: p.x - view.x, y: p.y - view.y };
    },
    panTo(p) {
      view.x = p.x - panning.x;
      view.y = p.y - panning.y;
      schedule();
    },
    endGesture({ clic, sobreNodo }) {
      if (clic && sobreNodo) {
        selected = dragging === selected ? null : dragging;
        onPick(selected);
      } else if (clic) {
        selected = null;
        onPick(null);
      }
      dragging = null;
      panning = null;
      schedule();
    },
    zoomBy,
    onActiveChange: (activo) => onActive(activo),
  });

  const observer = new ResizeObserver(resize);
  observer.observe(canvas);

  /* --- Lo que se ofrece fuera --------------------------------------------- */

  return {
    /**
     * Carga un grafo nuevo.
     *
     * Las posiciones de partida se reparten en espiral en vez de al azar: dos
     * nodos nunca nacen encima y la simulación converge bastante antes.
     */
    setData(data, colors) {
      colorOf = colors;
      const index = new Map();

      // Puesto por número de relaciones: decide quién lleva rótulo. Se calcula
      // una vez, no en cada fotograma.
      const rank = new Map();
      [...data.nodes]
        .sort((a, b) => b.degree - a.degree)
        .forEach((node, position) => rank.set(node.id, position));

      nodes = data.nodes.map((node, i) => {
        const angle = i * 2.399; // Ángulo áureo: reparto sin huecos ni filas.
        const radius = 18 * Math.sqrt(i + 1);
        const placed = {
          ...node,
          rank: rank.get(node.id) ?? Infinity,
          x: Math.cos(angle) * radius,
          y: Math.sin(angle) * radius,
          vx: 0,
          vy: 0,
        };
        index.set(node.id, placed);
        return placed;
      });
      edges = data.edges.map((edge) => ({
        ...edge,
        from: index.get(edge.source),
        to: index.get(edge.target),
      }));
      selected = null;
      hovered = null;
      matches = new Set();
      alpha = 1;
      // Una disposición fija coloca de una vez y no hace falta esperar a que
      // nada se asiente: se encuadra en cuanto está puesta.
      const fija = applyLayout(layout, nodes);
      resize();
      if (fija) {
        fit();
        schedule();
        return;
      }
      // Se deja correr un poco y se encuadra cuando ya tiene forma: encuadrar
      // sobre la espiral de partida daría siempre un encuadre equivocado.
      window.setTimeout(fit, 700);
      schedule();
    },

    /**
     * Cambia de disposición sin volver a pedir datos.
     *
     * Las fijas colocan y encuadran; las de simulación arrancan desde donde
     * estén los nodos, así que pasar de circular a fuerzas se ve relajarse en
     * vez de saltar de golpe.
     */
    setLayout(key) {
      layout = key;
      if (applyLayout(layout, nodes)) {
        fit();
      } else {
        alpha = 1;
      }
      schedule();
    },

    setMatches(ids) {
      matches = new Set(ids);
      schedule();
    },

    /** Selecciona una entidad por identificador y la trae al centro. */
    select(id) {
      selected = nodes.find((n) => n.id === id) || null;
      if (selected) {
        const { w, h } = size();
        view.x = w / 2 - selected.x * view.k;
        view.y = h / 2 - selected.y * view.k;
      }
      onPick(selected);
      schedule();
    },

    fit,
    zoomIn: () => zoomBy(1.25),
    zoomOut: () => zoomBy(1 / 1.25),
    repaint: schedule,

    /** Deja el lienzo en reposo: la rueda vuelve a desplazar la página. */
    deactivate: () => gestos.deactivate(),

    destroy() {
      gestos.destroy();
      observer.disconnect();
      if (frame) window.cancelAnimationFrame(frame);
    },
  };
}
