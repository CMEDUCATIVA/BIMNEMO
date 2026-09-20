/* ==========================================================================
   BIMNEMO — Combo: campo de texto con sugerencias
   --------------------------------------------------------------------------
   Sustituye a `<input list>` + `<datalist>`, que no sirve aquí por dos
   motivos, los dos visibles en pantalla:

   1. **No se puede dar estilo.** El desplegable y su flecha los pinta el
      navegador con su propio aspecto; desentonan junto a los demás campos y
      cambian de una máquina a otra.
   2. **No se puede acotar por contexto.** Un `<datalist>` es una lista fija
      atada al `list=` del campo. Con un solo listado para todos los
      proveedores, elegir OpenAI sugería `openai/gpt-4o-mini`, que es de
      OpenRouter.

   Este componente resuelve ambos: las opciones se piden **en el momento de
   abrir** (`getOptions()`), así siempre son las del proveedor seleccionado, y
   el marcado es nuestro.

   Escribir a mano sigue siendo válido y es el caso principal: los catálogos
   de modelos cambian cada pocas semanas y la lista es una ayuda, no una
   validación.
   ========================================================================== */

import { escape } from './format.js';

/**
 * Convierte un `<input>` en un combo con sugerencias.
 *
 * @param {HTMLInputElement} input   El campo de texto.
 * @param {() => string[]} getOptions Devuelve las sugerencias vigentes. Se
 *        llama al abrir, no al montar: por eso refleja el proveedor actual.
 * @returns {{destroy: () => void}}
 */
export function attachCombo(input, getOptions) {
  const wrapper = input.closest('.combo');
  if (!wrapper) return { destroy() {} };

  const list = wrapper.querySelector('.combo__list');
  const toggle = wrapper.querySelector('.combo__toggle');
  let active = -1;
  let visible = [];
  // Al elegir una opción se emite un evento `input` para que la marca de
  // cambios sin guardar se entere. Ese evento vuelve a nuestro propio
  // manejador, que abriría la lista otra vez justo después de cerrarla. La
  // bandera distingue «lo ha escrito una persona» de «lo hemos puesto
  // nosotros».
  let choosing = false;

  const isOpen = () => !list.hidden;

  function render(filter) {
    const needle = (filter || '').trim().toLowerCase();
    const all = getOptions() || [];
    visible = needle
      ? all.filter((o) => o.toLowerCase().includes(needle))
      : all.slice();

    if (!visible.length) {
      list.innerHTML = `<li class="combo__empty" role="presentation">${
        all.length ? 'Ninguna sugerencia coincide' : 'Sin sugerencias; escribe el nombre'
      }</li>`;
      return;
    }

    list.innerHTML = visible
      .map(
        (option, index) =>
          `<li class="combo__option" role="option" id="${input.id}-opt-${index}" ` +
          `aria-selected="${option === input.value}" data-value="${escape(option)}">` +
          `${escape(option)}</li>`
      )
      .join('');
  }

  function setActive(index) {
    const options = [...list.querySelectorAll('.combo__option')];
    if (!options.length) return;

    active = (index + options.length) % options.length;
    options.forEach((el, i) => el.classList.toggle('is-active', i === active));
    options[active].scrollIntoView({ block: 'nearest' });
    input.setAttribute('aria-activedescendant', options[active].id);
  }

  function open(filter) {
    render(filter);
    list.hidden = false;
    wrapper.classList.add('is-open');
    input.setAttribute('aria-expanded', 'true');
    active = -1;
    input.removeAttribute('aria-activedescendant');
  }

  function close() {
    list.hidden = true;
    wrapper.classList.remove('is-open');
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    active = -1;
  }

  function choose(value) {
    input.value = value;
    close();
    choosing = true;
    try {
      // Evento `input` para que quien escuche el campo —la marca de cambios
      // sin guardar— se entere igual que si se hubiera tecleado.
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.focus();
    } finally {
      choosing = false;
    }
  }

  // --- Escuchadores -------------------------------------------------------

  const onInput = () => {
    if (choosing) return;
    open(input.value);
  };

  const onFocus = () => {
    if (choosing) return;
    // Al enfocar se enseña TODA la lista, no la filtrada por lo que ya hay
    // escrito: si el campo trae «gpt-4o-mini», filtrar por ese texto dejaría
    // una sola opción y el desplegable no serviría para cambiar de modelo.
    if (!isOpen()) open('');
  };

  const onKeyDown = (event) => {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        if (!isOpen()) open('');
        else setActive(active + 1);
        break;
      case 'ArrowUp':
        event.preventDefault();
        if (isOpen()) setActive(active - 1);
        break;
      case 'Enter':
        if (isOpen() && active >= 0 && visible[active] !== undefined) {
          // Solo se intercepta cuando hay una opción resaltada; si no, Enter
          // sigue siendo el envío normal del formulario.
          event.preventDefault();
          choose(visible[active]);
        } else if (isOpen()) {
          close();
        }
        break;
      case 'Escape':
        if (isOpen()) {
          event.stopPropagation();
          close();
        }
        break;
      case 'Tab':
        close();
        break;
      default:
        break;
    }
  };

  // Un solo escuchador para toda la lista, no uno por opción.
  const onListMouseDown = (event) => {
    const option = event.target.closest('.combo__option');
    if (!option) return;
    // `mousedown` y no `click`: el `blur` del campo llegaría antes que el
    // click y habría cerrado la lista, así que el click nunca se dispararía.
    event.preventDefault();
    choose(option.dataset.value);
  };

  const onToggle = (event) => {
    event.preventDefault();
    if (isOpen()) close();
    else {
      input.focus();
      open('');
    }
  };

  const onDocumentDown = (event) => {
    if (!wrapper.contains(event.target)) close();
  };

  input.addEventListener('input', onInput);
  input.addEventListener('focus', onFocus);
  input.addEventListener('keydown', onKeyDown);
  list.addEventListener('mousedown', onListMouseDown);
  toggle?.addEventListener('mousedown', onToggle);
  document.addEventListener('mousedown', onDocumentDown);

  close();

  return {
    destroy() {
      input.removeEventListener('input', onInput);
      input.removeEventListener('focus', onFocus);
      input.removeEventListener('keydown', onKeyDown);
      list.removeEventListener('mousedown', onListMouseDown);
      toggle?.removeEventListener('mousedown', onToggle);
      document.removeEventListener('mousedown', onDocumentDown);
    },
  };
}

/**
 * Marcado del combo. Lo pinta quien lo use; `attachCombo` solo lo anima.
 *
 * @param {object} opts
 * @param {string} opts.id           Id del campo.
 * @param {string} opts.value        Valor inicial.
 * @param {string} opts.placeholder  Texto de ayuda.
 * @param {string} opts.role         Valor de `data-role` para el formulario.
 */
export function comboMarkup({ id, value = '', placeholder = '', role = '' }) {
  return `
    <div class="combo">
      <input class="input combo__input" id="${escape(id)}"
             ${role ? `data-role="${escape(role)}"` : ''}
             type="text" autocomplete="off" spellcheck="false"
             role="combobox" aria-expanded="false" aria-autocomplete="list"
             aria-controls="${escape(id)}-list"
             value="${escape(value)}" placeholder="${escape(placeholder)}">
      <button type="button" class="combo__toggle" tabindex="-1"
              aria-label="Ver sugerencias"></button>
      <ul class="combo__list" id="${escape(id)}-list" role="listbox" hidden></ul>
    </div>`;
}
