/* ==========================================================================
   BIMNEMO — Vista Motor
   La configuración con la que LightRAG está funcionando ahora, y el estado
   vivo del pipeline de ingesta.
   ========================================================================== */

import { getEngine, getPipelineStatus } from './api.js';
import { allNemos, currentNemo } from './nemo.js';
import { icon } from './icons.js';
import { doRestart } from './configuracion-reinicio.js';
import { count, escape } from './format.js';

/** Fila de lista de definición, con «—» cuando el valor no está. */
function row(term, value) {
  const shown =
    value === null || value === undefined || value === ''
      ? '—'
      : String(value);
  return `<dt>${escape(term)}</dt><dd>${escape(shown)}</dd>`;
}

function monoRow(term, value) {
  const shown = value === null || value === undefined || value === '' ? '—' : String(value);
  return `<dt>${escape(term)}</dt><dd class="mono">${escape(shown)}</dd>`;
}

function yesNo(value) {
  if (value === true) return 'Sí';
  if (value === false) return 'No';
  return '—';
}

function card(title, iconName, inner, hint = '') {
  return `
    <div class="card">
      <div class="card__head">
        <span class="card__title">${icon(iconName, 14)}${escape(title)}</span>
        ${hint ? `<span class="card__hint">${escape(hint)}</span>` : ''}
      </div>
      <div class="card__body">${inner}</div>
    </div>`;
}

/**
 * Aviso cuando el motor no puede responder.
 *
 * Es el fallo más común al estrenar la instalación: LightRAG arranca sin
 * proveedor de LLM ni de embeddings, el panel se ve entero y el chat falla.
 * Decirlo aquí, con el nombre de las variables que faltan, ahorra el paseo
 * por los registros.
 */
function readiness(engine) {
  const missing = [];
  for (const [rotulo, prefijo, config] of [
    ['modelo de lenguaje', 'LLM', engine.llm],
    ['embeddings', 'EMBEDDING', engine.embedding],
  ]) {
    if (config.host === '(sin definir)' && !config.api_key_set) {
      missing.push(`${prefijo}_BINDING_HOST o ${prefijo}_BINDING_API_KEY (${rotulo})`);
    } else if (!config.api_key_set && !isLocalHost(config.host)) {
      // Un host remoto sin clave falla en la primera llamada. Es el caso más
      // común al estrenar: el .env copiado trae el host de OpenAI y la clave
      // se queda sin poner.
      missing.push(`${prefijo}_BINDING_API_KEY (${rotulo}, el host es remoto)`);
    }
  }
  if (!missing.length) return '';

  return `
    <div class="notice notice--warn">
      <span class="notice__icon">${icon('triangle-alert', 14)}</span>
      <span>
        El motor no está listo para responder: la ingesta y el chat fallarán.
        Falta por definir en el <code>.env</code>:
        <strong>${escape(missing.join(' · '))}</strong>.
      </span>
    </div>`;
}

/**
 * ¿Apunta este host a la propia máquina?
 *
 * Un proveedor local (Ollama, LM Studio, vLLM) no pide clave; uno remoto sí.
 * La distinción decide si la ausencia de clave es un aviso o es normal.
 */
function isLocalHost(host) {
  const value = String(host || '').toLowerCase();
  return (
    value.includes('localhost') ||
    value.includes('127.0.0.1') ||
    value.includes('0.0.0.0') ||
    value.includes('host.docker.internal') ||
    value.includes('://192.168.') ||
    value.includes('://10.')
  );
}

function pipelineCard(status) {
  if (!status) {
    return card(
      'Pipeline de ingesta',
      'refresh-cw',
      '<p class="card__hint">Estado no disponible.</p>'
    );
  }

  const busy = Boolean(status.busy);
  const inner = `
    <dl class="deflist">
      ${row('Estado', busy ? 'Trabajando' : 'En reposo')}
      ${row('Tarea', status.job_name || '—')}
      ${row('Progreso', status.job_start ? `${count(status.cur_batch ?? 0)} / ${count(status.batchs ?? 0)}` : '—')}
      ${row('Documentos en curso', count(status.docs ?? 0))}
      ${row('Petición de parada', yesNo(status.request_pending))}
    </dl>
    ${
      Array.isArray(status.history_messages) && status.history_messages.length
        ? `<pre class="codeblock">${escape(status.history_messages.slice(-8).join('\n'))}</pre>`
        : ''
    }`;

  return card('Pipeline de ingesta', 'refresh-cw', inner, busy ? 'Trabajando' : 'En reposo');
}

/** Pinta la vista Motor entera. */
export async function renderMotor() {
  const body = document.getElementById('engine-body');
  body.innerHTML = `<p class="card__hint">Leyendo la configuración…</p>`;

  let engine;
  try {
    engine = await getEngine(currentNemo());
  } catch (error) {
    body.innerHTML = `
      <div class="notice notice--error">
        <span class="notice__icon">${icon('triangle-alert', 14)}</span>
        <span>No se pudo leer la configuración del motor: ${escape(
          error.detail || error.message
        )}</span>
      </div>`;
    return null;
  }

  let pipeline = null;
  try {
    pipeline = await getPipelineStatus();
  } catch {
    // El estado del pipeline es accesorio aquí: su ausencia no debe impedir
    // ver la configuración, que es lo que se viene a mirar.
  }

  body.innerHTML = `
    ${readiness(engine)}
    ${memoriasCard(engine)}

    ${card(
      'Identidad',
      'zap',
      `<dl class="deflist">
        ${row(
          'Producto',
          `${engine.product.name} ${engine.product.version}` +
            (engine.product.build ? ` · ${engine.product.build}` : '')
        )}
        ${row('Motor', `${engine.product.engine} ${engine.product.engine_version}`)}
        ${row('Espacio de trabajo', engine.workspace || '(por defecto)')}
        ${monoRow('Directorio de datos', engine.working_dir)}
        ${monoRow('Directorio de entrada', engine.input_dir)}
      </dl>`
    )}

    <div class="split">
      ${card(
        'Modelo de lenguaje',
        'message-square',
        `<dl class="deflist">
          ${row('Modelo', engine.llm.model)}
          ${row('Proveedor', engine.llm.binding)}
          ${monoRow('Host', engine.llm.host)}
          ${row('Clave de API', engine.llm.api_key_set ? 'Configurada' : 'Sin configurar')}
          ${row('Concurrencia', engine.llm.max_async)}
          ${row('Caché de respuestas', yesNo(engine.llm.cache_enabled))}
          ${row('Tokens de resumen', engine.llm.summary_max_tokens)}
        </dl>`
      )}

      ${card(
        'Embeddings',
        'layers',
        `<dl class="deflist">
          ${row('Modelo', engine.embedding.model)}
          ${row('Proveedor', engine.embedding.binding)}
          ${monoRow('Host', engine.embedding.host)}
          ${row('Clave de API', engine.embedding.api_key_set ? 'Configurada' : 'Sin configurar')}
          ${row('Dimensión', engine.embedding.dim)}
          ${row('Tamaño de lote', engine.embedding.batch_num)}
        </dl>`
      )}
    </div>

    <div class="split">
      ${card(
        'Almacenamiento',
        'database',
        `<dl class="deflist">
          ${monoRow('Clave-valor', engine.storages.kv)}
          ${monoRow('Vectores', engine.storages.vector)}
          ${monoRow('Grafo', engine.storages.graph)}
          ${monoRow('Estado de documentos', engine.storages.doc_status)}
        </dl>
        ${storageWarning(engine.storages)}`
      )}

      ${card(
        'Troceado y consulta',
        'scissors-line-dashed',
        `<dl class="deflist">
          ${row('Estrategia', engine.chunking.chunker)}
          ${row('Tamaño de fragmento', engine.chunking.chunk_token_size)}
          ${row('Solapamiento', engine.chunking.overlap_token_size)}
          ${row('Inserciones en paralelo', engine.chunking.max_parallel_insert)}
          ${row('top_k por defecto', engine.query_defaults.top_k)}
          ${row('Umbral de coseno', engine.query_defaults.cosine_threshold)}
          ${row('Reordenador', engine.query_defaults.rerank_enabled
            ? engine.query_defaults.rerank_binding
            : 'Desactivado')}
        </dl>`
      )}
    </div>

    ${pipelineCard(pipeline)}
    ${reinicioCard()}`;

  montarReinicio();
  return engine;
}

/**
 * Reiniciar el motor, desde la pantalla que lo describe.
 *
 * Hasta ahora el reinicio solo aparecía **después de guardar un cambio**, y
 * hay razones legítimas para querer reiniciar sin haber tocado nada: el motor
 * se atasca, un proveedor deja de responder. La alternativa era cerrar la
 * ventana y volver a abrir BIMNEMO.
 *
 * Va en rojo porque de todo lo que hay en esta pantalla es lo único que
 * **interrumpe**: corta lo que esté en curso y deja la aplicación sin motor
 * unos segundos. No borra nada, pero no es inocuo.
 */
function reinicioCard() {
  return card(
    'Reiniciar el motor',
    'refresh-cw',
    `<p class="motor-reinicio__texto">
       El motor construye los modelos de lenguaje y de embeddings al arrancar,
       así que un cambio de proveedor —o un proceso que se ha quedado
       atascado— solo se resuelve levantándolo de nuevo. Tarda unos segundos y
       la ventana se recarga sola al volver.
     </p>
     <p class="motor-reinicio__texto card__hint">
       <strong>No borra nada.</strong> Sí corta lo que esté indexando, así que
       si hay trabajo en curso el motor se negará y lo dirá.
     </p>
     <div id="motor-restart-notice"></div>
     <button type="button" class="btn btn--peligro" id="btn-restart-motor">
       ${icon('refresh-cw', 13)} Reiniciar motor LightRAG
     </button>`,
    'Corta lo que esté en curso',
  );
}

function montarReinicio() {
  document
    .getElementById('btn-restart-motor')
    ?.addEventListener('click', () =>
      doRestart({
        // Un 409 «está indexando» tiene que salir aquí: pintado en el banner
        // de Configuración, el botón parecería no hacer nada.
        avisar: (html) => {
          const hueco = document.getElementById('motor-restart-notice');
          if (hueco) hueco.innerHTML = html;
        },
        boton: 'btn-restart-motor',
      }),
    );
}

/**
 * Qué memoria describe esta ficha y cuáles están abiertas.
 *
 * Hace falta porque el resto de la vista habla de UNA memoria, y sin decir
 * cuál, los almacenes y el espacio de trabajo que se leen abajo parecerían
 * globales. La configuración de modelos sí es común a todas: eso se dice en
 * la pestaña Configuración, que es donde se cambia.
 */
function memoriasCard(engine) {
  const info = engine.nemos || {};
  const vivas = info.live || [];
  const nombre = (id) => allNemos().find((n) => n.id === id)?.name || id || 'General';

  return card(
    'Memorias',
    'library',
    `<dl class="deflist">
      ${row('Esta ficha describe', info.name || 'General')}
      ${row('Memorias registradas', info.total ?? 1)}
      ${row(
        'Abiertas ahora',
        vivas.length ? vivas.map(nombre).join(' · ') : 'ninguna'
      )}
    </dl>
    <div class="notice notice--info">
      <span class="notice__icon">${icon('info', 14)}</span>
      <span>
        Los almacenes y el directorio de abajo son de <strong>esta</strong>
        memoria. El modelo de lenguaje y el de embeddings son comunes a todas.
      </span>
    </div>`,
    vivas.length ? `${vivas.length} abierta(s)` : 'todas en reposo'
  );
}

/**
 * Aviso sobre los almacenes de fichero.
 *
 * No es una opinión: la documentación del propio LightRAG marca estos cinco
 * backends como «small-scale testing and validation only», porque cada commit
 * reescribe el fichero entero del espacio de nombres. Son los que vienen por
 * defecto, así que quien no lo sepa se lo encuentra en producción.
 */
function storageWarning(storages) {
  const fileBacked = [
    'JsonKVStorage',
    'JsonDocStatusStorage',
    'NetworkXStorage',
    'NanoVectorDBStorage',
    'FaissVectorDBStorage',
  ];
  const inUse = Object.values(storages).filter((s) => fileBacked.includes(s));
  if (!inUse.length) return '';

  return `
    <div class="notice notice--info">
      <span class="notice__icon">${icon('info', 14)}</span>
      <span>
        Estás usando almacenes respaldados por fichero. LightRAG los declara
        para pruebas y validación a pequeña escala: cada confirmación reescribe
        el fichero completo. Para un volumen serio, cambia a PostgreSQL o a
        Neo4j + Qdrant en el <code>.env</code>.
      </span>
    </div>`;
}
