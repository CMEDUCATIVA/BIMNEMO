/* ==========================================================================
   BIMNEMO — Cliente REST
   --------------------------------------------------------------------------
   Único punto desde el que se habla con el servidor. Ninguna vista construye
   una URL ni una cabecera por su cuenta: así la clave de API, el prefijo de
   proxy inverso y el tratamiento de errores viven en un solo sitio.
   ========================================================================== */

const API_KEY_STORAGE = 'bimnemo.apiKey';

/**
 * Raíz de la API.
 *
 * La UI se sirve desde `<prefijo>/bimnemo-app/`, así que la API está un nivel
 * por encima. Derivarlo de la ruta en curso — en vez de suponer la raíz del
 * dominio — es lo que hace que BIMNEMO funcione detrás de un proxy inverso con
 * prefijo, que es como LightRAG se despliega en la práctica.
 */
function apiRoot() {
  const path = window.location.pathname;
  const marker = '/bimnemo-app';
  const at = path.indexOf(marker);
  if (at === -1) return '';
  return path.slice(0, at);
}

export const ROOT = apiRoot();

export function getApiKey() {
  try {
    return window.localStorage.getItem(API_KEY_STORAGE) || '';
  } catch {
    // Modo privado o almacenamiento bloqueado: se sigue sin clave guardada.
    return '';
  }
}

export function setApiKey(value) {
  try {
    if (value) window.localStorage.setItem(API_KEY_STORAGE, value);
    else window.localStorage.removeItem(API_KEY_STORAGE);
  } catch {
    // No poder recordarla no impide usarla en esta sesión.
  }
}

function headers(extra = {}) {
  const out = { ...extra };
  const key = getApiKey();
  if (key) out['X-API-Key'] = key;
  return out;
}

/** Error de la API con su código, para que la vista pueda distinguir. */
export class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function toError(response) {
  let detail = `${response.status} ${response.statusText}`;
  try {
    const body = await response.json();
    if (body && body.detail) {
      detail =
        typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    }
  } catch {
    // Cuerpo no JSON: se queda el texto del estado, que ya dice algo.
  }
  return new ApiError(response.status, detail);
}

async function request(path, options = {}) {
  const response = await fetch(`${ROOT}${path}`, {
    ...options,
    headers: headers(options.headers),
  });
  if (!response.ok) throw await toError(response);
  return response.json();
}

function postJson(path, body) {
  return send('POST', path, body);
}

/**
 * Petición con método y cuerpo opcional.
 *
 * Existe porque no todo lo que manda cuerpo es un POST: borrar documentos es
 * un DELETE con lista de identificadores, y montarle su propio `fetch` a cada
 * caso es como se acaban duplicando las cabeceras y la clave de API.
 */
function send(method, path, body) {
  return request(path, {
    method,
    ...(body === undefined
      ? {}
      : {
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }),
  });
}

/** Sufijo `?nemo=` para los endpoints que aceptan memoria. */
const forNemo = (nemoId, extra = '') => {
  const params = new URLSearchParams(extra);
  if (nemoId) params.set('nemo', nemoId);
  const query = params.toString();
  return query ? `?${query}` : '';
};

/* --- Panel ---------------------------------------------------------------- */

export const getCatalog = () => request('/bimnemo/catalog');
export const getStats = (nemoId) => request(`/bimnemo/stats${forNemo(nemoId)}`);
export const getGraphStats = (nemoId) =>
  request(`/bimnemo/stats/graph${forNemo(nemoId)}`);

/** Subgrafo listo para dibujar: nodos, aristas y recuento por tipo. */
export const getGraph = (nemoId, { label = '*', depth = 3, max = 250 } = {}) =>
  request(
    `/bimnemo/graph${forNemo(nemoId, {
      label,
      max_depth: String(depth),
      max_nodes: String(max),
    })}`
  );

export const getEngine = (nemoId) => request(`/bimnemo/engine${forNemo(nemoId)}`);
export const getMemoryManifest = () => request('/bimnemo/memory/manifest');

/* --- Progreso y acciones sobre documentos --------------------------------- */

/** Qué está indexando ahora mismo esta memoria. */
export const getProgress = (nemoId) =>
  request(`/bimnemo/progress${forNemo(nemoId)}`);

/** Borra documentos indexados: su índice, su parte del grafo y su fichero. */
export const deleteDocuments = (nemoId, docIds) =>
  send('DELETE', `/bimnemo/documents${forNemo(nemoId)}`, {
    doc_ids: docIds,
    delete_file: true,
  });

/** Borra un fichero subido que todavía no ha llegado a indexarse. */
export const deleteStoredFile = (nemoId, name) =>
  send('DELETE', `/bimnemo/files${forNemo(nemoId, { name })}`);

/** Vuelve a encolar los documentos fallidos de esta memoria. */
export const retryFailed = (nemoId) =>
  send('POST', `/bimnemo/documents/retry${forNemo(nemoId)}`);

export const getFiles = (category, nemoId) =>
  request(
    `/bimnemo/files${forNemo(nemoId, category ? { category } : undefined)}`
  );

/* --- Motor y pipeline ----------------------------------------------------- */

export const getPipelineStatus = () => request('/documents/pipeline_status');
export const getHealth = () => request('/health');
export const getAppBuild = () => request('/bimnemo/app-build');

/* --- NEMOs: memorias separadas -------------------------------------------- */

export const listNemos = () => request('/bimnemo/nemos');
export const getNemosStats = () => request('/bimnemo/nemos/stats');
export const createNemo = (name) => postJson('/bimnemo/nemos', { name });

export const deleteNemo = (nemoId, confirmName, purgeFiles) =>
  request(`/bimnemo/nemos/${encodeURIComponent(nemoId)}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirm_name: confirmName, purge_files: purgeFiles }),
  });

/* --- Configuración de la IA ----------------------------------------------- */

export const getProviders = () => request('/bimnemo/providers');
export const getSettings = () => request('/bimnemo/settings');
export const saveSettings = (payload) => postJson('/bimnemo/settings', payload);
export const restartEngine = () => postJson('/bimnemo/restart', {});

/**
 * Exige —o deja de exigir— una clave para usar la API.
 *
 * Escribe `LIGHTRAG_API_KEY` en el `.env`; no cambia nada en caliente, porque
 * el guardia de las rutas se construye al arrancar. La respuesta pide
 * reinicio.
 */
/** ¿Hay una versión nueva publicada? */
export const getUpdateStatus = (force = false) =>
  request(`/bimnemo/update${force ? '?force=true' : ''}`);

/** Trae la versión publicada y reinicia. Responde en cuanto lanza el trabajo. */
export const applyUpdate = (discardLocalChanges = false) =>
  postJson('/bimnemo/update/apply', {
    discard_local_changes: discardLocalChanges,
  });

export const setAccess = (enabled, key) =>
  postJson('/bimnemo/access', { enabled, key: key || null });

/**
 * Centinela que el formulario manda cuando el usuario NO tocó el campo de la
 * clave de API. Debe coincidir con `envfile.UNCHANGED` del servidor: sin él,
 * guardar con el campo enmascarado borraría la clave ya guardada.
 */
export const API_KEY_UNCHANGED = '__BIMNEMO_SIN_CAMBIOS__';

/** Identidad del proceso que está respondiendo ahora mismo. */
export async function getBootId() {
  const build = await request('/bimnemo/app-build');
  return build.boot_id || null;
}

/**
 * Espera a que el motor vuelva tras un reinicio, y a que sea **otro**.
 *
 * Mirar `/health` no vale: la ruta de reinicio espera medio segundo antes de
 * matar el proceso —para que la respuesta salga por el socket— y durante ese
 * rato el motor moribundo contesta igual. Quien se fía de la primera
 * respuesta recarga contra un servidor que se está cerrando.
 *
 * Por eso se compara el `boot_id`: cambia con cada proceso nuevo.
 *
 * @param {string|null} anterior  El `boot_id` de antes de pedir el reinicio.
 * @param {(fase: string) => void} [alCambiarFase]  Para que quien espera pueda
 *        contar lo que está pasando. Las fases son: `cerrando` (todavía
 *        responde), `arrancando` (ya no responde) y `comprobando` (responde
 *        otra vez, falta ver si es otro).
 */
export async function waitForEngine(
  anterior = null,
  { timeoutMs = 90000, stepMs = 700, alCambiarFase = null } = {},
) {
  const deadline = Date.now() + timeoutMs;
  let fase = null;
  const anunciar = (nueva) => {
    if (nueva !== fase) {
      fase = nueva;
      if (alCambiarFase) alCambiarFase(nueva);
    }
  };

  // Si nadie dio un `boot_id` de referencia no hay nada que comparar, así que
  // la primera respuesta es lo único que se puede exigir. Peor, pero honesto.
  let seCayo = anterior === null;

  while (Date.now() < deadline) {
    let actual = null;
    try {
      actual = await getBootId();
    } catch {
      // Conexión rechazada: el proceso viejo ya murió. Esta es la señal de
      // que el reinicio va de verdad.
      seCayo = true;
      anunciar('arrancando');
    }

    if (actual !== null) {
      // Un `boot_id` distinto YA demuestra que es otro proceso. No hace falta
      // haber presenciado la caída.
      //
      // Exigirlo era un fallo: el motor está caído unos cuatro segundos y se
      // sondea cada 0,7 s, así que casi siempre se pilla — pero cuando no, la
      // espera se quedaba colgada hasta agotar el tiempo y decía «el motor no
      // volvió» con el motor perfectamente en pie y actualizado. Pasó en una
      // actualización que duró seis segundos y salió bien.
      if (anterior !== null && actual !== anterior) return true;

      // Sin referencia previa no hay con qué comparar, así que lo único
      // exigible es haber visto caer el proceso: la primera respuesta después
      // de eso es de uno nuevo.
      if (anterior === null && seCayo) return true;

      anunciar(seCayo ? 'comprobando' : 'cerrando');
    }

    await new Promise((resolve) => window.setTimeout(resolve, stepMs));
  }
  return false;
}

/* --- Ingesta -------------------------------------------------------------- */

/**
 * Sube un fichero por la vía oficial del motor (`POST /documents/upload`).
 * No se reimplementa nada: es el mismo endpoint que usa el WebUI de LightRAG.
 */
export async function uploadFile(file, nemoId) {
  if (nemoId) return uploadToNemo(file, nemoId);
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(`${ROOT}/documents/upload`, {
    method: 'POST',
    headers: headers(),
    body: form,
  });
  if (!response.ok) throw await toError(response);
  return response.json();
}

/** Sube a una NEMO concreta por su ruta espejo. */
export async function uploadToNemo(file, nemoId) {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(
    `${ROOT}/nemo/${encodeURIComponent(nemoId)}/documents/upload`,
    { method: 'POST', headers: headers(), body: form }
  );
  if (!response.ok) throw await toError(response);
  return response.json();
}

export const rememberText = (text, source) =>
  postJson('/bimnemo/memory/remember', { text, source });

export const scanDocuments = () => postJson('/documents/scan', {});

/* --- Consulta ------------------------------------------------------------- */

export const askMemory = (query, mode, extra = {}) =>
  postJson('/query', { query, mode, ...extra });

export const searchMemory = (query, mode, extra = {}) =>
  postJson('/bimnemo/memory/search', { query, mode, ...extra });

/** Pregunta a una NEMO concreta. */
export const askNemo = (nemoId, query, mode, extra = {}) =>
  postJson(`/nemo/${encodeURIComponent(nemoId)}/query`, { query, mode, ...extra });

/** Recupera contexto de una NEMO concreta, sin generar. */
export const searchNemo = (nemoId, query, mode, extra = {}) =>
  postJson(`/nemo/${encodeURIComponent(nemoId)}/memory/search`, {
    query,
    mode,
    ...extra,
  });

/** Pregunta a VARIAS memorias y recibe una sola respuesta con sus fuentes. */
export const askAllNemos = (query, mode, extra = {}) =>
  postJson('/bimnemo/memory/ask-all', { query, mode, ...extra });

/** Recupera contexto de varias memorias, etiquetado por memoria. */
export const searchAllNemos = (query, mode, extra = {}) =>
  postJson('/bimnemo/memory/search-all', { query, mode, ...extra });
