/* ==========================================================================
   BIMNEMO — De una plantilla a la ruta que de verdad funciona
   --------------------------------------------------------------------------
   El manifiesto describe **la API**: dice que existe `/bimnemo/memory/search`
   —sobre la memoria activa— y `/nemo/{nemo}/memory/search` —sobre una
   concreta—. Eso es correcto como descriptor y **inservible para copiar**.

   Quien copia tiene que saber que `{nemo}` es un identificador y no el
   nombre, averiguar cuál es —«Obra Sur» es `Obra_Sur`, y «Licitación Pública»
   es `Licitaci_n_P_blica`— y sustituirlo en cada línea.

   ## Y con la memoria por defecto no hay sustitución que valga

   Su identificador es **la cadena vacía**: `/nemo//memory/search` responde
   404. Hay que usar `/bimnemo/…` **sin parámetro**. Una plantilla genérica no
   puede expresar eso, así que lo que hoy se copia no funciona al pegarlo para
   la memoria que casi todo el mundo tiene abierta.

   Este módulo resuelve las dos cosas: elige la forma correcta y la rellena.
   ========================================================================== */

/**
 * Pares que son **la misma operación** vista desde dos sitios.
 *
 * Una vez elegida una memoria concreta, enseñar las dos es enseñar la misma
 * fila dos veces. La clave es la operación; el valor, qué ruta usar según la
 * memoria tenga identificador o sea la de por defecto.
 */
const GEMELOS = [
  {
    conNombre: '/nemo/{nemo}/memory/search',
    porDefecto: '/bimnemo/memory/search',
  },
  {
    conNombre: '/nemo/{nemo}/memory/remember',
    porDefecto: '/bimnemo/memory/remember',
  },
];

/**
 * Rutas que para la memoria por defecto son **otra ruta distinta**.
 *
 * Subir a la memoria por defecto no es `/nemo//documents/upload`: es la ruta
 * oficial de LightRAG, que es justo lo que hace la propia aplicación.
 */
const EQUIVALENTES_POR_DEFECTO = {
  '/nemo/{nemo}/documents/upload': '/documents/upload',
};

/** ¿Esta ruta lleva el identificador en el camino? */
const llevaNemoEnElCamino = (ruta) => ruta.includes('{nemo}');

/** ¿Esta ruta acepta `?nemo=` para elegir memoria? */
const aceptaParametro = (ruta) =>
  ruta.startsWith('/bimnemo/') &&
  !ruta.startsWith('/bimnemo/nemos') &&
  !ruta.includes('memory/search-all') &&
  !ruta.includes('memory/ask-all');

/**
 * La ruta concreta de un endpoint para una memoria.
 *
 * @param {object} ep       Entrada del manifiesto.
 * @param {string} nemoId   Identificador. Cadena vacía: la de por defecto.
 * @returns {string|null}   La ruta, o `null` si ese endpoint no aplica a esta
 *                          memoria (el gemelo que sobra).
 */
export function rutaPara(ep, nemoId) {
  const esPorDefecto = !nemoId;
  const ruta = ep.path;

  // De cada par de gemelos se queda uno, según la memoria.
  for (const par of GEMELOS) {
    if (ruta === par.conNombre) return esPorDefecto ? null : rellenar(ruta, nemoId);
    if (ruta === par.porDefecto) return esPorDefecto ? ruta : null;
  }

  if (esPorDefecto && EQUIVALENTES_POR_DEFECTO[ruta]) {
    return EQUIVALENTES_POR_DEFECTO[ruta];
  }

  if (llevaNemoEnElCamino(ruta)) {
    return esPorDefecto ? null : rellenar(ruta, nemoId);
  }

  // `?nemo=` solo cuando hay identificador: omitirlo ES decir «la de por
  // defecto», y ponerlo vacío no significa lo mismo.
  if (!esPorDefecto && aceptaParametro(ruta)) {
    return `${ruta}?nemo=${encodeURIComponent(nemoId)}`;
  }

  return ruta;
}

function rellenar(ruta, nemoId) {
  return ruta.replace('{nemo}', encodeURIComponent(nemoId));
}

/**
 * Los endpoints que aplican a una memoria, ya resueltos y agrupados.
 *
 * @param {Array} endpoints  Los del manifiesto.
 * @param {string} nemoId
 * @param {object} ambitos   Rótulo de cada ámbito.
 * @returns {Array<{clave: string, titulo: string, filas: Array}>}
 */
export function agruparPorAmbito(endpoints, nemoId, ambitos) {
  const orden = ['esta', 'todas', 'motor'];
  const cajas = new Map(orden.map((k) => [k, []]));

  for (const ep of endpoints) {
    const ruta = rutaPara(ep, nemoId);
    if (ruta === null) continue; // el gemelo que sobra para esta memoria
    const ambito = ep.scope || 'esta';
    if (!cajas.has(ambito)) cajas.set(ambito, []);
    cajas.get(ambito).push({ ...ep, ruta });
  }

  return [...cajas.entries()]
    .filter(([, filas]) => filas.length > 0)
    .map(([clave, filas]) => ({
      clave,
      titulo: ambitos[clave] || clave,
      filas,
    }));
}

/**
 * Las rutas de las operaciones que los ejemplos necesitan, ya resueltas.
 *
 * Los ejemplos de curl y Python enseñaban `/bimnemo/memory/search` fijo. Con
 * «Obra Sur» abierta eso lee **otra memoria** —la de por defecto—, así que el
 * ejemplo funcionaba al pegarlo y devolvía lo que no era. Peor que fallar.
 */
export function rutasDeMemoria(endpoints, nemoId) {
  const dame = (candidatas) => {
    for (const ruta of candidatas) {
      const ep = (endpoints || []).find((e) => e.path === ruta);
      if (!ep) continue;
      const resuelta = rutaPara(ep, nemoId);
      if (resuelta) return resuelta;
    }
    return candidatas[candidatas.length - 1];
  };

  return {
    buscar: dame(['/nemo/{nemo}/memory/search', '/bimnemo/memory/search']),
    recordar: dame(['/nemo/{nemo}/memory/remember', '/bimnemo/memory/remember']),
  };
}
