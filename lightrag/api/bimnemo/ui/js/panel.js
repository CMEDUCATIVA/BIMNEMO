/* ==========================================================================
   BIMNEMO — Vista Panel
   Tarjetas de cifra, reparto de almacenamiento, categorías, tipos y grafo.
   ========================================================================== */

import { getNemosStats, getStats } from './api.js';
import { currentNemo, renderNemoBreakdown } from './nemo.js';
import { icon } from './icons.js';
import { bytes, compact, count, escape, percent, percentLabel } from './format.js';

/** Categorías con al menos un fichero, de mayor a menor peso. */
function occupied(categories) {
  return categories
    .filter((c) => c.files > 0)
    .sort((a, b) => b.size_bytes - a.size_bytes);
}

/**
 * Tarjetas de cifra del panel.
 *
 * Suman TODAS las memorias, que es lo que el usuario pidió ver «en general».
 * La última tarjeta es la excepción y se dice: los documentos indexados son
 * los de la memoria activa, porque contar los de una memoria dormida obligaría
 * a abrirla — seis grafos en RAM por pintar una cifra.
 */
function renderTiles(agregado, stats) {
  const { memory } = stats;
  const t = agregado.total;
  const tiles = [
    {
      icon: 'file-text',
      label: 'Archivos',
      value: count(t.total_files),
      note: `En ${t.nemos} memoria${t.nemos === 1 ? '' : 's'}`,
    },
    {
      icon: 'hard-drive',
      label: 'Total almacenado',
      value: bytes(t.total_bytes),
      note: 'Bytes reales en disco',
    },
    {
      icon: 'layers',
      label: 'Categorías',
      value: `${t.categories_in_use} / ${t.categories_available}`,
      note: 'En uso sobre el catálogo',
    },
    {
      icon: 'database',
      label: 'En esta memoria',
      value: count(memory.total_documents),
      note: `${compact(memory.total_chunks)} fragmentos indexados`,
    },
  ];

  document.getElementById('panel-tiles').innerHTML = tiles
    .map(
      (t) => `
      <div class="tile">
        <div class="tile__label">${icon(t.icon, 14)}<span>${escape(t.label)}</span></div>
        <div class="tile__value">${escape(t.value)}</div>
        <div class="tile__note">${escape(t.note)}</div>
      </div>`
    )
    .join('');
}

function renderMeter(target, categories, total) {
  const slices = occupied(categories);
  if (!slices.length || total <= 0) {
    // Sin datos se deja la pista vacía: una barra a cero es más honesta que
    // una barra completa de color neutro, que parece "lleno".
    target.innerHTML = '';
    return;
  }
  target.innerHTML = slices
    .map((c) => {
      const width = percent(c.size_bytes, total);
      return `<span class="meter__slice" data-color="${escape(c.color)}"
        title="${escape(c.label)}: ${escape(bytes(c.size_bytes))}"
        style="width:${width}%"></span>`;
    })
    .join('');
}

function renderLegend(categories, total) {
  const slices = occupied(categories);
  document.getElementById('panel-legend').innerHTML = slices.length
    ? slices
        .map(
          (c) => `
        <span class="legend__item" data-color="${escape(c.color)}">
          <span class="legend__dot"></span>
          <span>${escape(c.label)}</span>
          <span class="legend__pct">${escape(percentLabel(c.size_bytes, total))}</span>
        </span>`
        )
        .join('')
    : '<span class="legend__item">Todavía no hay nada almacenado.</span>';
}

function renderCategories(categories, total, onPick) {
  const grid = document.getElementById('panel-categories');
  grid.innerHTML = categories
    .map(
      (c) => `
      <button type="button" class="catcard${c.files ? '' : ' is-empty'}"
              data-color="${escape(c.color)}" data-category="${escape(c.key)}">
        <span class="catcard__head">
          <span class="catcard__icon">${icon(c.icon, 15)}</span>
          <span class="catcard__name truncate" title="${escape(c.label)}">${escape(c.label)}</span>
        </span>
        <span class="catcard__count">
          <span class="catcard__number">${escape(count(c.files))}</span>
          <span class="catcard__unit">archivo${c.files === 1 ? '' : 's'}</span>
        </span>
        <span class="catcard__size">${escape(bytes(c.size_bytes))}</span>
        <span class="catcard__foot">
          <span class="meter meter--thin" data-color="${escape(c.color)}">
            <span class="meter__slice" style="width:${percent(c.size_bytes, total)}%"></span>
          </span>
          <span class="catcard__pct">${escape(percentLabel(c.size_bytes, total))}</span>
        </span>
      </button>`
    )
    .join('');

  // Un solo escuchador en la rejilla, no uno por tarjeta.
  grid.onclick = (event) => {
    const card = event.target.closest('[data-category]');
    if (card) onPick(card.dataset.category);
  };
}

function renderTypes(types, total) {
  const list = document.getElementById('panel-types');
  document.getElementById('panel-types-hint').textContent =
    types.length ? `${types.length} tipos` : '';

  if (!types.length) {
    list.innerHTML =
      '<p class="card__hint">Todavía no hay archivos que clasificar.</p>';
    return;
  }

  list.innerHTML = types
    .map(
      (t) => `
      <div class="typerow">
        <span class="typerow__ext" title="${escape(t.type)}">${escape(t.type)}</span>
        <span class="meter meter--thin" data-color="slate">
          <span class="meter__slice" style="width:${percent(t.size_bytes, total)}%"></span>
        </span>
        <span class="typerow__size">${escape(count(t.files))} · ${escape(bytes(t.size_bytes))}</span>
      </div>`
    )
    .join('');
}

/**
 * Atajos del carril: solo las categorías que tienen algo.
 *
 * Aquí no se pintan las vacías — al contrario que en la rejilla del panel,
 * donde las ocho ranuras cuentan para el «N / 8». El carril es para saltar a
 * lo que existe, y una categoría vacía no lleva a ninguna parte.
 */
function renderRailCategories(categories, onPick) {
  const box = document.getElementById('rail-categories');
  const used = occupied(categories);

  if (!used.length) {
    box.innerHTML = '<span class="card__hint">Sin archivos todavía.</span>';
    return;
  }

  box.innerHTML = used
    .map(
      (c) => `
      <button type="button" class="chip" data-color="${escape(c.color)}"
              data-category="${escape(c.key)}" title="${escape(bytes(c.size_bytes))}">
        ${icon(c.icon, 12)}
        <span>${escape(c.label)}</span>
        <span class="chip__count">${escape(count(c.files))}</span>
      </button>`
    )
    .join('');

  box.onclick = (event) => {
    const chip = event.target.closest('[data-category]');
    if (chip) onPick(chip.dataset.category);
  };
}

function renderAlerts(stats) {
  const box = document.getElementById('panel-alerts');
  const alerts = [];

  if (stats.storage.scan_error) {
    alerts.push({
      kind: 'error',
      icon: 'triangle-alert',
      text: `No se pudo recorrer el directorio de entrada: ${stats.storage.scan_error}`,
    });
  }
  if (stats.storage.unreadable_files > 0) {
    alerts.push({
      kind: 'warn',
      icon: 'triangle-alert',
      text: `${stats.storage.unreadable_files} archivo(s) no se pudieron leer y no cuentan en el total.`,
    });
  }
  if (stats.memory.documents_error) {
    alerts.push({
      kind: 'error',
      icon: 'triangle-alert',
      text: `El estado de los documentos no está disponible: ${stats.memory.documents_error}`,
    });
  }
  const failed = stats.memory.by_status?.failed || 0;
  if (failed > 0) {
    // El motivo va DENTRO del aviso, no en un tooltip de la tabla de
    // archivos. Un fallo de indexado casi nunca es culpa del documento: es la
    // clave, el crédito de la cuenta o el modelo. Esconder eso detrás de un
    // «pasa el ratón por encima» deja al usuario sin saber qué arreglar.
    const motivo = stats.memory.failed_reason;
    alerts.push({
      kind: 'error',
      icon: 'triangle-alert',
      text:
        `${failed} documento(s) fallaron al indexarse` +
        (motivo ? `: ${motivo}` : '.') +
        ' No se reintentan solos: arregla la causa y usa «Reindexar pendientes» en Archivos.',
    });
  }

  box.innerHTML = alerts
    .map(
      (a) => `
      <div class="notice notice--${a.kind}">
        <span class="notice__icon">${icon(a.icon, 14)}</span>
        <span>${escape(a.text)}</span>
      </div>`
    )
    .join('');
}

/**
 * Pinta el panel entero.
 *
 * El grafo va aparte, en `grafo.js`: leerlo y dibujarlo es caro y el resto de
 * las cifras no deben esperarlo.
 *
 * @param {(category: string) => void} onPickCategory  Qué hacer al pulsar una
 *        tarjeta de categoría (lo resuelve app.js: ir a Archivos filtrado).
 * @returns {object} Las estadísticas, para que quien llama las reutilice.
 */
export async function renderPanel(onPickCategory, onPickNemo) {
  // Dos lecturas con propósitos distintos: el agregado de TODAS las memorias
  // para las cifras generales, y el detalle de la activa para sus categorías
  // y tipos. Mezclarlas daría un panel que no se sabe de qué habla.
  const [agregado, stats] = await Promise.all([
    getNemosStats(),
    getStats(currentNemo()),
  ]);
  const { storage } = stats;
  const total = agregado.total.total_bytes;

  renderAlerts(stats);
  renderTiles(agregado, stats);
  renderNemoBreakdown(agregado.nemos, total, onPickNemo);

  document.getElementById('panel-storage-total').textContent = bytes(total);
  renderMeter(document.getElementById('panel-meter'), agregado.total.categories, total);
  renderLegend(agregado.total.categories, total);
  renderCategories(agregado.total.categories, total, onPickCategory);
  // Los tipos sí son de la memoria activa: es el detalle de dónde estás.
  renderTypes(storage.types, storage.total_bytes);

  document.getElementById('panel-cat-hint').textContent =
    `${agregado.total.categories_in_use} de ${agregado.total.categories_available} en uso`;

  // Carril lateral: el mismo dato, resumido.
  document.getElementById('rail-storage').textContent = bytes(total);
  document.getElementById('rail-files').textContent =
    `${count(agregado.total.total_files)} archivo${agregado.total.total_files === 1 ? '' : 's'}`;
  renderMeter(document.getElementById('rail-meter'), agregado.total.categories, total);
  renderRailCategories(agregado.total.categories, onPickCategory);
  // El contador del carril es de la memoria activa: es a lo que lleva pulsar.
  document.getElementById('nav-files-count').textContent = count(storage.total_files);

  return stats;
}
