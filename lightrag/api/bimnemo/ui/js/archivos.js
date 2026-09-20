/* ==========================================================================
   BIMNEMO — Vista Archivos
   Subida (botón y arrastre), filtros por categoría y tabla de almacenados.
   ========================================================================== */

import { getCatalog, getFiles, scanDocuments, uploadFile } from './api.js';
import { currentNemo, currentNemoName } from './nemo.js';
import { icon } from './icons.js';
import { avisar } from './dialogo.js';
import {
  mountAcciones,
  olvidarBorrados,
  rowActions,
  seEstaBorrando,
} from './archivos-acciones.js';
import { repintarBarras, watchProgress } from './archivos-progreso.js';
import { bytes, count, escape, statusLabel, timestamp } from './format.js';

let catalog = null;
let activeCategory = null;
let onChanged = () => {};

/* --- Catálogo ------------------------------------------------------------- */

async function ensureCatalog() {
  if (!catalog) catalog = await getCatalog();
  return catalog;
}

function categoryOf(key) {
  return (
    catalog?.categories.find((c) => c.key === key) || {
      key,
      label: 'Otros',
      icon: 'file',
      color: 'slate',
    }
  );
}

/* --- Zona de arrastre ----------------------------------------------------- */

function describeAccepted() {
  const hint = document.getElementById('dropzone-hint');
  const accepted = catalog?.ingestible_extensions || [];
  if (!accepted.length) {
    hint.textContent =
      'El motor no declara ningún formato admitido. Revisa la configuración de parsers antes de subir nada.';
    return;
  }
  // Se enseñan TODOS, no los primeros dieciocho.
  //
  // Recortar la lista con «y 23 más» obligaba a adivinar: quien quiere saber
  // si su .pptx entra no puede comprobarlo, y el dato está a mano — el motor
  // lo deriva vivo del registro de parsers. La lista va en su propio bloque
  // para que no empuje al resto de la zona.
  hint.innerHTML =
    `<span class="dropzone__count">Admite ${accepted.length} formatos</span>` +
    `<span class="dropzone__formats">${accepted.map(escape).join(' · ')}</span>`;
}

/* --- Cola de subida ------------------------------------------------------- */

const queue = [];

function renderQueue() {
  const card = document.getElementById('queue-card');
  const list = document.getElementById('queue');
  card.hidden = queue.length === 0;

  const symbols = { pending: 'inbox', sending: 'loader-circle', done: 'check', error: 'x' };
  const words = {
    pending: 'En cola',
    sending: 'Enviando…',
    done: 'Subido',
    error: 'Error',
  };

  list.innerHTML = queue
    .map(
      (item) => `
      <div class="queueitem" data-state="${escape(item.state)}">
        <span>${icon(symbols[item.state], 13)}</span>
        <span class="queueitem__name truncate" title="${escape(item.name)}">${escape(item.name)}</span>
        <span class="queueitem__state">${escape(item.detail || words[item.state])}</span>
      </div>`
    )
    .join('');
}

/** Estados en los que el motor ya no va a hacer nada más con un documento. */
const TERMINADOS = new Set(['processed', 'failed']);

/**
 * Quita de «Subidas» lo que ya no tiene nada que contar.
 *
 * Una línea de esa tarjeta describe **un fichero que todavía no ha llegado a
 * la memoria**. En cuanto llega —o falla— la tabla de abajo lo cuenta mejor:
 * con su estado, sus fragmentos y su fecha. Dejarla puesta no solo estorba:
 * sigue diciendo «Encolado» justo encima de una fila que dice «En memoria».
 *
 * **Las de error de subida se quedan.** Ésas nunca llegaron al motor, así que
 * no hay ninguna fila abajo que las cuente; irse solas sería tragarse el
 * fallo antes de que nadie lo lea. Se van con «Limpiar», que es cuando el
 * usuario ha decidido que ya las vio.
 *
 * @param {Array<{name: string, status: string}>} rows  Los ficheros de la
 *        memoria tal y como acaba de devolverlos el servidor.
 */
function depurarCola(rows) {
  if (!queue.length) return;
  const estados = new Map(rows.map((r) => [r.name, r.status || '']));

  const quedan = queue.filter((item) => {
    if (item.state !== 'done') return true;
    // Ya no está en la lista: se borró. Describir lo que no existe no ayuda.
    if (!estados.has(item.name)) return false;
    return !TERMINADOS.has(estados.get(item.name));
  });

  if (quedan.length === queue.length) return;
  queue.length = 0;
  queue.push(...quedan);
  renderQueue();
}

/**
 * Sube los ficheros de uno en uno.
 *
 * En serie a propósito: la ingesta de LightRAG ya paraleliza por su cuenta
 * (`max_parallel_insert`), y disparar veinte subidas a la vez desde el
 * navegador solo consigue saturar el servidor y perder el orden de la cola.
 */
/**
 * Estados con los que el servidor dice que sí.
 *
 * No es solo `success`: la ruta general responde así, pero la de una NEMO
 * devuelve `accepted` cuando encola el texto y `stored` cuando guarda un
 * binario para que lo recoja el parser. Comparando solo con `success`, una
 * subida correcta salía en rojo y con cara de error.
 */
const ACEPTADOS = new Set(['success', 'accepted', 'stored']);

/**
 * Lo que se acaba de subir, con la hora.
 *
 * Un archivo existe en disco antes de que el motor le cree su estado, y
 * durante ese par de segundos la fila decía «Sin indexar» — justo el mensaje
 * que ya desconcertó una vez. Mientras el nombre esté aquí dentro, la fila se
 * pinta como «En cola». Pasado el plazo, si sigue sin estado, es que de verdad
 * no se indexó y vuelve a decir la verdad.
 */
const recienSubidos = new Map();
const GRACIA = 30000;

function marcarSubido(nombre) {
  recienSubidos.set(nombre, Date.now());
}

function esperaTurno(nombre) {
  const t = recienSubidos.get(nombre);
  if (t === undefined) return false;
  if (Date.now() - t > GRACIA) {
    recienSubidos.delete(nombre);
    return false;
  }
  return true;
}

async function pushFiles(fileList) {
  const incoming = Array.from(fileList);
  if (!incoming.length) return;

  const added = incoming.map((file) => ({
    name: file.name,
    file,
    state: 'pending',
    detail: '',
  }));
  queue.push(...added);
  renderQueue();

  // Se despierta al vigilante para que la barra salga ya, sin esperar al
  // siguiente sondeo en reposo.
  watchProgress();

  for (const item of added) {
    item.state = 'sending';
    renderQueue();
    try {
      const result = await uploadFile(item.file, currentNemo());
      const status = String(result?.status || '').toLowerCase();
      if (status === 'duplicated') {
        item.state = 'done';
        item.detail = 'Ya estaba';
      } else if (status && !ACEPTADOS.has(status)) {
        // El endpoint responde 200 con un estado de rechazo; no es un fallo
        // de red, así que se muestra su mensaje tal cual.
        item.state = 'error';
        item.detail = result?.message || status;
      } else {
        item.state = 'done';
        item.detail = 'Encolado';
        // Aceptado por el servidor: su fila ya puede decir «En cola» aunque el
        // motor tarde un segundo en crearle el estado.
        marcarSubido(item.name);
      }
    } catch (error) {
      item.state = 'error';
      item.detail = error.detail || error.message;
    }
    renderQueue();
  }

  await refreshFiles();
  onChanged();
}

/* --- Filtros -------------------------------------------------------------- */

function renderFilters(rows) {
  const counts = new Map();
  for (const row of rows) {
    counts.set(row.category, (counts.get(row.category) || 0) + 1);
  }

  const chips = [
    `<button type="button" class="chip" data-filter=""
       aria-pressed="${activeCategory === null}">
       <span>Todos</span><span class="chip__count">${rows.length}</span>
     </button>`,
  ];

  for (const category of catalog?.categories || []) {
    const n = counts.get(category.key) || 0;
    if (!n) continue;
    chips.push(
      `<button type="button" class="chip" data-filter="${escape(category.key)}"
         data-color="${escape(category.color)}"
         aria-pressed="${activeCategory === category.key}">
         ${icon(category.icon, 12)}
         <span>${escape(category.label)}</span>
         <span class="chip__count">${n}</span>
       </button>`
    );
  }

  const other = counts.get('other') || 0;
  if (other) {
    chips.push(
      `<button type="button" class="chip" data-filter="other"
         aria-pressed="${activeCategory === 'other'}">
         <span>Otros</span><span class="chip__count">${other}</span>
       </button>`
    );
  }

  document.getElementById('files-filters').innerHTML = chips.join('');
}

/* --- Tabla ---------------------------------------------------------------- */

function renderTable(rows) {
  const body = document.getElementById('files-body');
  const empty = document.getElementById('files-empty');

  const visible = activeCategory
    ? rows.filter((r) => r.category === activeCategory)
    : rows;

  document.getElementById('files-hint').textContent =
    `${currentNemoName()} · ${count(visible.length)} de ${count(rows.length)}`;

  if (!visible.length) {
    body.innerHTML = '';
    empty.innerHTML = `
      <div class="empty">
        <span class="empty__icon">${icon('inbox', 28)}</span>
        <span class="empty__title">${rows.length ? 'Nada en esta categoría' : 'Todavía no hay archivos'}</span>
        <span class="empty__text">${
          rows.length
            ? 'Prueba con otro filtro.'
            : 'Arrastra documentos a la zona de arriba y entrarán en la memoria.'
        }</span>
      </div>`;
    return;
  }

  empty.innerHTML = '';
  body.innerHTML = visible
    .map((row) => {
      const category = categoryOf(row.category);
      // «Borrando» gana a todo lo demás: es lo último que se pidió sobre esa
      // fila y lo único que explica por qué sigue ahí.
      const status = seEstaBorrando(row.name)
        ? 'deleting'
        : row.status || (esperaTurno(row.name) ? 'pending' : 'none');
      return `
      <tr>
        <td>
          <span class="table__file" data-color="${escape(category.color)}">
            <span class="table__file-icon">${icon(category.icon, 15)}</span>
            <span class="table__name truncate" title="${escape(row.name)}">${escape(row.name)}</span>
          </span>
        </td>
        <td>
          <span class="badge badge--cat" data-color="${escape(category.color)}">
            ${escape(category.label)}
          </span>
        </td>
        <td><span class="typerow__ext">${escape(row.type)}</span></td>
        <td class="table__num">${escape(bytes(row.size_bytes))}</td>
        <td>
          <span class="badge" data-status="${escape(status)}"
                title="${escape(row.error_msg || '')}">
            <span class="badge__dot"></span>${escape(statusLabel(status))}
          </span>
          ${barraDeFila(status)}
        </td>
        <td class="table__num">${row.chunks_count == null ? '—' : escape(count(row.chunks_count))}</td>
        <td class="card__hint">${escape(timestamp(row.modified_at))}</td>
        ${rowActions(row)}
      </tr>`;
    })
    .join('');

  // Las barras acaban de nacer vacías: se les pone el avance ya, sin esperar
  // al siguiente sondeo.
  repintarBarras();
}

/**
 * La barra de esa fila, o nada.
 *
 * Solo la llevan las filas con trabajo por delante. Una fila terminada no
 * necesita barra: su etiqueta ya lo dice, y una barra al 100 % permanente es
 * ruido. El ancho lo escribe el vigilante en cada sondeo (`archivos-progreso`),
 * porque la tabla no puede repintarse cada dos segundos sin perder el hover y
 * el foco de quien está mirando.
 */
const EN_CURSO = new Set([
  'pending',
  'parsing',
  'analyzing',
  'processing',
  'deleting',
]);

function barraDeFila(status) {
  if (!EN_CURSO.has(status)) return '';
  return `
    <span class="estado-barra" data-estado="${escape(status)}" data-modo="espera">
      <span class="estado-barra__track"><span class="estado-barra__fill"></span></span>
      <span class="estado-barra__pct tabular"></span>
    </span>`;
}

/* --- Refresco ------------------------------------------------------------- */

let lastRows = [];

async function refreshFiles() {
  const payload = await getFiles(null, currentNemo());
  lastRows = payload.files;
  olvidarBorrados(lastRows.map((f) => f.name));
  // Con los estados ya en la mano: no hace falta un sondeo aparte.
  depurarCola(lastRows);
  renderFilters(lastRows);
  renderTable(lastRows);
  return payload;
}

/* --- Montaje -------------------------------------------------------------- */

/**
 * Engancha la vista de Archivos.
 *
 * Se llama UNA vez al arrancar, no en cada cambio de pestaña: los escuchadores
 * se registran sobre elementos que viven toda la sesión, de modo que navegar
 * entre vistas no los descarga ni los duplica.
 *
 * @param {() => void} notifyChanged  Avisa a la aplicación de que el contenido
 *        cambió, para que el panel se vuelva a pintar.
 */
export async function mountArchivos(notifyChanged) {
  onChanged = notifyChanged;

  // Las acciones de fila se montan una vez: la tabla se repinta entera en
  // cada refresco, así que el escuchador va delegado en su cuerpo.
  mountAcciones(async () => {
    await refreshFiles();
    onChanged();
  });


  const input = document.getElementById('file-input');
  const dropzone = document.getElementById('dropzone');

  document.getElementById('btn-pick').addEventListener('click', () => input.click());

  input.addEventListener('change', () => {
    pushFiles(input.files);
    input.value = ''; // permite volver a elegir el mismo fichero
  });

  // Arrastre. Hay que cancelar dragover o el navegador abre el fichero.
  ['dragenter', 'dragover'].forEach((type) =>
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.add('is-over');
    })
  );
  ['dragleave', 'drop'].forEach((type) =>
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      dropzone.classList.remove('is-over');
    })
  );
  dropzone.addEventListener('drop', (event) => {
    if (event.dataTransfer?.files?.length) pushFiles(event.dataTransfer.files);
  });

  document.getElementById('btn-clear-queue').addEventListener('click', () => {
    queue.length = 0;
    renderQueue();
  });

  document.getElementById('btn-scan').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await scanDocuments();
      await refreshFiles();
      onChanged();
    } catch (error) {
      avisar(
        'No se pudo reindexar',
        error.detail || error.message,
        true
      );
    } finally {
      button.disabled = false;
    }
  });

  // Un escuchador para todos los filtros, delegado en el contenedor.
  document.getElementById('files-filters').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-filter]');
    if (!chip) return;
    activeCategory = chip.dataset.filter || null;
    renderFilters(lastRows);
    renderTable(lastRows);
  });

  await ensureCatalog();
  describeAccepted();
  await refreshFiles();
}

/** Refresca desde fuera (el botón global de actualizar). */
export async function reloadArchivos() {
  await refreshFiles();
}

/** Abre Archivos ya filtrado por una categoría (lo usa el panel). */
export function filterByCategory(key) {
  activeCategory = key || null;
  renderFilters(lastRows);
  renderTable(lastRows);
}
