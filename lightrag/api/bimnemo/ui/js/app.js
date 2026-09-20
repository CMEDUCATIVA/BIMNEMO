/* ==========================================================================
   BIMNEMO — Arranque
   Navegación entre vistas, tema, iconos del marcado y estado del motor.
   Es el único fichero que conoce todas las vistas; ninguna conoce a las otras.
   ========================================================================== */

import {
  getEngine,
  getAppBuild,
  getHealth,
} from './api.js';
import { icon } from './icons.js';
import { mountActualizar } from './actualizar.js';
import { mountDialogo, preguntar } from './dialogo.js';
import { renderPanel } from './panel.js';
import {
  invalidarGrafo,
  mountGrafo,
  refrescarGrafoSiHaceFalta,
  renderGrafo,
} from './grafo.js';
import { filterByCategory, mountArchivos, reloadArchivos } from './archivos.js';
import {
  mountProgressVisibility,
  resetProgress,
  watchProgress,
} from './archivos-progreso.js';
import { focusChat, mountChat, refreshChatScope } from './chat.js';
import {
  hasUnsavedChanges,
  mountConfiguracion,
  renderConfiguracion,
} from './configuracion.js';
import {
  currentNemo,
  loadNemos,
  mountNemo,
  onNemoChange,
  selectNemo,
} from './nemo.js';
import { renderMotor } from './motor.js';
import { renderApi } from './apiview.js';

const THEME_STORAGE = 'bimnemo.theme';
const VIEWS = ['panel', 'archivos', 'chat', 'configuracion', 'motor', 'api'];

let current = 'panel';

/* --- Iconos del marcado --------------------------------------------------- */

/**
 * Rellena los huecos `data-icon` del HTML.
 *
 * El marcado declara QUÉ icono quiere y de qué tamaño; el SVG lo pone el
 * ayudante. Así no hay un solo trazado suelto en index.html.
 */
function paintIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach((node) => {
    const size = Number(node.dataset.iconSize) || 16;
    node.innerHTML = icon(node.dataset.icon, size);
  });
}

/* --- Tema ----------------------------------------------------------------- */

function storedTheme() {
  try {
    return window.localStorage.getItem(THEME_STORAGE);
  } catch {
    return null;
  }
}

function applyTheme(theme) {
  // Sin preferencia guardada se quita el atributo y manda el sistema, que es
  // lo que hace el bloque @media de tokens.css.
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;

  const dark =
    theme === 'dark' ||
    (!theme && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.getElementById('btn-theme').innerHTML = icon(dark ? 'sun' : 'moon', 14);
}

function toggleTheme() {
  const dark =
    document.documentElement.dataset.theme === 'dark' ||
    (!document.documentElement.dataset.theme &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);
  const next = dark ? 'light' : 'dark';
  try {
    window.localStorage.setItem(THEME_STORAGE, next);
  } catch {
    // No poder recordarlo no impide cambiarlo en esta sesión.
  }
  applyTheme(next);
}

/* --- Navegación ----------------------------------------------------------- */

/**
 * Cambia de vista.
 *
 * Las secciones se ocultan, no se descargan: por eso los escuchadores de cada
 * vista se registran una sola vez al arrancar y nunca hay que volver a
 * montarlos. Lo que sí se refresca aquí es el contenido que envejece.
 */
async function show(view) {
  if (!VIEWS.includes(view)) view = 'panel';

  // Salir de la configuración con cambios a medias pierde lo escrito, y el
  // usuario no tiene por qué saberlo: se le pregunta. Con el diálogo de la
  // aplicación, no con el del navegador.
  if (current === 'configuracion' && view !== 'configuracion' && hasUnsavedChanges()) {
    const seguir = await preguntar({
      titulo: 'Cambios sin guardar',
      mensaje:
        'Has modificado la configuración y todavía no la has guardado. Si ' +
        'sales ahora, se pierde lo escrito.',
      aceptar: 'Salir sin guardar',
      cancelar: 'Seguir editando',
      peligro: true,
    });
    if (!seguir) return;
  }

  current = view;

  VIEWS.forEach((name) => {
    document
      .getElementById(`view-${name}`)
      .classList.toggle('is-active', name === view);
  });

  document.querySelectorAll('.navitem').forEach((item) => {
    if (item.dataset.view === view) item.setAttribute('aria-current', 'page');
    else item.removeAttribute('aria-current');
  });

  document.getElementById('workspace').scrollTop = 0;

  if (view === 'chat') focusChat();
  // El grafo puede haber caducado mientras se miraba otra pestaña: se lee
  // ahora, que es cuando hay alguien delante. Si nada cambió, no hace nada.
  if (view === 'panel') guard(refrescarGrafoSiHaceFalta);
  if (view === 'configuracion') await guard(renderConfiguracion);
  if (view === 'motor') await guard(renderMotor);
  if (view === 'api') await guard(renderApi);
}

/** Ejecuta una acción y deja el fallo escrito en la consola, no en silencio. */
async function guard(action) {
  try {
    return await action();
  } catch (error) {
    console.error('[BIMNEMO]', error);
    return null;
  }
}

/* --- Estado del motor ----------------------------------------------------- */

async function refreshEngineState() {
  const badge = document.getElementById('engine-state');
  const dot = badge.querySelector('.dot');
  const text = document.getElementById('engine-state-text');

  try {
    const health = await getHealth();
    const status = String(health.status || '').toLowerCase();
    const healthy = status === 'healthy' || status === 'ok';
    dot.dataset.state = healthy ? 'ok' : 'error';
    text.textContent = healthy ? 'Motor activo' : `Motor: ${health.status}`;
  } catch (error) {
    dot.dataset.state = 'error';
    text.textContent =
      error.status === 401 || error.status === 403
        ? 'Requiere clave'
        : 'Motor no disponible';
  }
}

/**
 * La versión, al final del carril.
 *
 * Es lo primero que hace falta al pedir soporte —«¿qué versión tienes?»— y no
 * estaba a la vista en ninguna parte: había que abrir la pestaña Motor.
 *
 * Lleva también el commit instalado en el título emergente, porque entre dos
 * versiones hay commits y saber cuál se está ejecutando es lo que distingue
 * «ya lo arreglamos» de «lo arreglamos después de tu copia».
 */
async function pintarVersion() {
  const hueco = document.getElementById('rail-version');
  if (!hueco) return;
  try {
    const motor = await getEngine(currentNemo());
    const p = motor.product || {};
    hueco.textContent = `${p.name || 'BIMNEMO'} ${p.version || ''}`.trim();
    hueco.title = p.build
      ? `${p.name} ${p.version} · ${p.build} — motor ${p.engine} ${p.engine_version}`
      : `motor ${p.engine} ${p.engine_version}`;
  } catch {
    // Sin motor no hay versión que enseñar, y un «desconocida» en el pie del
    // carril no ayuda a nadie: se deja vacío.
    hueco.textContent = '';
  }
}

/* --- Versión de la interfaz ----------------------------------------------- */

// Huella de los ficheros de interfaz con la que arrancó ESTA ventana. Si la
// del servidor deja de coincidir, se actualizó BIMNEMO y lo que se está
// ejecutando es el código anterior.
let loadedBuild = null;

/**
 * Comprueba si la ventana está ejecutando una versión vieja de la interfaz.
 *
 * Una página que no se recarga no vuelve a pedir sus módulos, por mucho que el
 * servidor los sirva sin caché: quedan en memoria hasta que alguien recarga.
 * Visto desde fuera eso es indistinguible de un fallo del programa — una lista
 * desactualizada, un botón que «no aparece» — así que lo dice en vez de
 * dejarlo pasar.
 */
async function checkBuild() {
  let build;
  try {
    build = await getAppBuild();
  } catch {
    // El motor puede estar reiniciándose; no es momento de avisar de nada.
    return;
  }

  if (loadedBuild === null) {
    loadedBuild = build.fingerprint;
    return;
  }
  if (build.fingerprint === loadedBuild) return;

  document.getElementById('stale-banner').innerHTML = `
    <div class="stale">
      ${icon('triangle-alert', 14)}
      <span>
        BIMNEMO se ha actualizado. Esta ventana sigue ejecutando la versión
        anterior, así que puede mostrarte datos o pantallas desfasados.
      </span>
      <button type="button" class="btn btn--primary" id="btn-stale-reload">
        Recargar ahora
      </button>
    </div>`;
  document
    .getElementById('btn-stale-reload')
    ?.addEventListener('click', () => window.location.reload());
}

/* --- Refresco global ------------------------------------------------------ */

async function refreshAll() {
  const button = document.getElementById('btn-refresh');
  button.disabled = true;
  try {
    await Promise.all([
      guard(() => renderPanel(goToCategory, goToNemo)),
      guard(() => renderGrafo()),
      guard(reloadArchivos),
      refreshEngineState(),
      checkBuild(),
    ]);
    if (current === 'motor') await guard(renderMotor);
  } finally {
    button.disabled = false;
  }
}

/** Ir a Archivos filtrado por una categoría (desde una tarjeta del panel). */
function goToCategory(key) {
  filterByCategory(key);
  show('archivos');
}

/** Cambiar de memoria desde el desglose del panel. */
function goToNemo(nemoId) {
  selectNemo(nemoId);
}

/* --- Arranque ------------------------------------------------------------- */

async function start() {
  applyTheme(storedTheme());
  paintIcons();

  document.getElementById('btn-theme').addEventListener('click', toggleTheme);
  document.getElementById('btn-refresh').addEventListener('click', refreshAll);

  document.querySelectorAll('.navitem').forEach((item) => {
    item.addEventListener('click', () => show(item.dataset.view));
  });

  // Cada vista se monta una vez. Chat no pide datos al servidor, así que va
  // primero y queda usable aunque el resto tarde.
  mountDialogo();
  mountActualizar();
  mountProgressVisibility();
  mountChat();
  mountConfiguracion();
  mountNemo();
  mountGrafo();

  // Las NEMOs se cargan ANTES que cualquier vista: todas preguntan por la
  // memoria activa, y arrancar sin saber cuál es las haría pedir datos de la
  // que no toca y repintar acto seguido.
  await guard(loadNemos);

  // El selector de alcance del chat se monta antes de que existan las
  // memorias, así que se rellena AQUÍ. Suscribirse al cambio de memoria no
  // bastaría: cargar la lista por primera vez no es un cambio.
  refreshChatScope();

  // Cambiar de memoria repinta panel y archivos. Las demás vistas se pintan
  // al entrar en ellas, así que no hace falta tocarlas aquí.
  onNemoChange(() => {
    guard(() => renderPanel(goToCategory, goToNemo));
    // El grafo se reinicia: una entidad de la memoria anterior no tiene por
    // qué existir en la nueva.
    guard(() => renderGrafo({ reset: true }));
    guard(reloadArchivos);
    // La vista API habla de la memoria abierta: sus rutas, sus ejemplos y la
    // instrucción que se copia llevan el identificador dentro. Dejarla sin
    // repintar daría rutas de otra memoria, que es peor que no darlas.
    if (current === 'api') guard(renderApi);
    // El estado de la tubería es por memoria: el banner de la anterior estaría
    // contando trabajo que no es de esta.
    guard(resetProgress);
    refreshChatScope();
    if (current === 'motor') guard(renderMotor);
  });

  await guard(() => mountArchivos(() => guard(() => renderPanel(goToCategory, goToNemo))));
  await guard(() => renderPanel(goToCategory, goToNemo));
  // El grafo no se espera: es la lectura más cara del panel y las cifras ya
  // están puestas.
  guard(() => renderGrafo({ reset: true }));
  await refreshEngineState();
  await guard(pintarVersion);
  await checkBuild();

  // Se vuelve a mirar cada minuto. No hace falta más: quien actualiza BIMNEMO
  // está delante, y un aviso que tarda un minuto en salir sigue llegando
  // mucho antes de que el desconcierto cueste una consulta al soporte.
  window.setInterval(checkBuild, 60000);

  // Un solo vigilante mantiene la pantalla viva: cuando el estado de la
  // memoria cambia —termina un indexado, se borra un archivo— repinta lo que
  // esté abierto, en vez de dejar datos viejos hasta que alguien actualice.
  //
  // Configuración se queda FUERA a propósito: es la única vista con un
  // formulario, y repintarla por debajo borraría lo que se está escribiendo.
  watchProgress(() => {
    guard(() => renderPanel(goToCategory, goToNemo));
    guard(reloadArchivos);
    // El grafo es la lectura más cara de la pantalla: se repinta si el Panel
    // está delante, y si no se marca para leerlo al volver. Sin `reset`, para
    // no deshacer la entidad de partida ni la disposición que eligió el
    // usuario.
    if (current === 'panel') guard(() => renderGrafo());
    else invalidarGrafo();
    if (current === 'motor') guard(renderMotor);
  });

  // Los iconos que las vistas hayan dejado declarados en su marcado.
  paintIcons();
}

// El módulo se carga diferido, así que el DOM ya está listo; el guardia es
// para el caso de que alguien mueva la etiqueta <script> a la cabecera.
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', start);
} else {
  start();
}
