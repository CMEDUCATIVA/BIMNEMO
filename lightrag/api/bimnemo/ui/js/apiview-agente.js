/* ==========================================================================
   BIMNEMO — La instrucción que se pega en una IA
   --------------------------------------------------------------------------
   Es el bloque que el usuario copia en su skill. Antes estaba escrito a mano
   y enseñaba **un** endpoint de los muchos que hay; peor, no decía nada de
   las memorias, así que una IA que lo leyera no podía elegir entre «General»
   y «Obra Sur» — que es de lo que va la aplicación entera.

   ## Se genera del manifiesto, no se escribe aparte

   Si fueran dos listas acabarían discrepando, y la que discreparía sin que
   nadie lo notase es justo ésta: la que se pega y se olvida dentro de una
   skill. Una sola fuente, `bimnemo/manifiesto.py`.

   ## Cabe, y se lee

   Lo lee un modelo con contexto limitado y lo revisa una persona. Por eso va
   **agrupado por lo que permite** —leer, explorar, guardar, borrar—, con el
   cuerpo mínimo de cada llamada y nada más. El cuerpo importa: saber que
   existe `/nemo/{nemo}/memory/remember` no dice qué hay que mandarle, y ese
   era justo el trabajo que obligaba a ir a Swagger.
   ========================================================================== */

/** En qué orden se leen bien los grupos. */
const ORDEN = ['consultar', 'explorar', 'guardar', 'borrar'];

/** Cuerpo de ejemplo en una línea, si lo lleva. */
function cuerpo(ep) {
  return ep.body ? `\n      ${JSON.stringify(ep.body)}` : '';
}

function bloqueDeGrupo(grupo, titulo, endpoints) {
  const suyos = endpoints.filter((e) => e.group === grupo);
  if (!suyos.length) return '';

  const lineas = suyos
    .map((e) => `  ${e.method} ${e.path}\n      ${e.purpose}${cuerpo(e)}`)
    .join('\n\n');

  return `\n${titulo.toUpperCase()}\n\n${lineas}\n`;
}

/**
 * La instrucción completa, lista para pegar.
 *
 * @param {string} url         Dirección de esta memoria.
 * @param {object} manifest    Lo que devuelve `/bimnemo/memory/manifest`.
 * @param {boolean} protegida  Si la API pide clave.
 * @param {string} clave       La clave, cuando la haya.
 */
export function instruccionParaAgente(url, manifest, protegida, clave) {
  const endpoints = manifest.endpoints || [];
  const grupos = manifest.groups || {};
  const modos = manifest.retrieval_modes || {};

  // La cabecera va arriba del todo: si falta, ninguna de las llamadas de abajo
  // funciona, y un 401 sin explicación es lo peor que le puede pasar a un
  // agente — no tiene forma de deducir qué le falta.
  const acceso = protegida
    ? `\nTODAS las llamadas necesitan esta cabecera:\n\n  X-API-Key: ${clave}\n`
    : '\nEsta memoria no pide credencial.\n';

  const cuerpoGrupos = ORDEN.map((g) =>
    bloqueDeGrupo(g, grupos[g] || g, endpoints),
  ).join('');

  const listaModos = Object.entries(modos)
    .map(([nombre, para]) => `  ${nombre.padEnd(8)}${para}`)
    .join('\n');

  const puedeBorrar = endpoints.some((e) => e.group === 'borrar');

  return `Tienes acceso a BIMNEMO, una memoria de conocimiento con grafo que
corre en ${url}.

Antes de responder cualquier pregunta sobre los documentos del proyecto,
consulta la memoria en vez de improvisar. Usa el campo "context" de la
respuesta como tu fuente; si viene vacío, dilo.
${acceso}
BIMNEMO guarda VARIAS memorias separadas. Pide primero
GET /bimnemo/nemos para saber cuáles hay y cuál está activa. Las rutas
/bimnemo/… trabajan sobre la activa; las /nemo/{nemo}/… sobre la que
indiques.
${cuerpoGrupos}
MODOS DE RECUPERACIÓN (el campo "mode")

${listaModos}
${
  puedeBorrar
    ? `
CUIDADO CON EL BORRADO

  Borrar un documento se lleva por delante lo que el motor aprendió de él y
  no se puede deshacer. No borres nada que no te hayan pedido borrar
  explícitamente, y di qué vas a borrar antes de hacerlo.
`
    : ''
}
El descriptor completo, siempre al día, está en
${url}/bimnemo/memory/manifest`;
}
