/* ==========================================================================
   BIMNEMO — La instrucción que se pega en una IA
   --------------------------------------------------------------------------
   Es el bloque que el usuario copia en su skill.

   ## Habla de LA MEMORIA QUE TIENE ABIERTA

   Antes traía plantillas: `/nemo/{nemo}/memory/search`. Quien la pegaba tenía
   que saber que `{nemo}` es un identificador y no el nombre, averiguar cuál
   —«Obra Sur» es `Obra_Sur`— y sustituirlo línea por línea. Y para la memoria
   por defecto **no había sustitución posible**: su identificador es la cadena
   vacía y `/nemo//…` responde 404.

   Ahora las rutas vienen resueltas. Se pega y funciona.

   ## Se genera del manifiesto, no se escribe aparte

   Si fueran dos listas acabarían discrepando, y la que discreparía sin que
   nadie lo notase es justo ésta: la que se pega y se olvida dentro de una
   skill.

   ## Agrupado por lo que permite

   Lo lee un modelo con contexto limitado y lo revisa una persona. Por eso va
   por ámbito —esta memoria, todas, el motor— con el cuerpo mínimo de cada
   llamada. El cuerpo importa: saber que existe `remember` no dice **qué**
   mandarle, y ése era el trabajo que obligaba a ir a Swagger.
   ========================================================================== */

import { agruparPorAmbito } from './apiview-rutas.js';

/**
 * Cuerpo de ejemplo en una línea, si lo lleva, con la etiqueta delante.
 *
 * Sin ella, el JSON colgando bajo la descripción se lee como un resto pegado
 * por error. Con ella dice lo que es: lo que hay que mandar en el cuerpo.
 */
function cuerpo(ep) {
  return ep.body ? `\n      cuerpo JSON: ${JSON.stringify(ep.body)}` : '';
}

function bloque(titulo, filas) {
  if (!filas.length) return '';
  const lineas = filas
    .map((e) => `  ${e.method} ${e.ruta}\n      ${e.purpose}${cuerpo(e)}`)
    .join('\n\n');
  return `\n${titulo.toUpperCase()}\n\n${lineas}\n`;
}

/**
 * La instrucción completa, lista para pegar.
 *
 * @param {string} url         Dirección del servidor.
 * @param {object} manifest    Lo que devuelve `/bimnemo/memory/manifest`.
 * @param {boolean} protegida  Si la API pide clave.
 * @param {string} clave       La clave, cuando la haya.
 * @param {{id: string, nombre: string}} nemo  La memoria abierta.
 */
export function instruccionParaAgente(url, manifest, protegida, clave, nemo) {
  const ambitos = manifest.ambitos || {};
  const modos = manifest.retrieval_modes || {};
  const grupos = agruparPorAmbito(manifest.endpoints || [], nemo.id, ambitos);

  // La cabecera va arriba del todo: si falta, ninguna de las llamadas de abajo
  // funciona, y un 401 sin explicación es lo peor que le puede pasar a un
  // agente — no tiene forma de deducir qué le falta.
  const acceso = protegida
    ? `\nTODAS las llamadas necesitan esta cabecera:\n\n  X-API-Key: ${clave}\n`
    : '\nEsta memoria no pide credencial.\n';

  const cuerpoGrupos = grupos
    .map((g) => bloque(rotulo(g, nemo), g.filas))
    .join('');

  const listaModos = Object.entries(modos)
    .map(([nombre, para]) => `  ${nombre.padEnd(8)}${para}`)
    .join('\n');

  const puedeBorrar = grupos.some((g) => g.filas.some((f) => f.group === 'borrar'));

  return `Tienes acceso a BIMNEMO, una memoria de conocimiento con grafo que
corre en ${url}.

Estas instrucciones son para la memoria «${nemo.nombre}». Las rutas de abajo
ya apuntan a ella: úsalas tal cual, sin sustituir nada.

Antes de responder cualquier pregunta sobre los documentos del proyecto,
consulta la memoria en vez de improvisar. Usa el campo "context" de la
respuesta como tu fuente; si viene vacío, dilo.
${acceso}${cuerpoGrupos}
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
OTRAS MEMORIAS

  BIMNEMO guarda varias memorias separadas. Estas instrucciones son de
  «${nemo.nombre}». Para trabajar con otra, pide GET ${url}/bimnemo/nemos,
  que devuelve el identificador de cada una, y úsalo en lugar de
  ${nemo.id ? `"${nemo.id}"` : 'omitir el parámetro'}.

El descriptor completo, siempre al día, está en
${url}/bimnemo/memory/manifest`;
}

/**
 * El rótulo de un ámbito dentro de la instrucción.
 *
 * El de «esta memoria» lleva el nombre: un agente que lee «ESTA MEMORIA» sin
 * saber cuál es no tiene forma de comprobar que está donde debe.
 */
function rotulo(grupo, nemo) {
  return grupo.clave === 'esta'
    ? `${grupo.titulo} — ${nemo.nombre}`
    : grupo.titulo;
}
