/* ==========================================================================
   BIMNEMO — Vista API
   La superficie que otra IA usa para conectarse a esta memoria: el manifiesto
   legible por máquina, los endpoints, la clave de acceso y ejemplos listos
   para pegar.
   ========================================================================== */

import { ROOT, getApiKey, getMemoryManifest, setApiKey } from './api.js';
import {
  abrirApi,
  generarClave,
  protegerApi,
  usarAviso,
} from './apiview-acceso.js';
import { instruccionParaAgente } from './apiview-agente.js';
import { mostrarDoc, ocultarDocs } from './apiview-docs.js';
import { agruparPorAmbito, rutasDeMemoria } from './apiview-rutas.js';
import { currentNemo, currentNemoName } from './nemo.js';
import { icon } from './icons.js';
import { escape } from './format.js';

/** Las solapas se cablean una vez; la vista se repinta muchas. */
let solapasPuestas = false;

function base() {
  return `${window.location.origin}${ROOT}`;
}

/**
 * Una fila de endpoint, con la ruta **ya resuelta** para la memoria abierta y
 * su botón de copiar.
 *
 * Lo que se copia lleva el servidor delante —`http://127.0.0.1:9621/nemo/…`—
 * porque es lo que hace falta para pegarlo en una terminal o en una skill. Una
 * ruta sin servidor obliga a componerla a mano, que es justo el trabajo que
 * esta pestaña existe para ahorrar.
 */
function endpointRow(item, url) {
  const completa = `${url}${item.ruta}`;
  return `
    <div class="endpoint">
      <span class="endpoint__method" data-method="${escape(item.method)}">${escape(item.method)}</span>
      <span class="endpoint__path" data-ruta="${escape(completa)}">${escape(item.ruta)}</span>
      <span class="endpoint__purpose">${escape(item.purpose)}</span>
      <button type="button" class="btn btn--ghost btn--icon endpoint__copiar"
              data-copy-texto="${escape(completa)}"
              title="Copiar la ruta completa" aria-label="Copiar la ruta completa">
        ${icon('copy', 12)}
      </button>
    </div>`;
}

/** Un ámbito con su título y sus endpoints. */
function ambitoCard(grupo, url, nemoNombre) {
  const subtitulo =
    grupo.clave === 'esta'
      ? escape(nemoNombre)
      : grupo.clave === 'todas'
        ? 'Sin importar cuál esté abierta'
        : 'LightRAG por debajo';

  return `
    <div class="card">
      <div class="card__head">
        <span class="card__title">${icon('plug', 14)}${escape(grupo.titulo)}</span>
        <span class="card__hint">${subtitulo}</span>
      </div>
      <div class="card__body">
        <div class="endpoints">
          ${grupo.filas.map((f) => endpointRow(f, url)).join('')}
        </div>
      </div>
    </div>`;
}

function modesList(modes) {
  return Object.entries(modes || {})
    .map(
      ([name, purpose]) =>
        `<dt class="mono">${escape(name)}</dt><dd>${escape(purpose)}</dd>`
    )
    .join('');
}

/**
 * La clave que va dentro de los ejemplos.
 *
 * Con la API protegida se escribe **la de verdad**, no un hueco que rellenar:
 * el botón de copiar tiene que entregar algo que funcione al pegarlo. Ese es
 * el sentido de proteger y compartir.
 *
 * Si no hay clave guardada en este navegador se cae al marcador: mejor un
 * ejemplo que hay que completar que uno que miente.
 */
function claveEjemplo() {
  return getApiKey() || 'TU_CLAVE';
}

function curlExample(url, authenticated, buscar) {
  const auth = authenticated
    ? `\n  -H "X-API-Key: ${claveEjemplo()}" \\`
    : '';
  return `curl -X POST "${url}${buscar}" \\${auth}
  -H "Content-Type: application/json" \\
  -d '{"query": "¿Qué dicen los pliegos sobre plazos?", "mode": "mix"}'`;
}

function pythonExample(url, authenticated, buscar, recordar) {
  const headers = authenticated
    ? `\n    headers={"X-API-Key": "${claveEjemplo()}"},`
    : '';
  return `import httpx

# Recuperar contexto SIN gastar el LLM que redacta.
respuesta = httpx.post(
    "${url}${buscar}",${headers}
    json={"query": "¿Qué dicen los pliegos sobre plazos?", "mode": "mix"},
    timeout=120,
)
contexto = respuesta.json()["context"]

# Guardar algo nuevo en la memoria.
httpx.post(
    "${url}${recordar}",${headers}
    json={"text": "El plazo de ejecución es de 180 días.", "source": "acta-2026-09"},
    timeout=60,
)`;
}

/**
 * Quién puede entrar a esta memoria.
 *
 * Antes aquí había un campo de clave **siempre visible**, que con la API
 * abierta —lo normal— mandaba una cabecera que nadie comprueba: un formulario
 * que se rellenaba para nada.
 *
 * Ahora es un interruptor que dice la verdad en los dos estados. Y lo que
 * enciende no es un adorno de pantalla: escribe la clave en el `.env` y
 * reinicia el motor, porque el guardia de las rutas se construye al arrancar.
 */
function accessCard(authenticated) {
  const clave = getApiKey();

  const abierto = `
    <p class="acceso__texto">
      Tu memoria está <strong>abierta</strong>: cualquier programa de este
      ordenador puede consultarla, escribir en ella y borrarla sin presentar
      nada. Cómodo para conectar tus skills sin configurar.
    </p>`;

  const cerrado = `
    <p class="acceso__texto">
      La API <strong>pide una clave</strong>. Esta ventana ya la tiene
      guardada; pégala en las herramientas que quieras dar acceso.
    </p>
    <div class="field">
      <label class="field__label" for="acceso-clave">Clave de acceso</label>
      <div class="row row--tight">
        <input class="input input--mono" id="acceso-clave" readonly
               value="${escape(clave)}" autocomplete="off">
        <button type="button" class="btn btn--ghost" data-copy-valor="acceso-clave">
          ${icon('copy', 12)} Copiar
        </button>
      </div>
    </div>
    <p class="acceso__texto card__hint">
      Es una credencial: viaja con el fichero donde la pegues. Si acaba en un
      repositorio o en un chat, cámbiala desde aquí.
    </p>`;

  return `
    <div class="card">
      <div class="card__head">
        <span class="card__title">${icon('plug', 14)}Acceso a la API</span>
        <span class="card__hint">${authenticated ? 'Protegida' : 'Abierta'}</span>
      </div>
      <div class="card__body stack stack--tight">
        <label class="interruptor">
          <input type="checkbox" id="acceso-toggle" ${authenticated ? 'checked' : ''}>
          <span class="interruptor__pista"><span class="interruptor__bola"></span></span>
          <span class="interruptor__texto">Pedir una clave para entrar</span>
        </label>

        ${authenticated ? cerrado : abierto}

        <div id="acceso-aviso"></div>
        <div class="row row--end">
          <button type="button" class="btn ${authenticated ? 'btn--ghost' : 'btn--primary'}"
                  id="btn-acceso" hidden></button>
        </div>
      </div>
    </div>`;
}

/**
 * La API pide clave y esta ventana no la tiene.
 *
 * Es el caso de abrir BIMNEMO en otro navegador —o en otro ordenador— después
 * de haber protegido la API. Sin esto, la aplicación cargaría sin datos y sin
 * explicación, y la única salida sería editar el `.env` a mano.
 */
function claveQueFaltaCard() {
  return `
    <div class="card">
      <div class="card__head">
        <span class="card__title">${icon('plug', 14)}Esta memoria pide una clave</span>
        <span class="card__hint">Protegida</span>
      </div>
      <div class="card__body stack stack--tight">
        <p class="acceso__texto">
          La API está protegida y esta ventana no tiene la clave, así que no
          puede leer nada. Pégala aquí y se guardará en este navegador.
        </p>
        <div class="field">
          <label class="field__label" for="clave-entrada">Clave de acceso</label>
          <div class="row row--tight">
            <input class="input input--mono" id="clave-entrada" type="password"
                   autocomplete="off" placeholder="La que generaste al protegerla">
            <button type="button" class="btn btn--primary" id="btn-clave-entrada">
              Entrar
            </button>
          </div>
        </div>
        <p class="acceso__texto card__hint">
          Si la has perdido, está en el fichero <code>.env</code> de BIMNEMO,
          en la línea <code>LIGHTRAG_API_KEY</code>.
        </p>
        <div id="clave-entrada-aviso"></div>
      </div>
    </div>`;
}

function wireClaveQueFalta() {
  const campo = document.getElementById('clave-entrada');
  const boton = document.getElementById('btn-clave-entrada');
  if (!campo || !boton) return;

  const entrar = async () => {
    const valor = campo.value.trim();
    if (!valor) return;
    setApiKey(valor);
    try {
      // Se comprueba antes de dar nada por bueno: guardar una clave que no
      // vale dejaría la aplicación igual de rota, pero en silencio.
      await getMemoryManifest();
      window.location.reload();
    } catch {
      setApiKey('');
      document.getElementById('clave-entrada-aviso').innerHTML = `
        <div class="notice notice--error">
          <span class="notice__icon">${icon('triangle-alert', 14)}</span>
          <span>Esa clave no vale. Compruébala en el <code>.env</code>.</span>
        </div>`;
    }
  };

  boton.addEventListener('click', entrar);
  campo.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') entrar();
  });
}

function snippetCard(title, iconName, code, id) {
  return `
    <div class="card">
      <div class="card__head">
        <span class="card__title">${icon(iconName, 14)}${escape(title)}</span>
        <button type="button" class="btn btn--ghost" data-copy="${escape(id)}">
          ${icon('copy', 12)} Copiar
        </button>
      </div>
      <div class="card__body">
        <pre class="codeblock" id="${escape(id)}">${escape(code)}</pre>
      </div>
    </div>`;
}

/** Pinta la vista API entera. */
export async function renderApi() {
  const body = document.getElementById('api-body');
  const url = base();

  body.innerHTML = '<p class="card__hint">Leyendo el manifiesto…</p>';

  let manifest;
  try {
    manifest = await getMemoryManifest();
  } catch (error) {
    // Un 401/403 no es «no se pudo leer»: es la respuesta correcta de una API
    // protegida a la que esta ventana no le ha enseñado la clave. Pintar
    // «Abierta» aquí sería decir lo contrario de lo que acaba de pasar, y
    // dejaría sin salida a quien abra BIMNEMO en otro navegador.
    if (error.status === 401 || error.status === 403) {
      body.innerHTML = claveQueFaltaCard();
      wireClaveQueFalta();
      return;
    }
    body.innerHTML = `
      <div class="notice notice--error">
        <span class="notice__icon">${icon('triangle-alert', 14)}</span>
        <span>No se pudo leer el manifiesto: ${escape(error.detail || error.message)}</span>
      </div>
      ${accessCard(false)}`;
    wireAccess(false);
    return;
  }

  const authenticated = !String(manifest.authentication || '')
    .toLowerCase()
    .includes('sin autenticación');

  // Todo lo que se enseña aquí habla de LA MEMORIA ABIERTA: las rutas, los
  // ejemplos y la instrucción del agente. Genéricas no se pueden pegar sin
  // editarlas, y para la memoria por defecto ni eso: su identificador es la
  // cadena vacía y `/nemo//…` responde 404.
  const nemoId = currentNemo();
  const nemoNombre = currentNemoName();
  const rutas = rutasDeMemoria(manifest.endpoints, nemoId);

  body.innerHTML = `
    <div class="notice notice--info">
      <span class="notice__icon">${icon('info', 14)}</span>
      <span>
        ${
          authenticated
            ? 'La API pide una clave: solo entra quien la tenga.'
            : 'Cualquier IA con acceso a esta máquina puede usar la memoria.'
        }
        La documentación interactiva está en las solapas
        <strong>Swagger</strong> y <strong>ReDoc</strong> de aquí arriba,
        y el esquema en
        <a href="${escape(ROOT)}/openapi.json" target="_blank" rel="noopener">openapi.json</a>.
      </span>
    </div>

    <div class="card">
      <div class="card__head">
        <span class="card__title">${icon('network', 14)}Dirección de la memoria</span>
        <span class="card__hint">${escape(manifest.authentication)}</span>
      </div>
      <div class="card__body">
        <pre class="codeblock" id="snippet-base">${escape(url)}</pre>
      </div>
    </div>

    ${agruparPorAmbito(manifest.endpoints, nemoId, manifest.ambitos || {})
      .map((g) => ambitoCard(g, url, nemoNombre))
      .join('')}

    <!-- Una sola columna, en el orden en que se usa esto: primero lo que se
         copia, luego la referencia, y al final lo que cambia algo.

         Había dos columnas, y la de la derecha dejaba sus fichas pegadas
         arriba, flotando al lado de los ejemplos. Cuando una columna tiene
         tres fichas y la otra una, no son dos columnas: es una lista con algo
         suelto al lado. -->
    ${snippetCard('Ejemplo — curl', 'code', curlExample(url, authenticated, rutas.buscar), 'snippet-curl')}
    ${snippetCard('Ejemplo — Python', 'code', pythonExample(url, authenticated, rutas.buscar, rutas.recordar), 'snippet-python')}
    ${snippetCard(
      'Instrucción para un agente',
      'message-square',
      instruccionParaAgente(url, manifest, authenticated, claveEjemplo(), {
            id: nemoId,
            nombre: nemoNombre,
          }),
      'snippet-agent'
    )}

    <div class="card">
      <div class="card__head">
        <span class="card__title">${icon('layers', 14)}Modos de recuperación</span>
        <span class="card__hint">El campo "mode" de las consultas</span>
      </div>
      <div class="card__body">
        <dl class="deflist">${modesList(manifest.retrieval_modes)}</dl>
      </div>
    </div>

    <!-- Lo último: es lo único de esta pantalla que cambia algo, y además
         reinicia el motor. -->
    ${accessCard(authenticated)}`;

  wireAccess(authenticated);
  wireCopy(body);
  if (!solapasPuestas) {
    wireSolapas();
    solapasPuestas = true;
  }
}

/**
 * El interruptor y su botón.
 *
 * El interruptor **no aplica nada por sí solo**: solo descubre el botón que
 * confirma. Encender la clave reinicia el motor, y eso no puede dispararse
 * por rozar una casilla sin querer.
 */
function wireAccess(authenticated) {
  const toggle = document.getElementById('acceso-toggle');
  const boton = document.getElementById('btn-acceso');
  if (!toggle || !boton) return;

  usarAviso((html) => {
    const hueco = document.getElementById('acceso-aviso');
    if (hueco) hueco.innerHTML = html;
  });

  toggle.addEventListener('change', () => {
    const quiereProteger = toggle.checked;
    if (quiereProteger === authenticated) {
      boton.hidden = true;
      return;
    }
    boton.hidden = false;
    boton.textContent = quiereProteger
      ? 'Generar clave y reiniciar'
      : 'Quitar la clave y reiniciar';
  });

  boton.addEventListener('click', async () => {
    boton.disabled = true;
    if (toggle.checked) {
      const clave = generarClave();
      // Se enseña ANTES de reiniciar: después de la recarga sigue disponible
      // en la ficha, pero verla aquí es lo que permite copiarla ya.
      const hueco = document.getElementById('acceso-aviso');
      if (hueco) {
        hueco.innerHTML = `
          <div class="notice notice--info">
            <span class="notice__icon">${icon('info', 14)}</span>
            <span>Clave generada: <code>${escape(clave)}</code></span>
          </div>`;
      }
      await protegerApi(clave);
    } else {
      await abrirApi();
    }
    boton.disabled = false;
  });
}

/** Las solapas: Guía, Swagger y ReDoc. */
function wireSolapas() {
  const solapas = document.querySelectorAll('#view-api .solapa');
  const guia = document.getElementById('api-body');

  solapas.forEach((s) => {
    s.addEventListener('click', () => {
      solapas.forEach((o) => o.setAttribute('aria-selected', String(o === s)));
      const cual = s.dataset.solapa;
      guia.hidden = cual !== 'guia';
      if (cual === 'guia') ocultarDocs();
      else mostrarDoc(cual);
    });
  });
}

/**
 * Copia un texto y lo dice en el propio botón.
 *
 * Si el portapapeles está bloqueado —sin HTTPS, sin permiso— no se calla: se
 * avisa, porque creer que copiaste algo que no copiaste es peor que saber que
 * no se pudo.
 */
async function copiar(texto, boton) {
  const original = boton.innerHTML;
  try {
    await navigator.clipboard.writeText(texto);
    boton.innerHTML = `${icon('check', 12)} Copiado`;
  } catch {
    boton.innerHTML = `${icon('triangle-alert', 12)} No se pudo`;
  }
  window.setTimeout(() => {
    boton.innerHTML = original;
  }, 1600);
}

/** Un solo escuchador para todos los botones de copiar de la vista. */
function wireCopy(root) {
  root.addEventListener('click', async (event) => {
    // Dos formas de copiar: el texto de un bloque, o el VALOR de un campo.
    // La clave vive en un `input`, y `textContent` de un input está vacío.
    // Copiar un texto que ya está en el atributo: las rutas de los endpoints.
    const suelto = event.target.closest('[data-copy-texto]');
    if (suelto) {
      await copiar(suelto.dataset.copyTexto, suelto);
      return;
    }

    const campo = event.target.closest('[data-copy-valor]');
    if (campo) {
      const entrada = document.getElementById(campo.dataset.copyValor);
      if (entrada) await copiar(entrada.value, campo);
      return;
    }

    const button = event.target.closest('[data-copy]');
    if (!button) return;
    const source = document.getElementById(button.dataset.copy);
    if (!source) return;

    try {
      await navigator.clipboard.writeText(source.textContent);
      const original = button.innerHTML;
      button.innerHTML = `${icon('check', 12)} Copiado`;
      window.setTimeout(() => {
        button.innerHTML = original;
      }, 1500);
    } catch {
      // El portapapeles puede estar bloqueado (sin HTTPS, sin permiso). Se
      // deja el texto seleccionado para que se copie a mano.
      const range = document.createRange();
      range.selectNodeContents(source);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    }
  });
}
