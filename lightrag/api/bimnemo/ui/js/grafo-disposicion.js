/* ==========================================================================
   BIMNEMO — Disposiciones del grafo
   --------------------------------------------------------------------------
   Dónde se coloca cada entidad. El lienzo se ocupa de dibujarlas y de
   manejarlas; aquí solo se decide la forma.

   Hay dos familias y se comportan distinto:

   - Las de **simulación** (fuerzas, atlas) no calculan posiciones: ajustan las
     fuerzas y dejan que el grafo se asiente solo. Se mueven al cargar y al
     arrastrar un nodo.
   - Las **fijas** (circular, tipos, radial) colocan cada nodo de una vez y se
     quedan quietas. Sirven para leer, no para explorar: la circular enseña de
     un vistazo cuántas entidades hay de cada tipo, y la radial pone en el
     centro lo que más relaciones tiene.
   ========================================================================== */

/** Separación mínima entre centros de nodos en las disposiciones fijas. */
const SEPARACION = 30;

//: Separación entre vecinos de un mismo anillo. Es casi el doble que la
//: mínima porque en un anillo los nodos llevan el rótulo debajo: con la
//: separación justa los círculos no se tocan, pero los nombres sí.
const SEPARACION_ANILLO = 54;

/**
 * Radio del círculo de una entidad, según cuántas relaciones tiene.
 *
 * Vive aquí y no en el lienzo porque el empaquetado necesita saber cuánto
 * ocupa cada nodo antes de colocarlo.
 */
export function radiusOf(degree) {
  return 6 + Math.min(15, Math.sqrt(degree) * 3.2);
}

/** Las disposiciones que se ofrecen, en el orden en que salen en el selector. */
export const LAYOUTS = [
  { key: 'fuerzas', label: 'Fuerzas', kind: 'sim' },
  { key: 'atlas', label: 'Force Atlas', kind: 'sim' },
  { key: 'circular', label: 'Circular', kind: 'fija' },
  { key: 'tipos', label: 'Círculos por tipo', kind: 'fija' },
  { key: 'radial', label: 'Radial por conexiones', kind: 'fija' },
];

const BY_KEY = new Map(LAYOUTS.map((l) => [l.key, l]));

export const isSim = (key) => (BY_KEY.get(key) || LAYOUTS[0]).kind === 'sim';

/* --- Circular ------------------------------------------------------------- */

/**
 * Todas las entidades en un círculo, agrupadas por tipo.
 *
 * Agrupar por tipo es lo que hace útil esta disposición: cada tipo ocupa un
 * arco continuo y se ve de un vistazo cuánto pesa cada uno. Ordenadas al azar
 * —como haría un círculo «puro»— solo sería una lista doblada.
 */
function circular(nodes) {
  const ordenados = [...nodes].sort(
    (a, b) =>
      a.type.localeCompare(b.type) ||
      b.degree - a.degree ||
      a.label.localeCompare(b.label)
  );
  const n = ordenados.length || 1;
  const radio = Math.max(140, (SEPARACION_ANILLO * n) / (2 * Math.PI));

  ordenados.forEach((node, i) => {
    const angulo = (i / n) * 2 * Math.PI - Math.PI / 2;
    node.x = Math.cos(angulo) * radio;
    node.y = Math.sin(angulo) * radio;
  });
}

/* --- Círculos por tipo ---------------------------------------------------- */

/** Reparte m puntos dentro de un disco, en espiral áurea (sin huecos ni filas). */
function espiral(m, paso) {
  const puntos = [];
  for (let i = 0; i < m; i += 1) {
    const angulo = i * 2.399;
    const radio = paso * Math.sqrt(i + 0.5);
    puntos.push({ x: Math.cos(angulo) * radio, y: Math.sin(angulo) * radio });
  }
  return puntos;
}

/**
 * Un disco por tipo de entidad, y los discos repartidos en corona.
 *
 * Es el equivalente del «circlepack» de LightRAG, pero agrupando por tipo en
 * vez de empaquetar sin más: empaquetar por empaquetar da una forma bonita que
 * no dice nada, y el tipo de entidad es la única agrupación que la memoria
 * conoce de verdad.
 */
function porTipos(nodes) {
  const grupos = new Map();
  nodes.forEach((node) => {
    if (!grupos.has(node.type)) grupos.set(node.type, []);
    grupos.get(node.type).push(node);
  });

  // De mayor a menor: los tipos numerosos primero, para que la corona no
  // empiece con un grupo de un solo nodo.
  const ordenados = [...grupos.entries()].sort(
    (a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0])
  );

  const discos = ordenados.map(([tipo, miembros]) => ({
    tipo,
    miembros,
    radio: Math.max(SEPARACION, (SEPARACION * Math.sqrt(miembros.length)) / 1.5),
  }));

  // Un solo tipo: no hay corona que repartir, ocupa el centro.
  if (discos.length === 1) {
    colocarDisco(discos[0], 0, 0);
    return;
  }

  const hueco = SEPARACION;
  const perimetro = discos.reduce((suma, d) => suma + 2 * d.radio + hueco, 0);
  const coronaR = Math.max(140, perimetro / (2 * Math.PI));

  let recorrido = 0;
  discos.forEach((disco) => {
    const tramo = 2 * disco.radio + hueco;
    // El ángulo de cada disco es proporcional a su tamaño: así los grandes no
    // se pisan con los pequeños.
    const angulo = ((recorrido + tramo / 2) / perimetro) * 2 * Math.PI - Math.PI / 2;
    recorrido += tramo;
    colocarDisco(disco, Math.cos(angulo) * coronaR, Math.sin(angulo) * coronaR);
  });
}

function colocarDisco(disco, cx, cy) {
  const ordenados = [...disco.miembros].sort((a, b) => b.degree - a.degree);
  const puntos = espiral(ordenados.length, SEPARACION * 0.62);
  ordenados.forEach((node, i) => {
    node.x = cx + puntos[i].x;
    node.y = cy + puntos[i].y;
  });
}

/* --- Radial por conexiones ------------------------------------------------ */

/**
 * Anillos concéntricos: cuantas más relaciones, más al centro.
 *
 * Responde de un vistazo a «qué sostiene esta memoria», que en un grafo de
 * fuerzas hay que deducir mirando cuál tiene más líneas.
 */
function radial(nodes) {
  if (!nodes.length) return;
  const ordenados = [...nodes].sort(
    (a, b) => b.degree - a.degree || a.label.localeCompare(b.label)
  );

  // La más conectada va sola en el centro.
  ordenados[0].x = 0;
  ordenados[0].y = 0;

  let indice = 1;
  let anillo = 1;
  let radioAnterior = 0;

  while (indice < ordenados.length) {
    // Se decide PRIMERO cuántas caben y DESPUÉS el radio, no al revés: con el
    // radio fijado de antemano, los anillos interiores salían con los nodos
    // pegados y los rótulos encima unos de otros.
    const cabida = 6 * anillo;
    const restantes = ordenados.length - indice;
    // Si lo que queda casi cabe, entra todo: un anillo exterior con un solo
    // nodo deja el grafo descentrado y desperdicia la mitad del lienzo.
    const cuantos = restantes <= cabida * 1.5 ? restantes : cabida;
    const tanda = ordenados.slice(indice, indice + cuantos);

    const radio = Math.max(
      radioAnterior + SEPARACION * 2.8,
      (tanda.length * SEPARACION_ANILLO) / (2 * Math.PI)
    );

    tanda.forEach((node, i) => {
      const angulo = (i / tanda.length) * 2 * Math.PI - Math.PI / 2;
      node.x = Math.cos(angulo) * radio;
      node.y = Math.sin(angulo) * radio;
    });

    radioAnterior = radio;
    indice += tanda.length;
    anillo += 1;
  }
}

/* --- Aplicar -------------------------------------------------------------- */

const FIJAS = { circular, tipos: porTipos, radial };

/**
 * Coloca los nodos según la disposición pedida.
 *
 * Devuelve `true` si ha movido algo. Para las de simulación devuelve `false`:
 * ahí las posiciones las decide el lienzo, no este módulo.
 */
export function applyLayout(key, nodes) {
  const fija = FIJAS[key];
  if (!fija || !nodes.length) return false;
  fija(nodes);
  nodes.forEach((node) => {
    node.vx = 0;
    node.vy = 0;
  });
  return true;
}
