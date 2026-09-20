/* ==========================================================================
   BIMNEMO — Idioma de la memoria
   --------------------------------------------------------------------------
   En qué idioma escribe el motor las entidades al indexar y las respuestas
   del chat. Vive aparte de la configuración de proveedores porque no es un
   proveedor y porque se comporta distinto: es el único ajuste de esa pantalla
   que no se puede rectificar sin reindexar.
   ========================================================================== */

import { icon } from './icons.js';
import { escape } from './format.js';

//: Idiomas que se ofrecen. El campo admite cualquiera que el modelo entienda
//: —va literal al prompt— pero una lista corta evita la errata que arruina
//: una indexación entera.
const IDIOMAS = [
  { value: 'Spanish', label: 'Español' },
  { value: 'English', label: 'Inglés' },
  { value: 'Portuguese', label: 'Portugués' },
  { value: 'French', label: 'Francés' },
  { value: 'German', label: 'Alemán' },
  { value: 'Italian', label: 'Italiano' },
  { value: 'Chinese', label: 'Chino' },
];

/**
 * Tarjeta del idioma de extracción.
 *
 * Va aparte de los tres bloques de proveedor porque no es un proveedor: es el
 * idioma en el que el motor **escribe** las entidades al indexar y en el que
 * responde el chat. Y va con aviso, porque es el único ajuste de esta pantalla
 * que no se puede rectificar sin reindexar: lo ya extraído conserva el idioma
 * con el que se extrajo.
 */
export function languageCard(actual) {
  const opciones = IDIOMAS.map(
    (i) =>
      `<option value="${escape(i.value)}"${i.value === actual ? ' selected' : ''}>${escape(i.label)}</option>`
  ).join('');
  const suelto = IDIOMAS.some((i) => i.value === actual)
    ? ''
    : `<option value="${escape(actual)}" selected>${escape(actual)}</option>`;

  return `
    <div class="card" data-section="language">
      <div class="card__head">
        <span class="card__title">
          <span data-icon="book-open" data-icon-size="14"></span>
          Idioma de la memoria
        </span>
        <span class="card__hint">En qué idioma se escriben las entidades y las respuestas</span>
      </div>
      <div class="card__body">
        <div class="cfggrid">
          <div class="field">
            <label class="field__label" for="cfg-language">Idioma</label>
            <span class="selectwrap">
              <select class="select" id="cfg-language" data-role="language">
                ${suelto}${opciones}
              </select>
            </span>
            <span class="field__help">
              Se guarda como <code>SUMMARY_LANGUAGE</code>.
            </span>
          </div>
        </div>
        <div class="notice notice--warn">
          <span class="notice__icon">${icon('triangle-alert', 13)}</span>
          <span>
            Cambiarlo <strong>no reescribe lo ya indexado</strong>: las
            entidades guardadas conservan el idioma con el que se extrajeron.
            Para unificarlo hay que vaciar la memoria y volver a indexar.
          </span>
        </div>
      </div>
    </div>`;
}

/** El idioma elegido en el formulario, o null si la tarjeta no está pintada. */
export function readLanguage() {
  return document.getElementById('cfg-language')?.value || null;
}

/** Avisa de los cambios del selector; la tarjeta no está dentro de un bloque. */
export function onLanguageChange(handler) {
  document.getElementById('cfg-language')?.addEventListener('change', handler);
}
