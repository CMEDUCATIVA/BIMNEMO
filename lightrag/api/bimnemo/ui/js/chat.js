/* ==========================================================================
   BIMNEMO — Vista Chat
   Conversación contra la memoria. Dos modos de devolución: respuesta generada
   por el motor, o solo el contexto recuperado (sin llamada al LLM redactor).
   ========================================================================== */

import { askAllNemos, askNemo, searchAllNemos, searchNemo } from './api.js';
import { allNemos, currentNemoName } from './nemo.js';
import { icon } from './icons.js';
import { escape } from './format.js';

const history = [];
let busy = false;

/** Valor del selector que significa «todas las memorias». */
const ALL = '__all__';

/**
 * Rellena el selector de alcance.
 *
 * Por defecto busca en TODAS, que es lo que pidió el usuario: preguntar sin
 * tener que acordarse de en qué memoria está cada cosa. Elegir una concreta es
 * la excepción, no la norma.
 */
export function refreshChatScope() {
  const select = document.getElementById('chat-scope');
  if (!select) return;
  const previo = select.value || ALL;

  select.innerHTML =
    `<option value="${ALL}">Todas las memorias</option>` +
    allNemos()
      .map((n) => `<option value="${escape(n.id)}">${escape(n.name)}</option>`)
      .join('');

  // Si la memoria elegida desapareció, se vuelve a «todas» en vez de dejar el
  // selector apuntando a algo que ya no existe.
  select.value = [...select.options].some((o) => o.value === previo) ? previo : ALL;
}

function logEl() {
  return document.getElementById('chat-log');
}

function scrollToEnd() {
  const log = logEl();
  log.scrollTop = log.scrollHeight;
}

function welcome() {
  logEl().innerHTML = `
    <div class="empty">
      <span class="empty__icon">${icon('message-square', 28)}</span>
      <span class="empty__title">Pregunta a tu memoria</span>
      <span class="empty__text">
        Por defecto busca en <strong>todas</strong> tus memorias y te dice de
        cuál sale cada dato. Puedes acotar a una desde «Buscar en».
        Con «Solo contexto recuperado» ves lo que el motor encuentra sin gastar
        una llamada al modelo que redacta.
      </span>
    </div>`;
}

/**
 * Añade un mensaje al hilo.
 *
 * Devuelve el elemento de la burbuja para poder sustituir su contenido cuando
 * llega la respuesta, en lugar de repintar el hilo entero.
 */
function addMessage(role, text, { pending = false, error = false } = {}) {
  if (!history.length) logEl().innerHTML = '';

  const wrapper = document.createElement('div');
  wrapper.className = `msg msg--${role}${error ? ' msg--error' : ''}`;

  const avatar = document.createElement('span');
  avatar.className = 'msg__avatar';
  avatar.innerHTML = icon(role === 'user' ? 'user' : 'network', 15);

  const column = document.createElement('div');
  const bubble = document.createElement('div');
  bubble.className = 'msg__bubble';
  bubble.textContent = pending ? 'Consultando la memoria…' : text;

  const meta = document.createElement('div');
  meta.className = 'msg__meta';

  column.append(bubble, meta);
  wrapper.append(avatar, column);
  logEl().append(wrapper);

  history.push({ role, text });
  scrollToEnd();
  return { wrapper, bubble, meta };
}

/** Rótulo de qué memorias aportaron, para el pie del mensaje. */
function fuentes(consultadas) {
  if (!consultadas?.length) return '';
  return `${icon('library', 11)} ${consultadas.map((c) => escape(c.name)).join(' · ')}`;
}

async function send(question) {
  const mode = document.getElementById('chat-mode').value;
  const kind = document.getElementById('chat-kind').value;
  const scope = document.getElementById('chat-scope').value;
  const todas = scope === ALL;

  addMessage('user', question);
  const slot = addMessage('assistant', '', { pending: true });

  try {
    if (todas) {
      // Con varias memorias en juego, de dónde sale cada dato deja de ser un
      // adorno: es la información más útil de la respuesta.
      if (kind === 'context') {
        const result = await searchAllNemos(question, mode);
        slot.bubble.textContent = result.results.length
          ? result.results
              .map((r) => `### ${r.name}\n${r.context}`)
              .join('\n\n')
          : 'Ninguna memoria devolvió contexto para esta consulta.';
        slot.meta.innerHTML =
          `${fuentes(result.results)} · ${escape(mode)}, contexto en crudo`;
      } else {
        const result = await askAllNemos(question, mode);
        slot.bubble.textContent = result.response || '(respuesta vacía)';
        slot.meta.innerHTML = `${fuentes(result.consulted)} · ${escape(mode)}`;
        if (result.failures?.length) {
          slot.meta.innerHTML +=
            ` <span>· ${result.failures.length} memoria(s) fallaron</span>`;
        }
        if (result.llm_generated === false) {
          slot.meta.innerHTML += ' <span>· sin generación del modelo</span>';
        }
      }
      return;
    }

    const nemoId = scope;
    const nombre =
      allNemos().find((n) => n.id === nemoId)?.name || currentNemoName();

    if (kind === 'context') {
      const result = await searchNemo(nemoId, question, mode);
      slot.bubble.textContent =
        result.context || 'Esta memoria no devolvió contexto para la consulta.';
      slot.meta.textContent = `${nombre} · modo ${mode}, contexto en crudo`;
    } else {
      const result = await askNemo(nemoId, question, mode);
      slot.bubble.textContent = result.response || '(respuesta vacía)';
      slot.meta.textContent = `${nombre} · modo ${mode}`;
    }
  } catch (error) {
    slot.wrapper.classList.add('msg--error');
    slot.bubble.textContent =
      error.status === 401 || error.status === 403
        ? 'El servidor pide autenticación. Guarda tu clave de API en la pestaña API.'
        : `No se pudo consultar: ${error.detail || error.message}`;
    slot.meta.textContent = 'Revisa la configuración del motor en la pestaña Motor.';
  } finally {
    scrollToEnd();
  }
}

/** Ajusta el alto del cuadro de texto a su contenido, hasta el tope del CSS. */
function autoGrow(textarea) {
  textarea.style.height = 'auto';
  textarea.style.height = `${textarea.scrollHeight}px`;
}

/**
 * Engancha la vista de Chat. Una sola vez al arrancar.
 *
 * Los escuchadores van sobre el formulario y el cuadro de texto, que
 * sobreviven a los cambios de vista: cambiar de pestaña solo oculta la
 * sección, no la descarga, así que nada hay que volver a montar.
 */
export function mountChat() {
  welcome();
  // El selector de alcance lo rellena app.js cuando las memorias ya están
  // cargadas: al montar el chat todavía no existen.

  const form = document.getElementById('chat-form');
  const input = document.getElementById('chat-input');
  const button = document.getElementById('btn-send');

  async function submit() {
    const question = input.value.trim();
    if (!question || busy) return;

    busy = true;
    button.disabled = true;
    input.value = '';
    autoGrow(input);

    try {
      await send(question);
    } finally {
      busy = false;
      button.disabled = false;
      input.focus();
    }
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    submit();
  });

  input.addEventListener('input', () => autoGrow(input));

  input.addEventListener('keydown', (event) => {
    // Enter envía; Mayús+Enter salta línea. Es lo que espera quien escribe
    // en un chat, y el <form> por sí solo no lo hace en un <textarea>.
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  });

  document.getElementById('btn-clear-chat').addEventListener('click', () => {
    history.length = 0;
    welcome();
  });
}

/** Lleva el foco al cuadro de texto al entrar en la vista. */
export function focusChat() {
  document.getElementById('chat-input')?.focus();
}
