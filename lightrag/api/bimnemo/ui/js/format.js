/* ==========================================================================
   BIMNEMO — Formato de cifras, fechas y texto
   Todo lo que se enseña al usuario pasa por aquí, para que un mismo dato se
   vea igual en el panel, en la tabla y en la ficha del motor.
   ========================================================================== */

const LOCALE = 'es-ES';

/**
 * Bytes en unidades legibles, base 1024.
 *
 * Se usa base 1024 (KB = 1024 B) porque es lo que enseña el explorador de
 * Windows, que es contra lo que el usuario va a comparar la cifra.
 */
export function bytes(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return '—';
  if (n === 0) return '0 B';

  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const exponent = Math.min(
    Math.floor(Math.log(n) / Math.log(1024)),
    units.length - 1
  );
  const scaled = n / 1024 ** exponent;
  // Un decimal a partir de KB; los bytes sueltos siempre enteros.
  const decimals = exponent === 0 ? 0 : scaled >= 100 ? 0 : 1;
  return `${scaled.toFixed(decimals)} ${units[exponent]}`;
}

/** Entero con separador de millar español. */
export function count(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  return n.toLocaleString(LOCALE);
}

/** Cifra grande abreviada: 12.400 -> «12,4 K». Para tarjetas estrechas. */
export function compact(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  if (Math.abs(n) < 1000) return count(n);
  return new Intl.NumberFormat(LOCALE, {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(n);
}

/** Porcentaje entero, sin decimales engañosos. */
export function percent(part, total) {
  const p = Number(part);
  const t = Number(total);
  if (!Number.isFinite(p) || !Number.isFinite(t) || t <= 0) return 0;
  return (p / t) * 100;
}

export function percentLabel(part, total) {
  const value = percent(part, total);
  if (value === 0) return '0%';
  // Por debajo del 1% se dice «<1%» en vez de «0%»: no es lo mismo nada que
  // poco, y en un reparto de almacenamiento esa diferencia importa.
  if (value < 1) return '<1%';
  return `${Math.round(value)}%`;
}

/** Marca de tiempo Unix en segundos -> fecha y hora local corta. */
export function timestamp(seconds) {
  const n = Number(seconds);
  if (!Number.isFinite(n) || n <= 0) return '—';
  return new Date(n * 1000).toLocaleString(LOCALE, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Fecha ISO que llega del motor -> fecha y hora local corta. */
export function isoDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(LOCALE, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const STATUS_LABELS = {
  pending: 'En cola',
  parsing: 'Extrayendo',
  analyzing: 'Analizando',
  processing: 'Indexando',
  preprocessed: 'Preprocesado',
  processed: 'En memoria',
  failed: 'Fallido',
  // No es un estado del motor: lo pone la pantalla mientras espera a que el
  // borrado termine, para que la fila no finja que no está pasando nada.
  deleting: 'Borrando…',
};

/** Estado del motor en palabras que signifiquen algo para quien mira. */
export function statusLabel(status) {
  if (!status) return 'Sin indexar';
  return STATUS_LABELS[status] || status;
}

/**
 * Escapa texto para insertarlo en HTML.
 *
 * Todo lo que venga del servidor o del usuario —nombres de fichero, respuestas
 * del modelo, mensajes de error— pasa por aquí antes de tocar innerHTML. Un
 * nombre de fichero puede contener `<` perfectamente.
 */
export function escape(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
