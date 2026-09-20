/* ==========================================================================
   BIMNEMO — Vista Configuración IA
   --------------------------------------------------------------------------
   Tres bloques: modelo de lenguaje, embeddings y reordenado. Cada uno es el
   mismo formulario — proveedor, host, modelo, clave — así que se construye
   una vez y se instancia tres veces.

   El proveedor NO es el binding: elegir «DeepSeek» guarda `LLM_BINDING=openai`
   con el host de DeepSeek, porque eso es lo que el motor entiende. La vista
   enseña el binding real para que no haya magia oculta.
   ========================================================================== */

import {
  API_KEY_UNCHANGED,
  getProviders,
  getSettings,
  saveSettings,
} from './api.js';
import { attachCombo, comboMarkup } from './combo.js';
import { icon } from './icons.js';
import {
  hasUnsavedChanges,
  markDirty,
  olvidarReferencia,
  setLector,
  setReferencia,
} from './configuracion-cambios.js';
import {
  languageCard,
  onLanguageChange,
  readLanguage,
} from './configuracion-idioma.js';
import { escape } from './format.js';
import { restartBanner, usarBanner } from './configuracion-reinicio.js';

const SECTIONS = [
  {
    kind: 'llm',
    title: 'Modelo de lenguaje',
    icon: 'message-square',
    hint: 'Extrae entidades al indexar y redacta las respuestas del chat.',
  },
  {
    kind: 'embedding',
    title: 'Embeddings',
    icon: 'layers',
    hint: 'Convierte el texto en vectores para poder buscarlo.',
  },
  {
    kind: 'rerank',
    title: 'Reordenado',
    icon: 'sliders-horizontal',
    hint: 'Opcional. Reordena lo recuperado; sube mucho la calidad del modo «mix».',
  },
];

let catalog = null;
let saved = null;

// Combos vivos. Se sueltan antes de repintar: la vista se reconstruye con
// innerHTML, y el escuchador que `attachCombo` pone en `document` sobrevive
// a sus elementos. Sin esto, cada repintado dejaría uno más trabajando sobre
// un marcado que ya no existe.
let combos = [];

function destroyCombos() {
  combos.forEach((c) => c.destroy());
  combos = [];
}

/* --- Construcción --------------------------------------------------------- */

function groupedOptions(providers, selected) {
  const groups = new Map();
  for (const provider of providers) {
    const name = provider.group || 'Opciones';
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(provider);
  }

  return [...groups.entries()]
    .map(
      ([name, items]) => `
      <optgroup label="${escape(name)}">
        ${items
          .map(
            (p) =>
              `<option value="${escape(p.key)}"${p.key === selected ? ' selected' : ''}>` +
              `${escape(p.label)}</option>`
          )
          .join('')}
      </optgroup>`
    )
    .join('');
}

/** Modelos sugeridos del proveedor que esté seleccionado AHORA en esa sección.
 *
 * Se consulta en el momento de abrir el combo, no al pintarlo: de lo
 * contrario la lista se quedaría anclada al proveedor inicial y sugeriría
 * modelos de otro — con OpenAI elegido llegó a ofrecer
 * `openai/gpt-4o-mini`, que es de OpenRouter.
 */
function currentModels(kind) {
  const select = document.querySelector(`#cfg-${kind}-provider`);
  if (!select) return [];
  const provider = providersOf(kind).find((p) => p.key === select.value);
  return provider ? provider.models : [];
}

function sectionCard(section, providers, current) {
  const selected = current.provider || providers[0].key;
  const provider = providers.find((p) => p.key === selected) || providers[0];
  const isRerankOff = section.kind === 'rerank' && provider.binding === 'null';

  return `
    <div class="card" data-section="${escape(section.kind)}">
      <div class="card__head">
        <span class="card__title">${icon(section.icon, 14)}${escape(section.title)}</span>
        <span class="card__hint">${escape(section.hint)}</span>
      </div>
      <div class="card__body stack stack--tight">
        <div class="cfggrid">
          <div class="field">
            <label class="field__label" for="cfg-${section.kind}-provider">Proveedor</label>
            <span class="selectwrap">
              <select class="select" id="cfg-${section.kind}-provider" data-role="provider">
                ${groupedOptions(providers, selected)}
              </select>
            </span>
            <a class="field__link" data-role="key-link" target="_blank"
               rel="noopener noreferrer" hidden></a>
          </div>

          <div class="field" data-hide-when-off>
            <label class="field__label" for="cfg-${section.kind}-model">Modelo</label>
            ${comboMarkup({
              id: `cfg-${section.kind}-model`,
              role: 'model',
              value: current.model || '',
              placeholder: provider.models[0] || 'nombre del modelo',
            })}
            <span class="field__help">
              Elige uno de la lista o escribe cualquier otro.
            </span>
          </div>
        </div>

        <div class="cfggrid" data-hide-when-off>
          <div class="field" data-role="host-field">
            <label class="field__label" for="cfg-${section.kind}-host">Dirección (host)</label>
            <input class="input mono" id="cfg-${section.kind}-host" data-role="host"
                   autocomplete="off" value="${escape(current.host || '')}"
                   placeholder="${escape(hostPlaceholder(provider))}">
            <span class="field__help" data-role="host-help"></span>
          </div>

          <div class="field" data-role="key-field">
            <label class="field__label" for="cfg-${section.kind}-key">Clave de API</label>
            <div class="clave">
              <input class="input" type="password" id="cfg-${section.kind}-key"
                     data-role="apikey" autocomplete="new-password"
                     ${current.api_key_set ? 'readonly' : ''}
                     placeholder="${current.api_key_set ? '•••••• (guardada)' : 'sin configurar'}">
              ${
                current.api_key_set
                  ? `<button type="button" class="btn" data-role="key-edit">Cambiar</button>`
                  : ''
              }
            </div>
            <span class="field__help" data-role="key-hint"></span>
          </div>
        </div>

        ${
          section.kind === 'embedding'
            ? `<div class="cfggrid" data-hide-when-off>
                 <div class="field">
                   <label class="field__label" for="cfg-embedding-dim">Dimensión</label>
                   <input class="input" type="number" id="cfg-embedding-dim" data-role="dim"
                          min="1" max="16384" value="${current.dim ?? ''}"
                          placeholder="la del modelo">
                   <span class="field__help">
                     Cambiar de modelo de embeddings invalida los vectores ya guardados:
                     hay que vaciar la memoria y reindexar.
                   </span>
                 </div>
                 <div></div>
               </div>`
            : ''
        }

        <div data-role="note"></div>
        <div class="cfgbinding">
          Se guardará como
          <code data-role="binding">${escape(provider.binding)}</code>
        </div>
      </div>
    </div>`;
}

/** Dominio de una URL, para no enseñar la ruta entera en el enlace. */
/**
 * Qué poner de marca de agua en el campo de dirección.
 *
 * Tres casos distintos y hasta ahora los tres decían lo mismo —«lo decide el
 * proveedor»—, que no ayuda en ninguno: no es lo mismo que exista una
 * dirección y se rellene sola, que no exista una universal porque depende de
 * tu cuenta, que el proveedor ni la mire.
 */
function hostPlaceholder(provider) {
  if (provider.host) return provider.host;
  if (provider.host_used === false) return 'Este proveedor no usa dirección';
  return provider.host_hint || 'lo decide el proveedor';
}

/**
 * Deja el campo de dirección diciendo la verdad para este proveedor.
 *
 * Voyage se conecta a su endpoint fijo desde su propia biblioteca y nunca
 * recibe lo que se escriba aquí, así que el campo se deshabilita: un campo
 * editable que no hace nada es peor que no tener campo.
 */
function applyHost(card, provider) {
  const input = card.querySelector('[data-role="host"]');
  const help = card.querySelector('[data-role="host-help"]');
  const ignora = provider.host_used === false;

  input.placeholder = hostPlaceholder(provider);
  input.disabled = ignora;
  if (ignora) input.value = '';

  // La ayuda es solo para el caso que la marca de agua no puede contar: que
  // el campo no sirva de nada. Cuando la marca ya lleva el patrón —Azure,
  // Bedrock, compatible— repetirlo debajo es ruido.
  help.textContent = ignora
    ? 'La biblioteca de este proveedor se conecta a su dirección fija; este campo no se usa.'
    : '';
  help.hidden = !help.textContent;
}

function hostOf(url) {
  try {
    return new URL(url).host.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/* --- Reacción al cambio de proveedor -------------------------------------- */

function providersOf(kind) {
  return catalog[kind];
}

function applyProvider(card, kind, { resetFields }) {
  const select = card.querySelector('[data-role="provider"]');
  const provider = providersOf(kind).find((p) => p.key === select.value);
  if (!provider) return;

  const hostInput = card.querySelector('[data-role="host"]');
  const modelInput = card.querySelector('[data-role="model"]');
  const keyField = card.querySelector('[data-role="key-field"]');
  const keyHint = card.querySelector('[data-role="key-hint"]');
  const note = card.querySelector('[data-role="note"]');
  const binding = card.querySelector('[data-role="binding"]');

  binding.textContent = provider.binding;

  if (resetFields) {
    // Al cambiar de proveedor se rellenan los valores sugeridos: dejar el
    // host de DeepSeek al elegir Groq es el error más fácil de cometer.
    hostInput.value = provider.host_used === false ? '' : provider.host || '';
    modelInput.value = provider.models[0] || '';
    syncDim(card, provider, modelInput.value);
  }
  applyHost(card, provider);
  modelInput.placeholder = provider.models[0] || 'nombre del modelo';

  keyField.hidden = !provider.needs_key;
  keyHint.textContent = provider.key_hint || '';

  // El enlace va pegado al SELECTOR, no al campo de la clave.
  //
  // Estuvo dentro del bloque de la clave y desaparecía con él en los
  // proveedores que no la piden —Ollama, Bedrock—, justo donde también hace
  // falta: esa página es donde se ve qué modelos hay disponibles hoy, y los
  // catálogos cambian cada pocas semanas. Aquí se ve siempre, y cambia al
  // cambiar de proveedor.
  const keyLink = card.querySelector('[data-role="key-link"]');
  if (provider.key_url) {
    keyLink.href = provider.key_url;
    keyLink.textContent = `${provider.needs_key ? 'Clave y modelos' : 'Ver modelos'} en ${hostOf(provider.key_url)} ↗`;
    keyLink.hidden = false;
  } else {
    keyLink.removeAttribute('href');
    keyLink.hidden = true;
  }

  note.innerHTML = provider.note
    ? `<div class="notice notice--info">
         <span class="notice__icon">${icon('info', 13)}</span>
         <span>${escape(provider.note)}</span>
       </div>`
    : '';

  // El reordenado desactivado no tiene nada más que configurar.
  const off = kind === 'rerank' && provider.binding === 'null';
  card.querySelectorAll('[data-hide-when-off]').forEach((el) => {
    el.hidden = off;
  });
  card.querySelector('.cfgbinding').hidden = off;
}

/**
 * Pone la dimensión que corresponde al modelo de embeddings elegido.
 *
 * No es un adorno: si la dimensión no cuadra con la que devuelve el modelo,
 * la ingesta falla — y el error que sale no dice que el número esté mal. En
 * el catálogo, `dims[i]` es la dimensión de `models[i]`.
 *
 * Con un modelo que no está en el catálogo no hay nada que deducir, y las dos
 * situaciones piden cosas distintas:
 *
 * * **Al cambiar de proveedor** (`fallback: true`) se pone su dimensión más
 *   habitual. Arrastrar los 3072 de Gemini a Ollama sería peor que acertar a
 *   medias.
 * * **Al escribir el modelo a mano** (`fallback: false`) no se toca. Bajar el
 *   número mientras se teclea, letra a letra, pisaría lo que el usuario
 *   hubiera puesto ahí a propósito.
 */
function syncDim(card, provider, model, { fallback = true } = {}) {
  const dimInput = card.querySelector('[data-role="dim"]');
  if (!dimInput || !provider.dims.length) return;

  const index = provider.models.indexOf(model);
  if (index >= 0) {
    if (provider.dims[index]) dimInput.value = provider.dims[index];
  } else if (fallback && provider.dims[0]) {
    dimInput.value = provider.dims[0];
  }
}

/* --- Lectura del formulario ----------------------------------------------- */

function readSection(kind) {
  const card = document.querySelector(`[data-section="${kind}"]`);
  if (!card) return null;

  const keyInput = card.querySelector('[data-role="apikey"]');
  const dimInput = card.querySelector('[data-role="dim"]');

  return {
    provider: card.querySelector('[data-role="provider"]').value,
    host: card.querySelector('[data-role="host"]').value.trim(),
    model: card.querySelector('[data-role="model"]').value.trim(),
    // La clave solo viaja si el usuario pulsó «Cambiar».
    //
    // El navegador rellena solo los campos de contraseña — pasa aunque lleven
    // `autocomplete="new-password"` — y con eso se colaban dos fallos a la
    // vez: la pantalla creía que había cambios sin guardar, y al guardar se
    // habría escrito en el `.env` la clave que Chrome inventó encima de la
    // buena. Un campo bloqueado no se puede autorrellenar por accidente.
    //
    // Campo vacío tampoco significa «bórrala»: para eso se edita el .env a
    // mano; un formulario no debe destruir una credencial por descuido.
    api_key:
      keyInput && !keyInput.readOnly && keyInput.value
        ? keyInput.value
        : API_KEY_UNCHANGED,
    dim: dimInput && dimInput.value ? Number(dimInput.value) : null,
  };
}

/* --- Avisos --------------------------------------------------------------- */

function setBanner(html) {
  document.getElementById('config-banner').innerHTML = html;
}

// El módulo del reinicio escribe en el mismo sitio, pero no tiene por qué
// saber cuál es: se lo decimos una vez.
usarBanner(setBanner);

/* --- Acciones ------------------------------------------------------------- */

async function doSave() {
  const button = document.getElementById('btn-config-save');
  button.disabled = true;
  try {
    const payload = {
      llm: readSection('llm'),
      embedding: readSection('embedding'),
      rerank: readSection('rerank'),
      language: readLanguage(),
    };
    const result = await saveSettings(payload);
    // Lo que acaba de guardarse es la nueva vara de medir.
    setReferencia();

    if (result.restart_required) {
      restartBanner(result.message);
    } else {
      setBanner(`
        <div class="notice notice--info">
          <span class="notice__icon">${icon('check', 13)}</span>
          <span>${escape(result.message)}</span>
        </div>`);
    }
    saved = await getSettings();
  } catch (error) {
    setBanner(`
      <div class="notice notice--error">
        <span class="notice__icon">${icon('triangle-alert', 14)}</span>
        <span>No se pudo guardar: ${escape(error.detail || error.message)}</span>
      </div>`);
  } finally {
    button.disabled = false;
  }
}

/* --- Pintado -------------------------------------------------------------- */

export async function renderConfiguracion() {
  const body = document.getElementById('config-body');
  destroyCombos();
  body.innerHTML = '<p class="card__hint">Leyendo la configuración…</p>';

  try {
    if (!catalog) catalog = await getProviders();
    saved = await getSettings();
  } catch (error) {
    body.innerHTML = `
      <div class="notice notice--error">
        <span class="notice__icon">${icon('triangle-alert', 14)}</span>
        <span>No se pudo leer la configuración: ${escape(
          error.detail || error.message
        )}</span>
      </div>`;
    return;
  }

  body.innerHTML = `
    <div id="config-banner"></div>
    <div class="notice notice--warn">
      <span class="notice__icon">${icon('triangle-alert', 14)}</span>
      <span>
        Esta configuración es <strong>común a todas tus memorias</strong>.
        Cambiar el modelo de embeddings invalida los vectores de
        <strong>todas</strong>, no solo de la activa: habría que vaciarlas y
        reindexar.
      </span>
    </div>
    ${
      saved.env_exists
        ? ''
        : `<div class="notice notice--warn">
             <span class="notice__icon">${icon('triangle-alert', 14)}</span>
             <span>Todavía no hay fichero <code>.env</code>. Se creará al guardar.</span>
           </div>`
    }
    ${SECTIONS.map((s) => sectionCard(s, providersOf(s.kind), saved[s.kind])).join('')}
    ${languageCard(saved.language || 'English')}
    <p class="card__hint mono">${escape(saved.env_path)}</p>`;

  // El selector de idioma no está dentro de ningún bloque de proveedor, así
  // que necesita su propio escuchador para que «Guardar» se entere.
  onLanguageChange(() => markDirty());

  for (const section of SECTIONS) {
    const card = document.querySelector(`[data-section="${section.kind}"]`);
    applyProvider(card, section.kind, { resetFields: false });

    // El combo pide sus opciones al abrirse, así que siempre ofrece las del
    // proveedor que esté elegido en ese momento.
    combos.push(
      attachCombo(card.querySelector('[data-role="model"]'), () =>
        currentModels(section.kind)
      )
    );

    card
      .querySelector('[data-role="provider"]')
      .addEventListener('change', () => {
        applyProvider(card, section.kind, { resetFields: true });
        markDirty();
      });

    // «Cambiar» desbloquea el campo de la clave. Hasta entonces no se puede
    // escribir en él ni el navegador puede rellenarlo.
    card.querySelector('[data-role="key-edit"]')?.addEventListener('click', (event) => {
      const input = card.querySelector('[data-role="apikey"]');
      input.readOnly = false;
      input.value = '';
      input.placeholder = 'Pega aquí la clave nueva';
      event.currentTarget.remove();
      input.focus();
    });

    // Un solo escuchador por tarjeta para todos sus campos de texto.
    card.addEventListener('input', (event) => {
      markDirty();
      // Cambiar de modelo dentro del mismo proveedor también cambia la
      // dimensión: text-embedding-3-small son 1536 y -3-large son 3072.
      if (section.kind === 'embedding' && event.target.dataset.role === 'model') {
        const select = card.querySelector('[data-role="provider"]');
        const provider = providersOf('embedding').find((p) => p.key === select.value);
        if (provider) {
          syncDim(card, provider, event.target.value, { fallback: false });
        }
      }
    });
  }

  // El retrato se toma AL FINAL, con el formulario ya montado y con los
  // valores puestos por `applyProvider`. Tomarlo antes mediría un formulario a
  // medias y todo parecería un cambio del usuario.
  setReferencia();

  if (saved.restart_required) {
    restartBanner(
      'Hay configuración guardada que el motor todavía no está usando.'
    );
  }
}

/** Engancha los botones de la cabecera. Una sola vez, al arrancar. */
export function mountConfiguracion() {
  // El módulo de cambios no conoce el formulario: se le dice cómo leerlo.
  setLector(() => ({
    llm: readSection('llm'),
    embedding: readSection('embedding'),
    rerank: readSection('rerank'),
    language: readLanguage(),
  }));

  document.getElementById('btn-config-save').addEventListener('click', doSave);
  document
    .getElementById('btn-config-reload')
    .addEventListener('click', async () => {
      olvidarReferencia();
      await renderConfiguracion();
    });
}

export { hasUnsavedChanges };
