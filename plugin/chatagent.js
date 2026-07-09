/**
 * ChatAgent — Plugin de API-IDEE para asistente IA.
 *
 * Sigue el patron estandar de plugins API-IDEE:
 *   - Clase plana con constructor(options) y addTo(map)
 *   - Usa IDEE.ui.Panel + IDEE.Control + IDEE.impl.Control
 *   - CSS en fichero separado (chatagent.css)
 *   - Se registra en IDEE.plugin.ChatAgent
 */

/* =========================================================================
   Ejecutor de herramientas — asocia nombres de herramientas a llamadas de IDEE.Map
   ========================================================================= */

var CHATAGENT_TOOL_MAP = {
  /** Devuelve el centro actual del mapa.
    @param {IDEE.Map} map Mapa activo.
    @returns {{lat: number, lon: number, srs: string}} Objeto con latitud, longitud y SRS. */
  getMapCenter: function(map) {
    var center = map.getCenter();
    return { lat: center.y, lon: center.x, srs: map.getProjection().code };
  },
  /** Devuelve el nivel de zoom actual del mapa.
    @param {IDEE.Map} map Mapa activo.
    @returns {{level: number}} Nivel de zoom. */
  getCurrentZoom: function(map) {
    return { level: map.getZoom() };
  },
  /** Lista las capas activas del mapa con su nombre, tipo, visibilidad y leyenda.
    @param {IDEE.Map} map Mapa activo.
    @returns {Array<{name: string, type: string, visible: boolean, legend: string}>} Lista de capas. */
  listActiveLayers: function(map) {
    var layers = map.getLayers();
    return layers.map(function(layer) {
      return {
        name: layer.name || '',
        type: layer.type || '',
        visible: layer.isVisible ? layer.isVisible() : true,
        legend: layer.legend || '',
      };
    });
  },
  /** Devuelve la extensión geográfica actual del mapa.
    @param {IDEE.Map} map Mapa activo.
    @returns {{minX: number, minY: number, maxX: number, maxY: number, srs: string}} Extensión del mapa. */
  getMapExtent: function(map) {
    var bbox = map.getBbox();
    return {
      minX: bbox.x.min,
      minY: bbox.y.min,
      maxX: bbox.x.max,
      maxY: bbox.y.max,
      srs: map.getProjection().code,
    };
  },
  /** Añade cualquier tipo de capa al mapa (WMS, WMTS, WFS, GeoJSON, KML, XYZ, MVT, TMS, OGCAPIFeatures).
    @param {IDEE.Map} map Mapa activo.
    @param {{type: string, url?: string, name?: string, legend?: string, transparent?: boolean, tiled?: boolean, format?: string, style?: string, data?: string, matrixSet?: string, version?: string}} args Parámetros de la capa.
    @returns {{success: boolean, name?: string, type?: string, error?: string}} Resultado de la operación. */
  addLayer: function(map, args) {
    var type = (args.type || '').toUpperCase();
    var legend = args.legend || args.name || type;
    if (!args.name && type !== 'GEOJSON') args.name = legend;

    var addedLayer;

    switch (type) {
      case 'WMS':
        addedLayer = new IDEE.layer.WMS({
          url: args.url,
          name: args.name,
          legend: legend,
          transparent: args.transparent !== undefined ? args.transparent : true,
          tiled: args.tiled !== undefined ? args.tiled : false,
        });
        break;

      case 'WMTS':
        addedLayer = new IDEE.layer.WMTS({
          url: args.url,
          name: args.name,
          legend: legend,
          style: args.style || 'default',
          format: args.format || 'image/png',
          matrixSet: args.matrixSet,
        });
        break;

      case 'WFS':
        addedLayer = new IDEE.layer.WFS({
          url: args.url,
          name: args.name,
          legend: legend,
          version: args.version || '2.0.0',
        });
        break;

      case 'GEOJSON':
        var geojsonOpts = { name: legend, legend: legend };
        if (args.url) {
          geojsonOpts.url = args.url;
        } else if (args.data) {
          if (typeof args.data === 'object' && args.data !== null) {
            geojsonOpts.source = args.data;
          } else {
            try {
              geojsonOpts.source = JSON.parse(args.data);
            } catch (e) {
              return { success: false, error: 'GeoJSON data no válido: ' + e.message };
            }
          }
        } else {
          return { success: false, error: 'Se requiere url o data para GeoJSON' };
        }
        addedLayer = new IDEE.layer.GeoJSON(geojsonOpts);
        break;

      case 'KML':
        map.addKML(args.url, legend);
        break;

      case 'XYZ':
        map.addLayers([new IDEE.layer.XYZ({
          url: args.url,
          name: legend,
          legend: legend,
        })]);
        break;

      case 'MVT':
        map.addMVT({
          url: args.url,
          name: legend,
          legend: legend,
        });
        break;

      case 'TMS':
        map.addTMS({
          url: args.url,
          name: legend,
          legend: legend,
        });
        break;

      case 'OGCAPIFEATURES':
        map.addOGCAPIFeatures({
          url: args.url,
          name: legend,
          legend: legend,
        });
        break;

      default:
        return { success: false, error: 'Unsupported layer type: ' + type };
    }

    if (addedLayer) {
      map.addLayers([addedLayer]);
      if (args.fit) {
        var fitHandler = function() {
          if (typeof addedLayer.getMaxExtent === 'function') {
            var extent = addedLayer.getMaxExtent();
            if (extent && Array.isArray(extent) && extent.length === 4) {
              var minX = extent[0], minY = extent[1], maxX = extent[2], maxY = extent[3];
              if (type === 'GEOJSON' && args.data) {
                var p4 = window.proj4 || (IDEE && IDEE.proj4);
                if (p4) {
                  try {
                    var sw = p4('EPSG:4326', 'EPSG:3857', [minX, minY]);
                    var ne = p4('EPSG:4326', 'EPSG:3857', [maxX, maxY]);
                    minX = sw[0]; minY = sw[1]; maxX = ne[0]; maxY = ne[1];
                  } catch(e) {
                    console.warn('proj4 falló:', e);
                  }
                }
              }
              try { map.setBbox({ x: { min: minX, max: maxX }, y: { min: minY, max: maxY } }); } catch (e) { console.error('setBbox error:', e); }
            }
          }
        };
        addedLayer.on(IDEE.evt.LOAD, fitHandler);
        // Fallback: si LOAD ya se disparó antes de registrar el manejador, intentar fit
        setTimeout(fitHandler, 3000);
      }
    }
    return { success: true, name: args.name || legend, type: type };
  },
  /** Centra el mapa en las coordenadas dadas, transformando al SRS del mapa si es necesario.
    @param {IDEE.Map} map Mapa activo.
    @param {{lon: number, lat: number, zoom?: number, srs?: string}} args Coordenadas y zoom.
    @returns {{success: boolean, srs?: string}} Resultado. */
  zoomTo: function(map, args) {
    var x = args.lon;
    var y = args.lat;
    var srcSrs = args.srs || 'EPSG:4326';
    var dstSrs = map.getProjection ? map.getProjection().code : 'EPSG:3857';

    if (srcSrs !== dstSrs) {
      try {
        var transformed = ol.proj.transform([x, y], srcSrs, dstSrs);
        x = transformed[0];
        y = transformed[1];
      } catch (e) {
        return { success: false, error: 'Coordinate transformation failed: ' + e.message };
      }
    }

    map.setCenter({ x: x, y: y });
    if (args.zoom !== undefined) {
      map.setZoom(args.zoom);
    }
    return { success: true, srs: dstSrs };
  },
  /** Ajusta la vista del mapa al extent (bbox) dado, transformando al SRS del mapa.
    @param {IDEE.Map} map Mapa activo.
    @param {{minLon: number, minLat: number, maxLon: number, maxLat: number}} args Bounding box en EPSG:4326.
    @returns {{success: boolean, srs?: string, error?: string}} Resultado. */
  zoomToExtent: function(map, args) {
    var dstSrs = map.getProjection ? map.getProjection().code : 'EPSG:3857';
    var extent = [args.minLon, args.minLat, args.maxLon, args.maxLat];
    var srcSrs = 'EPSG:4326';

    if (srcSrs !== dstSrs) {
      try {
        extent = ol.proj.transformExtent(extent, srcSrs, dstSrs);
      } catch (e) {
        try {
          var bl = ol.proj.transform([extent[0], extent[1]], srcSrs, dstSrs);
          var tr = ol.proj.transform([extent[2], extent[3]], srcSrs, dstSrs);
          extent = [bl[0], bl[1], tr[0], tr[1]];
        } catch (e2) {
          return { success: false, error: 'Coordinate transformation failed: ' + e2.message };
        }
      }
    }

    try {
      map.setBbox({ x: { min: extent[0], max: extent[2] }, y: { min: extent[1], max: extent[3] } });
    } catch (e) {
      var cx = (extent[0] + extent[2]) / 2;
      var cy = (extent[1] + extent[3]) / 2;
      map.setCenter({ x: cx, y: cy });
      map.setZoom(10);
    }
    return { success: true, srs: dstSrs };
  },
  /** Elimina una capa del mapa por su nombre.
    @param {IDEE.Map} map Mapa activo.
    @param {{name: string}} args Nombre de la capa a eliminar.
    @returns {{success: boolean, name?: string, error?: string}} Resultado. */
  removeLayer: function(map, args) {
    var layers = map.getLayers();
    var target = layers.find(function(l) { return l.name === args.name; });
    if (target) {
      map.removeLayers([target]);
      return { success: true, name: args.name };
    }
    return { success: false, error: 'Layer not found: ' + args.name };
  },
  /** Establece el nivel de zoom del mapa.
    @param {IDEE.Map} map Mapa activo.
    @param {{level: number}} args Nivel de zoom.
    @returns {{success: boolean, level: number}} Resultado. */
  setZoom: function(map, args) {
    map.setZoom(args.level);
    return { success: true, level: args.level };
  },
};

/** Ejecuta una herramienta del mapa por su nombre.
    @param {IDEE.Map} map Mapa activo.
    @param {string} toolName Nombre de la herramienta.
    @param {Object} [args] Argumentos opcionales.
    @returns {{success: boolean, error?: string, ...*}} Resultado de la ejecución. */
function chatagentExecuteTool(map, toolName, args) {
  var executor = CHATAGENT_TOOL_MAP[toolName];
  if (!executor) {
    return { success: false, error: 'Unknown tool: ' + toolName };
  }
  try {
    return executor(map, args || {});
  } catch (err) {
    console.error('Tool execution error (' + toolName + '):', err);
    return { success: false, error: err.message || String(err) };
  }
}

/** Acumulador de features GeoJSON por nombre de capa.
    Clave = nombre de capa (ej: ``AGENT_MRE_Piscinas``), valor = array de features.
    Se usa para el protocolo de append: si la capa ya existe, se añaden las nuevas
    features en lugar de sustituir la capa completa. */
var CHATAGENT_ACCUMULATED_FEATURES = {};

/** Renderiza candidatos del geocoder en el chat como botones clicables.
    Cada boton carga el GeoJSON directamente desde su ``geojsonURL``.
    @param {Array<Object>} candidates Lista de candidatos con geojsonURL.
    @param {string} query Texto de la busqueda original. */
function chatagentRenderGeocodingCandidates(candidates, query) {
  if (!candidates || candidates.length === 0) return '';
  var html = '<div class="chatagent-candidates">';
  var currentType = '';
  for (var i = 0; i < candidates.length; i++) {
    var c = candidates[i];
    var ctype = c.type || '';
    if (ctype !== currentType) {
      currentType = ctype;
      html += '<div class="chatagent-candidates-group-title">' + chatagentEscapeHtml(ctype.charAt(0).toUpperCase() + ctype.slice(1)) + '</div>';
    }
    var addr = c.address || 'Sin dirección';
    var name = c.address || c.id || addr;
    var url = c.geojsonURL || '';
    html += '<button class="candidate-btn" onclick="chatagentQuickReply('
         + "'" + chatagentEscapeHtml(addr).replace(/'/g, "\\'") + "', "
         + "'" + chatagentEscapeHtml(url).replace(/'/g, "\\'") + "', "
         + "'" + chatagentEscapeHtml(name).replace(/'/g, "\\'") + "'"
         + ')">' + chatagentEscapeHtml(addr) + '</button>';
  }
  html += '</div>';
  return html;
}

/** Añade una capa GeoJSON al mapa o, si ya existe una capa con ese nombre,
    añade las nuevas features a la fuente existente (protocolo de append).
    @param {IDEE.Map} map Mapa activo.
    @param {string} layerName Nombre fijo de la capa.
    @param {Object} geojsonSource GeoJSON FeatureCollection a añadir.
    @param {Object} [styleOpts] Opciones de estilo IDEE.style.Generic (opcional). */
function chatagentAddOrAppendGeoJSON(map, layerName, geojsonSource, styleOpts) {
  var newFeatures = (geojsonSource && geojsonSource.features) || [];
  if (newFeatures.length === 0) return;

  // Inicializar acumulador si es primera vez
  if (!CHATAGENT_ACCUMULATED_FEATURES[layerName]) {
    CHATAGENT_ACCUMULATED_FEATURES[layerName] = [];
  }

  // Acumular IDs para evitar duplicados
  var existingIds = {};
  CHATAGENT_ACCUMULATED_FEATURES[layerName].forEach(function(f) {
    if (f.id !== undefined && f.id !== null) existingIds[f.id] = true;
  });

  newFeatures.forEach(function(f) {
    if (f.id !== undefined && f.id !== null && existingIds[f.id]) return;
    CHATAGENT_ACCUMULATED_FEATURES[layerName].push(f);
  });

  // Buscar capa existente en el mapa
  var existingLayer = null;
  var layers = map.getLayers();
  for (var i = 0; i < layers.length; i++) {
    if (layers[i].name === layerName) {
      existingLayer = layers[i];
      break;
    }
  }

  // Eliminar capa anterior si existe
  if (existingLayer) {
    try { map.removeLayers([existingLayer]); } catch (e) { /* ignorar */ }
  }

  // Crear nueva capa con todas las features acumuladas
  var mergedSource = {
    type: 'FeatureCollection',
    features: CHATAGENT_ACCUMULATED_FEATURES[layerName],
  };
  var gOpts = { name: layerName, legend: layerName, source: mergedSource };
  var gLayer = new IDEE.layer.GeoJSON(gOpts);
  if (styleOpts) {
    gLayer.setStyle(new IDEE.style.Generic(styleOpts));
  }
  map.addLayers([gLayer]);
}

/** Envia un mensaje de seleccion rapida del usuario al chat, o carga una capa
    GeoJSON directamente si se proporciona ``geojsonUrl``.
    Llamado desde botones/links HTML renderizados por el LLM en cualquier contexto
    donde el usuario deba elegir entre opciones (candidatos de geocodificacion,
    capas, acciones, etc.).
    @param {string} text Texto visible del mensaje o nombre de capa.
    @param {string} [geojsonUrl] URL del GeoJSON a cargar (opcional).
    @param {string} [layerName] Nombre para la capa (opcional, usa text por defecto). */
window.chatagentQuickReply = function(text, geojsonUrl, layerName) {
  var inst = window.__chatagentPlugin;
  if (!inst || !text) return;
  if (geojsonUrl) {
    var name = layerName || text;
    var gLayer = new IDEE.layer.GeoJSON({
      name: name,
      legend: name,
      url: geojsonUrl,
    });
    gLayer.on(IDEE.evt.LOAD, function () {
      try {
        var extent = gLayer.getFeaturesExtent();
        if (extent) inst.map_.setBbox({ x: { min: extent[0], max: extent[2] }, y: { min: extent[1], max: extent[3] } });
      } catch (e) {
        console.warn('Could not zoom to layer:', e);
      }
    });
    inst.map_.addLayers([gLayer]);
    inst._appendMessage('system', '✓ Capa cargada: ' + name);
  } else {
    inst._sendMessage(text);
  }
};

/** Escapa caracteres HTML en una cadena para prevenir XSS.
    @param {string} unsafe Cadena sin escapar.
    @returns {string} Cadena escapada. */
function chatagentEscapeHtml(unsafe) {
  return unsafe
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/** Sanitiza HTML manteniendo solo tags y atributos seguros (allowlist).
    Elimina scripts, event handlers (on*) e inyecciones de estilo peligrosas.
    @param {string} html HTML sin sanitizar.
    @returns {string} HTML seguro. */
function chatagentSanitizeHtml(html) {
  var ALLOWED_TAGS = [
    'p', 'br', 'b', 'i', 'em', 'strong', 'a', 'ul', 'ol', 'li',
    'code', 'pre', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'span', 'div', 'table', 'thead', 'tbody', 'tr', 'td', 'th',
    'details', 'summary', 'hr', 'sup', 'sub', 'mark',
  ];
  var ALLOWED_ATTRS = ['href', 'title', 'class', 'id', 'target', 'colspan', 'rowspan', 'onclick', 'data-geojson-url', 'data-id'];

  var tmp = document.createElement('div');
  tmp.innerHTML = html;

  function walk(node) {
    var children = Array.prototype.slice.call(node.childNodes);
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child.nodeType === 1) { // Elemento
        var tag = child.tagName.toLowerCase();
        if (ALLOWED_TAGS.indexOf(tag) === -1) {
          // Reemplazar el elemento prohibido por su contenido de texto
          while (child.firstChild) {
            node.insertBefore(child.firstChild, child);
          }
          node.removeChild(child);
          continue;
        }
        // Eliminar atributos no permitidos y event handlers
        var attrs = Array.prototype.slice.call(child.attributes);
        for (var j = 0; j < attrs.length; j++) {
          var attrName = attrs[j].name.toLowerCase();
          if (ALLOWED_ATTRS.indexOf(attrName) === -1) {
            child.removeAttribute(attrs[j].name);
          } else if (attrName === 'href') {
            var val = (child.getAttribute('href') || '').trim().toLowerCase();
            if (val.indexOf('javascript:') === 0 || val.indexOf('data:') === 0) {
              child.removeAttribute('href');
            }
          } else if (attrName === 'onclick') {
            // Solo permitir chatagentQuickReply en onclick
            var onclickVal = child.getAttribute('onclick') || '';
            if (onclickVal.indexOf('chatagentQuickReply') === -1) {
              child.removeAttribute('onclick');
            }
          }
        }
        walk(child);
      }
      // Text nodes (nodeType 3) se mantienen tal cual
    }
  }

  walk(tmp);
  return tmp.innerHTML;
}

/* =========================================================================
   Clase del plugin
   ========================================================================= */

var CHATAGENT_STORAGE_KEY = 'chatagent_user_keys';

/** Plugin de API-IDEE que integra un asistente IA conversacional. */
class ChatAgent {
  /** @param {Object} options Opciones de configuracion (backendUrl, position, etc.). */
  constructor(options) {
    this.name = 'ChatAgent';
    this.options = options || {};
    this.options.position = this.options.position || 'TR';
    this.options.collapsible = this.options.collapsible !== undefined ? this.options.collapsible : true;
    this.options.collapsed = this.options.collapsed !== undefined ? this.options.collapsed : true;
    this.options.backendUrl = this.options.backendUrl || 'http://localhost:8000/api';
    this.options.tooltip = this.options.tooltip || 'Asistente API-IDEE';
    this.options.placeholder = this.options.placeholder || 'Pregunta sobre API-IDEE...';
    this.options.welcomeMessage = this.options.welcomeMessage || null;
    this.options.stream = this.options.stream !== undefined ? this.options.stream : false;
    this.options.maxConversations = this.options.maxConversations || 10;

    // Estado
    this.map_ = null;
    this.panel_ = null;
    this.control_ = null;
    this.conversationId = null;
    this.providers = [];
    this.conversationIds = [];

    // Referencias al DOM (cacheadas en _onActivate)
    this.messagesContainer = null;
    this.inputElement = null;
    this.loadingEl = null;
    this.sendBtn = null;
    this.providerSelect = null;
    this.modelSelect = null;
    this.settingsToggle = null;
    this.settingsPanel = null;
    this.historyToggle = null;
    this.historyPanel = null;
    this.historyList = null;
    this.newConversationBtn = null;
    this.settingsProv = null;
    this.settingsSave = null;
    this.connTest = null;
    this.apiKeyToggle = null;
    this.apiKeyInput = null;
    this.keyNameInput = null;
    this.testResult = null;
    this.storedKeys = null;

    // Proveedor/modelo seleccionado de la barra
    this.selectedProvider = null;
    this.selectedModel = null;

    // Entradas guardadas por el usuario: [{ id, name, provider, apiKey }]
    this.userEntries = [];
    this._loadUserEntries();
  }

  /** Devuelve la ayuda del plugin con titulo y contenido HTML.
    @returns {{title: string, content: Promise}} Objeto con titulo y promesa del contenido. */
  getHelp() {
    return {
      title: 'Asistente API-IDEE',
      content: new Promise(function(success) {
        var html = '<div><p>Asistente IA para consultar y controlar el visor de mapas API-IDEE.</p></div>';
        html = IDEE.utils.stringToHtml(html);
        success(html);
      }),
    };
  }

  /* ------------------------------------------------------------------
     Persistencia de entradas de usuario (localStorage)
     ------------------------------------------------------------------ */

  /** Carga las entradas de usuario (claves guardadas) desde localStorage. */
  _loadUserEntries() {
    try {
      var raw = localStorage.getItem(CHATAGENT_STORAGE_KEY);
      if (raw) {
        this.userEntries = JSON.parse(raw);
      }
    } catch (e) {
      this.userEntries = [];
    }
    if (!Array.isArray(this.userEntries)) {
      this.userEntries = [];
    }
  }

  /** Guarda las entradas de usuario en localStorage. */
  _saveUserEntries() {
    try {
      localStorage.setItem(CHATAGENT_STORAGE_KEY, JSON.stringify(this.userEntries));
    } catch (e) {
      console.error('Error saving entries to localStorage:', e);
    }
  }

  /** Busca una entrada de usuario guardada por su ID.
    @param {string} id Identificador de la entrada.
    @returns {Object|null} Entrada encontrada o null. */
  _findEntryById(id) {
    return this.userEntries.find(function(e) { return e.id === id; }) || null;
  }

  /* ------------------------------------------------------------------
     Historial de conversaciones
     ------------------------------------------------------------------ */

  /** Carga los IDs de conversacion desde localStorage. */
  _loadConversationIds() {
    try {
      var raw = localStorage.getItem('chatagent_conversations');
      if (raw) {
        this.conversationIds = JSON.parse(raw);
      }
    } catch (e) {
      this.conversationIds = [];
    }
    if (!Array.isArray(this.conversationIds)) {
      this.conversationIds = [];
    }
  }

  /** Guarda los IDs de conversacion en localStorage. */
  _saveConversationIds() {
    try {
      localStorage.setItem('chatagent_conversations', JSON.stringify(this.conversationIds));
    } catch (e) {
      console.error('Error saving conversation IDs to localStorage:', e);
    }
  }

  /** Añade un ID de conversacion, recorta el array al maximo y guarda.
    @param {string} id ID de la nueva conversacion. */
  _addConversationId(id) {
    if (!id) return;
    // Eliminar si ya existe para moverlo al principio
    var index = this.conversationIds.indexOf(id);
    if (index > -1) {
      this.conversationIds.splice(index, 1);
    }
    // Añadir al principio
    this.conversationIds.unshift(id);
    // Recortar al tamaño maximo
    if (this.conversationIds.length > this.options.maxConversations) {
      this.conversationIds.length = this.options.maxConversations;
    }
    this._saveConversationIds();
  }

  /** Elimina un ID de conversacion y guarda.
    @param {string} id ID de la conversacion a eliminar. */
  _removeConversationId(id) {
    this.conversationIds = this.conversationIds.filter(function(savedId) {
      return savedId !== id;
    });
    this._saveConversationIds();
  }

  /** Elimina una conversacion en el backend y del historial local.
    @param {string} id ID de la conversacion a eliminar.
    @param {Element} item Elemento DOM del item a eliminar. */
  async _deleteConversation(id, item) {
    try {
      var res = await fetch(this.options.backendUrl + '/conversations/' + id + '/', {
        method: 'DELETE',
      });
      if (!res.ok && res.status !== 404) throw new Error('HTTP ' + res.status);
      item.remove();
      this._removeConversationId(id);
      if (this.historyList && this.historyList.children.length === 0) {
        this.historyList.innerHTML = '<div class="chatagent-history-empty">No hay conversaciones guardadas</div>';
      }
    } catch (error) {
      console.error('Error deleting conversation:', error);
      this._appendMessage('system', 'Error al eliminar la conversación. Comprueba que el servidor está en marcha.');
    }
  }

  /** Alterna la visibilidad del panel de historial. */
  _toggleHistory() {
    if (!this.historyPanel) return;
    var isOpen = this.historyPanel.classList.toggle('open');
    if (this.historyToggle) {
      this.historyToggle.classList.toggle('active', isOpen);
    }
    if (isOpen) {
      // Cerrar panel de ajustes si esta abierto
      if (this.settingsPanel && this.settingsPanel.classList.contains('open')) {
        this.settingsPanel.classList.remove('open');
      }
      this._loadHistory();
    }
  }

  /** Obtiene la configuracion de conversaciones del servidor. */
  async _fetchConversationConfig() {
    try {
      var res = await fetch(this.options.backendUrl + '/conversation-config/');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var config = await res.json();
      this.options.maxConversations = config.max_per_client || this.options.maxConversations;
    } catch (error) {
      console.error('Error fetching conversation config:', error);
    }
  }

  /** Carga la lista de conversaciones desde el backend y la renderiza. */
  async _loadHistory() {
    if (!this.historyList || this.conversationIds.length === 0) {
        if (this.historyList) this.historyList.innerHTML = '<div class="chatagent-history-empty">No hay conversaciones guardadas</div>';
        return;
    }

    this.historyList.innerHTML = '<div class="chatagent-history-loading">Cargando...</div>';

    try {
      var res = await fetch(this.options.backendUrl + '/conversations/by-ids/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: this.conversationIds }),
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var conversations = await res.json();

      // Ordenar conversaciones segun el orden de this.conversationIds
      var sortedConversations = this.conversationIds.map(function(id) {
        return conversations.find(function(c) { return c.id === id; });
      }).filter(Boolean);

      this._renderHistory(sortedConversations);
    } catch (error) {
      console.error('Error loading history:', error);
      if (this.historyList) this.historyList.innerHTML = '<div class="chatagent-history-empty">Error al cargar el historial</div>';
    }
  }

  /** Renderiza la lista de conversaciones en el panel de historial.
    @param {Array<Object>} conversations Lista de objetos de conversacion. */
  _renderHistory(conversations) {
    if (!this.historyList) return;
    if (conversations.length === 0) {
        this.historyList.innerHTML = '<div class="chatagent-history-empty">No hay conversaciones guardadas</div>';
        return;
    }

    var self = this;
    var html = '';
    conversations.forEach(function(conv) {
        var title = conv.title ? conv.title.substring(0, 40) : 'Conversación sin título';
        var date = new Date(conv.created_at);
        // Idealmente usariamos una libreria para fechas relativas, pero para no añadir dependencias, usamos una simple.
        var relativeDate = self._getRelativeDate(date);

        html += '<div class="chatagent-history-item" data-id="' + conv.id + '">'
             +  '<div class="chatagent-history-item-content">'
             +    '<div class="chatagent-history-item-title">' + chatagentEscapeHtml(title) + '</div>'
             +    '<div class="chatagent-history-item-date">' + relativeDate + '</div>'
             +  '</div>'
             +  '<button class="chatagent-history-item-del" title="Eliminar conversación">&times;</button>'
             + '</div>';
    });
    this.historyList.innerHTML = html;

    // Añadir listeners a los items (click en el contenido para cambiar)
    this.historyList.querySelectorAll('.chatagent-history-item').forEach(function(item) {
        var contentEl = item.querySelector('.chatagent-history-item-content');
        if (contentEl) {
            contentEl.addEventListener('click', function() {
                var id = item.getAttribute('data-id');
                self._switchConversation(id);
            });
        }
    });

    // Añadir listeners a los botones de eliminar
    this.historyList.querySelectorAll('.chatagent-history-item-del').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var item = btn.closest('.chatagent-history-item');
            var id = item.getAttribute('data-id');
            self._deleteConversation(id, item);
        });
    });
  }
    _getRelativeDate(date) {
        const now = new Date();
        const diff = now.getTime() - date.getTime();
        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) return `Hace ${days} día(s)`;
        if (hours > 0) return `Hace ${hours} hora(s)`;
        if (minutes > 0) return `Hace ${minutes} minuto(s)`;
        return 'Ahora mismo';
    }


  /** Cambia a una conversacion existente.
    @param {string} id ID de la conversacion a cargar. */
  async _switchConversation(id) {
    if (!id || id === this.conversationId) return;

    this.conversationId = id;
    if (this.messagesContainer) this.messagesContainer.innerHTML = '';
    this._showLoading(true);

    try {
        var res = await fetch(this.options.backendUrl + '/conversations/' + id + '/messages/');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        var messages = await res.json();

        messages.forEach(function(msg) {
            this._appendMessage(msg.role, msg.content, msg.metadata ? msg.metadata.sources : null);
        }, this);

    } catch (error) {
        console.error('Error loading conversation messages:', error);
        this._appendMessage('system', 'Error al cargar los mensajes de la conversación.');
    } finally {
        this._showLoading(false);
        if (this.historyPanel) this.historyPanel.classList.remove('open');
        if (this.historyToggle) this.historyToggle.classList.remove('active');
    }
  }

  /** Inicia una nueva conversacion. */
  _startNewConversation() {
    this.conversationId = null;
    if (this.messagesContainer) this.messagesContainer.innerHTML = '';
    var welcome = this.options.welcomeMessage
        || '<p>Soy el asistente de API-IDEE. Puedo ayudarte con:</p><ul><li>Usar el visor de mapas</li><li>Capas WMS, WMTS, WFS, GeoJSON, KML...</li><li>Desarrollar plugins</li><li>Navegar y buscar en el mapa</li></ul>';
    this._appendMessage('assistant', welcome);
    if (this.historyPanel) this.historyPanel.classList.remove('open');
    if (this.historyToggle) this.historyToggle.classList.remove('active');
  }

  /* ------------------------------------------------------------------
     Ciclo de vida del plugin
     ------------------------------------------------------------------ */

  /** Aniade el plugin al mapa. Crea el panel, el control y monta el HTML del chat.
    @param {IDEE.Map} map Mapa de API-IDEE. */
  addTo(map) {
    var self = this;
    this.map_ = map;
    window.__chatagentPlugin = this;

    var positionMap = {
      'TL': IDEE.ui.position.TL,
      'TR': IDEE.ui.position.TR,
      'BL': IDEE.ui.position.BL,
      'BR': IDEE.ui.position.BR,
    };

    this.panel_ = new IDEE.ui.Panel('chatAgentPanel', {
      collapsible: this.options.collapsible,
      className: 'g-chatagent',
      collapsedButtonClass: 'm-tools',
      position: positionMap[this.options.position] || IDEE.ui.position.TR,
      tooltip: this.options.tooltip,
    });

    // HTML para el panel del chat
    var htmlPanel = ''
      + '<div aria-label="asistente IA" role="menuitem" id="div-contenedor-chatagent" class="m-control m-container m-chatagent-container">'
      +   '<header role="heading" tabindex="0" id="m-chatagent-title" class="m-chatagent-header">'
      +     '<span class="chatagent-header-title">Asistente API-IDEE</span>'
      +     '<button id="chatagent-history-toggle" class="chatagent-history-toggle" title="Historial">&#128340;</button>'
      +     '<button id="chatagent-settings-toggle" class="chatagent-settings-toggle" title="Configuración">&#9881;</button>'
      +   '</header>'
      +   '<section id="m-chatagent-body" class="m-chatagent-body">'
      +     '<div class="chatagent-provider-bar" id="chatagent-provider-bar">'
      +       '<select id="chatagent-provider-select" class="chatagent-select" title="Proveedor IA"></select>'
      +       '<select id="chatagent-model-select" class="chatagent-select" title="Modelo"></select>'
      +     '</div>'
      +     '<div id="chatagent-settings-panel" class="chatagent-settings-panel">'
      +       '<div id="chatagent-stored-keys" class="chatagent-stored-keys"></div>'
      +       '<div class="chatagent-settings-divider"></div>'
      +       '<div class="chatagent-settings-field">'
      +         '<label for="chatagent-key-name">Nombre</label>'
      +         '<input type="text" id="chatagent-key-name" class="chatagent-input" placeholder="Mi API de Groq">'
      +       '</div>'
      +       '<div class="chatagent-settings-field">'
      +         '<label for="chatagent-settings-provider">Proveedor</label>'
      +         '<select id="chatagent-settings-provider" class="chatagent-select"></select>'
      +       '</div>'
      +       '<div class="chatagent-settings-field">'
      +         '<label for="chatagent-api-key">API Key</label>'
      +         '<div class="chatagent-api-key-wrapper">'
      +           '<input type="password" id="chatagent-api-key" class="chatagent-input chatagent-api-key-input" placeholder="sk-..." autocomplete="off">'
      +           '<button id="chatagent-api-key-toggle" class="chatagent-api-key-toggle" title="Mostrar/ocultar API key">&#128065;</button>'
      +         '</div>'
      +         '<div id="chatagent-test-result" class="chatagent-test-result"></div>'
      +       '</div>'
      +       '<div class="chatagent-settings-actions">'
      +         '<button id="chatagent-connection-test" class="chatagent-btn-test">Probar</button>'
      +         '<button id="chatagent-settings-save" class="chatagent-settings-save" disabled>Guardar</button>'
      +       '</div>'
      +     '</div>'
      +     '<div id="chatagent-history-panel" class="chatagent-history-panel">'
      +       '<div class="chatagent-history-header">'
      +         '<span class="chatagent-history-header-title">Historial</span>'
      +         '<button id="chatagent-new-conversation" class="chatagent-btn-new-conversation">+ Nueva</button>'
      +       '</div>'
      +       '<div id="chatagent-history-list" class="chatagent-history-list"></div>'
      +     '</div>'
      +     '<div id="chatagent-messages" class="chatagent-messages"></div>'
      +     '<div class="chatagent-loading" id="chatagent-loading">'
      +       '<div class="dot"></div><div class="dot"></div><div class="dot"></div>'
      +     '</div>'
      +     '<div class="chatagent-input-area">'
      +       '<textarea id="chatagent-input" class="chatagent-input" placeholder="' + chatagentEscapeHtml(this.options.placeholder) + '" rows="1"></textarea>'
      +       '<button id="chatagent-send" class="chatagent-send" title="Enviar"><span>&#10148;</span></button>'
      +     '</div>'
      +   '</section>'
      + '</div>';

    this.control_ = new IDEE.Control(new IDEE.impl.Control(), 'chatAgentControl');

    this.control_.createView = function() {
      var container = document.createElement('div');
      container.style.display = 'none';
      return container;
    };

    this.panel_.addControls(this.control_);
    map.addPanels(this.panel_);

    var panelControls = document.querySelector('.g-chatagent .m-panel-controls');
    if (panelControls) {
      panelControls.innerHTML = htmlPanel;
    }

    IDEE.utils.draggabillyPlugin(this.panel_, '#m-chatagent-title');

    this.control_.activate = function() {
      self._onActivate();
    };

    this.control_.deactivate = function() {
      self._onDeactivate();
    };

    this.control_.activate();
  }

  /* ------------------------------------------------------------------
     Ciclo de vida
     ------------------------------------------------------------------ */

  /** Configura las referencias DOM y los eventos al activarse el control del chat. */
  _onActivate() {
    this.messagesContainer = document.querySelector('#chatagent-messages');
    this.inputElement = document.querySelector('#chatagent-input');
    this.loadingEl = document.querySelector('#chatagent-loading');
    this.sendBtn = document.querySelector('#chatagent-send');
    this.providerSelect = document.querySelector('#chatagent-provider-select');
    this.modelSelect = document.querySelector('#chatagent-model-select');
    // Cargar selección previa desde localStorage (si existe)
    try {
      var storedProvider = localStorage.getItem('chatagentProvider');
      if (storedProvider) this.selectedProvider = storedProvider;
      var storedModel = localStorage.getItem('chatagentModel');
      if (storedModel) this.selectedModel = storedModel;
    } catch(e) {}

    this.settingsToggle = document.querySelector('#chatagent-settings-toggle');
    this.settingsPanel = document.querySelector('#chatagent-settings-panel');
    this.historyToggle = document.querySelector('#chatagent-history-toggle');
    this.historyPanel = document.querySelector('#chatagent-history-panel');
    this.historyList = document.querySelector('#chatagent-history-list');
    this.newConversationBtn = document.querySelector('#chatagent-new-conversation');
    this.settingsProv = document.querySelector('#chatagent-settings-provider');
    this.settingsSave = document.querySelector('#chatagent-settings-save');
    this.connTest = document.querySelector('#chatagent-connection-test');
    this.apiKeyToggle = document.querySelector('#chatagent-api-key-toggle');
    this.apiKeyInput = document.querySelector('#chatagent-api-key');
    this.keyNameInput = document.querySelector('#chatagent-key-name');
    this.testResult = document.querySelector('#chatagent-test-result');
    this.storedKeys = document.querySelector('#chatagent-stored-keys');

    if (!this.messagesContainer || !this.inputElement || !this.sendBtn) {
      return;
    }

    var self = this;

    this.sendBtn.disabled = true;
    this.inputElement.disabled = true;

    this._onSendClick = function() { self._sendMessage(); };
    this._onInputKeydown = function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        self._sendMessage();
      }
    };
    this._onInputChange = function() {
      self.inputElement.style.height = 'auto';
      self.inputElement.style.height = self.inputElement.scrollHeight + 'px';
    };

    this.sendBtn.addEventListener('click', this._onSendClick);
    this.inputElement.addEventListener('keydown', this._onInputKeydown);
    this.inputElement.addEventListener('input', this._onInputChange);

    // Selector de proveedor en la barra
    if (this.providerSelect) {
      this.providerSelect.addEventListener('change', function() {
        self._onProviderChange(self.providerSelect.value);
        // Guardar selección en localStorage
        try { localStorage.setItem('chatagentProvider', self.providerSelect.value); } catch(e) {}
      });
    }
    if (this.modelSelect) {
      this.modelSelect.addEventListener('change', function() {
        self.selectedModel = self.modelSelect.value;
        // Guardar selección en localStorage
        try { localStorage.setItem('chatagentModel', self.modelSelect.value); } catch(e) {}
      });
    }

    // Alternar panel de ajustes
    if (this.settingsToggle) {
      this.settingsToggle.addEventListener('click', function() {
        self._toggleSettings();
      });
    }

    // Alternar panel de historial
    if (this.historyToggle) {
      this.historyToggle.addEventListener('click', function() {
        self._toggleHistory();
      });
    }

    // Boton de nueva conversacion
    if (this.newConversationBtn) {
        this.newConversationBtn.addEventListener('click', function() {
            self._startNewConversation();
        });
    }

    // Probar conexión
    if (this.connTest) {
      this.connTest.addEventListener('click', function() {
        self._testKey();
      });
    }

    // Guardar clave
    if (this.settingsSave) {
      this.settingsSave.addEventListener('click', function() {
        self._saveKey();
      });
    }

    // Alternar visibilidad de API key
    if (this.apiKeyToggle) {
      this.apiKeyToggle.addEventListener('click', function() {
        if (self.apiKeyInput) {
          self.apiKeyInput.type = self.apiKeyInput.type === 'password' ? 'text' : 'password';
        }
      });
    }

    // Obtener proveedores y poblar selectores
    this._fetchProviders().then(function() {
      self.sendBtn.disabled = false;
      self.inputElement.disabled = false;
      self.inputElement.focus();
      var welcome = self.options.welcomeMessage
        || '<p>Soy el asistente de API-IDEE. Puedo ayudarte con:</p>'
        + '<ul>'
        + '<li>Usar el visor de mapas</li>'
        + '<li>Capas WMS, WMTS, WFS, GeoJSON, KML...</li>'
        + '<li>Desarrollar plugins</li>'
        + '<li>Navegar y buscar en el mapa</li>'
        + '</ul>';
      self._appendMessage('assistant', welcome);
    }).catch(function() {
      self.sendBtn.disabled = false;
      self.inputElement.disabled = false;
    });

    // Cargar configuracion e historial
    this._fetchConversationConfig();
    this._loadConversationIds();
  }

  /** Elimina los listeners de eventos al desactivarse el control. */
  _onDeactivate() {
    if (this.sendBtn && this._onSendClick) {
      this.sendBtn.removeEventListener('click', this._onSendClick);
    }
    if (this.inputElement) {
      if (this._onInputKeydown) this.inputElement.removeEventListener('keydown', this._onInputKeydown);
      if (this._onInputChange) this.inputElement.removeEventListener('input', this._onInputChange);
    }
  }

  /** Destruye el plugin, elimina el control del mapa y libera recursos. */
  destroy() {
    this._onDeactivate();
    if (this.map_ && this.panel_) {
      this.map_.removeControls([this.control_]);
    }
    this.map_ = null;
    this.panel_ = null;
    this.control_ = null;
  }

  /* ------------------------------------------------------------------
     Selección de proveedor
     ------------------------------------------------------------------ */

  /** Maneja el cambio de proveedor seleccionado en la barra superior.
    @param {string} value Identificador del proveedor (o prefijo __entry__ para claves guardadas). */
  _onProviderChange(value) {
    if (value && value.indexOf('__entry__') === 0) {
      // Entrada de usuario seleccionada
      var entryId = value.replace('__entry__', '');
      var entry = this._findEntryById(entryId);
      if (entry) {
        this._activeEntryId = entryId;
        this.selectedProvider = entry.provider;
        this._updateModelSelect(entry.provider);
        // Disparar sincronización de ajustes
        return;
      }
    }
    // Proveedor de servidor seleccionado
    this._activeEntryId = null;
    this.selectedProvider = value;
    this._updateModelSelect(value);
  }

  /* ------------------------------------------------------------------
     Obtención de proveedor / modelo
     ------------------------------------------------------------------ */

  /** Obtiene la lista de proveedores disponibles desde el backend. */
  async _fetchProviders() {
    try {
      var res = await fetch(this.options.backendUrl + '/providers/');
      if (!res.ok) throw new Error('HTTP ' + res.status);
      this.providers = await res.json();
      this._populateSelectors();
    } catch (error) {
      console.error('Error fetching providers:', error);
    }
  }

  /** Puebla los selectores de proveedor y modelo con los datos obtenidos del backend. */
  _populateSelectors() {
    if (!this.providerSelect || !this.modelSelect || !this.providers.length) return;
    var self = this;

    this.providerSelect.innerHTML = '';
    if (this.settingsProv) this.settingsProv.innerHTML = '';

    // Proveedores del servidor
    this.providers.forEach(function(p) {
      var opt = document.createElement('option');
      opt.value = p.name;
      opt.textContent = p.name;
      self.providerSelect.appendChild(opt);
      if (self.settingsProv) {
        var opt2 = document.createElement('option');
        opt2.value = p.name;
        opt2.textContent = p.name;
        self.settingsProv.appendChild(opt2);
      }
    });

    // Entradas de usuario
    if (this.userEntries.length > 0) {
      var sep = document.createElement('option');
      sep.disabled = true;
      sep.textContent = '─── Tus claves ───';
      this.providerSelect.appendChild(sep);

      this.userEntries.forEach(function(e) {
        var opt = document.createElement('option');
        opt.value = '__entry__' + e.id;
        opt.textContent = '\uD83D\uDD11 ' + e.name;
        self.providerSelect.appendChild(opt);
      });
    }

    // Restaurar selección
    if (this._activeEntryId) {
      this.providerSelect.value = '__entry__' + this._activeEntryId;
    } else if (this.selectedProvider) {
      this.providerSelect.value = this.selectedProvider;
    } else {
      this.selectedProvider = this.providers[0].name;
      this.providerSelect.value = this.selectedProvider;
    }

    if (this.settingsProv) this.settingsProv.value = this.selectedProvider;
    this._updateModelSelect(this.selectedProvider || this.providers[0].name);
  }

  /** Actualiza el selector de modelos segun el proveedor indicado.
    @param {string} providerName Nombre del proveedor. */
  _updateModelSelect(providerName) {
    if (!this.modelSelect) return;

    var provider = this.providers.find(function(p) { return p.name === providerName; });
    if (!provider) return;

    this.modelSelect.innerHTML = '';
    provider.models.forEach(function(m) {
      var opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.label;
      this.modelSelect.appendChild(opt);
    }, this);

    var selectedModel = null;
    try { selectedModel = localStorage.getItem('chatagentModel'); } catch(e) {}
    if (selectedModel && provider.models.some(function(m) { return m.id === selectedModel; })) {
      this.modelSelect.value = selectedModel;
    } else {
      var defaultModel = provider.default_model;
      if (defaultModel && provider.models.some(function(m) { return m.id === defaultModel; })) {
        this.modelSelect.value = defaultModel;
      }
    }
    this.selectedModel = this.modelSelect.value;
    try { localStorage.setItem('chatagentModel', this.selectedModel); } catch(e) {}
  }

  /** Refresca la barra de proveedor y el selector del panel de configuracion. */
  _refreshProviderBar() {
    if (!this.providerSelect) return;
    var self = this;

    this.providerSelect.innerHTML = '';
    if (this.settingsProv) this.settingsProv.innerHTML = '';

    // Proveedores del servidor
    this.providers.forEach(function(p) {
      var opt = document.createElement('option');
      opt.value = p.name;
      opt.textContent = p.name;
      self.providerSelect.appendChild(opt);
      if (self.settingsProv) {
        var opt2 = document.createElement('option');
        opt2.value = p.name;
        opt2.textContent = p.name;
        self.settingsProv.appendChild(opt2);
      }
    });

    // Entradas de usuario
    if (this.userEntries.length > 0) {
      var sep = document.createElement('option');
      sep.disabled = true;
      sep.textContent = '─── Tus claves ───';
      this.providerSelect.appendChild(sep);

      this.userEntries.forEach(function(e) {
        var opt = document.createElement('option');
        opt.value = '__entry__' + e.id;
        opt.textContent = '\uD83D\uDD11 ' + e.name;
        self.providerSelect.appendChild(opt);
      });
    }

    // Restaurar selección
    if (this._activeEntryId) {
      this.providerSelect.value = '__entry__' + this._activeEntryId;
    } else if (this.selectedProvider) {
      this.providerSelect.value = this.selectedProvider;
    }

    if (this.settingsProv && this.selectedProvider) {
      this.settingsProv.value = this.selectedProvider;
    }
  }

  /* ------------------------------------------------------------------
     Panel de ajustes
     ------------------------------------------------------------------ */

  /** Abre o cierra el panel de configuracion de claves. */
  _toggleSettings() {
    var panel = document.querySelector('#chatagent-settings-panel');
    if (!panel) return;
    var isOpen = panel.classList.toggle('open');
    if (isOpen) {
      this._renderStoredKeys();
      this._clearTestResult();
      if (this.settingsProv && this.selectedProvider) {
        this.settingsProv.value = this.selectedProvider;
      }
    }
  }

  /** Limpia el resultado de la prueba de conexion y deshabilita el boton Guardar. */
  _clearTestResult() {
    if (this.testResult) {
      this.testResult.innerHTML = '';
      this.testResult.className = 'chatagent-test-result';
    }
    if (this.settingsSave) this.settingsSave.disabled = true;
  }

  /** Muestra el resultado de la prueba de conexion (exito o error).
    @param {boolean} ok true si la prueba fue exitosa.
    @param {string} msg Mensaje a mostrar. */
  _showTestResult(ok, msg) {
    if (!this.testResult) return;
    this.testResult.innerHTML = msg;
    this.testResult.className = 'chatagent-test-result ' + (ok ? 'success' : 'error');

    if (this.settingsSave) this.settingsSave.disabled = !ok;

    if (ok && this.keyNameInput) {
      this.keyNameInput.focus();
    }
  }

  /** Renderiza la lista de claves guardadas en el panel de configuracion. */
  _renderStoredKeys() {
    if (!this.storedKeys) return;

    if (this.userEntries.length === 0) {
      this.storedKeys.innerHTML = '<div class="chatagent-stored-empty">No hay claves guardadas</div>';
      return;
    }

    var self = this;
    var html = '<div class="chatagent-stored-header">Tus claves</div>';
    this.userEntries.forEach(function(e) {
      var key = e.apiKey || '';
      var masked = key.length > 8 ? key.slice(0, 4) + '••••' + key.slice(-4) : '••••••••';
      var isActive = self._activeEntryId === e.id;
      html += '<div class="chatagent-stored-item' + (isActive ? ' active' : '') + '">'
        +   '<span class="chatagent-stored-item-name">' + chatagentEscapeHtml(e.name) + '</span>'
        +   '<span class="chatagent-stored-item-provider">' + chatagentEscapeHtml(e.provider) + '</span>'
        +   '<span class="chatagent-stored-item-key">' + chatagentEscapeHtml(masked) + '</span>'
        +   '<button class="chatagent-stored-item-del" data-entry-id="' + e.id + '" title="Eliminar">×</button>'
        + '</div>';
    });
    this.storedKeys.innerHTML = html;

    this.storedKeys.querySelectorAll('.chatagent-stored-item-del').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var id = btn.getAttribute('data-entry-id');
        self._deleteEntry(id);
      });
    });
  }

  /** Prueba una API key contra el backend para validarla. */
  async _testKey() {
    var provider = this.settingsProv ? this.settingsProv.value : '';
    var apiKey = this.apiKeyInput ? this.apiKeyInput.value.trim() : '';

    if (!provider) {
      this._showTestResult(false, 'Selecciona un proveedor');
      return;
    }
    if (!apiKey) {
      this._showTestResult(false, 'Introduce la API key');
      this.apiKeyInput && this.apiKeyInput.focus();
      return;
    }

    this._showTestResult(false, 'Probando conexión...');

    try {
      var res = await fetch(this.options.backendUrl + '/test-key/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: provider, api_key: apiKey }),
      });
      var data = await res.json();

      if (data.valid) {
        this._testedProvider = provider;
        this._testedApiKey = apiKey;
        this._showTestResult(true, '&#9989; Válida');
      } else {
        this._showTestResult(false, '&#10060; ' + (data.error || 'Error desconocido'));
      }
    } catch (error) {
      this._showTestResult(false, '&#10060; Error de conexión: ' + error.message);
    }
  }

  /** Guarda una nueva entrada de API key en localStorage y la selecciona. */
  _saveKey() {
    var name = this.keyNameInput ? this.keyNameInput.value.trim() : '';
    var provider = this.settingsProv ? this.settingsProv.value : '';
    var apiKey = this.apiKeyInput ? this.apiKeyInput.value.trim() : '';

    if (!name) { this.keyNameInput && this.keyNameInput.focus(); return; }
    if (!provider) { this.settingsProv && this.settingsProv.focus(); return; }
    if (!apiKey) { this.apiKeyInput && this.apiKeyInput.focus(); return; }

    var newEntry = {
      id: 'key_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8),
      name: name,
      provider: provider,
      apiKey: apiKey,
    };
    this.userEntries.push(newEntry);
    this._saveUserEntries();

    // Seleccionar la nueva entrada
    this._activeEntryId = newEntry.id;
    this.selectedProvider = provider;
    this._refreshProviderBar();
    this._updateModelSelect(provider);
    this._renderStoredKeys();

    // Limpiar formulario
    if (nameInput) nameInput.value = '';
    if (apiKeyInput) apiKeyInput.value = '';
    this._clearTestResult();
  }

  /** Elimina una entrada de usuario por su ID tras confirmacion.
    @param {string} id Identificador de la entrada. */
  _deleteEntry(id) {
    if (!id) return;
    var entry = this._findEntryById(id);
    var label = entry ? entry.name : 'esta clave';
    if (!confirm('¿Eliminar "' + label + '"?')) return;

    this.userEntries = this.userEntries.filter(function(e) { return e.id !== id; });
    this._saveUserEntries();

    if (this._activeEntryId === id) {
      this._activeEntryId = null;
      // Usar primer proveedor del servidor como fallback
      if (this.providers.length > 0) {
        this.selectedProvider = this.providers[0].name;
      }
    }

    this._refreshProviderBar();
    if (this.selectedProvider) this._updateModelSelect(this.selectedProvider);
    this._renderStoredKeys();
  }

  /* ------------------------------------------------------------------
     Lógica del chat
     ------------------------------------------------------------------ */

  /** Devuelve la API key activa (de una entrada guardada) o null si no hay.
    @returns {string|null} API key o null. */
  _getEffectiveApiKey() {
    if (this._activeEntryId) {
      var entry = this._findEntryById(this._activeEntryId);
      if (entry) return entry.apiKey || null;
    }
    return null;
  }

  /** Construye el cuerpo de la peticion anadiendo proveedor, modelo y API key activa.
    @param {Object} base Cuerpo base de la peticion.
    @returns {Object} Cuerpo completo con proveedor, modelo y API key. */
  _buildRequestBody(base) {
    var body = Object.assign({}, base);
    if (this.selectedProvider) body.provider = this.selectedProvider;
    if (this.selectedModel) body.model = this.selectedModel;
    var apiKey = this._getEffectiveApiKey();
    if (apiKey) body.api_key = apiKey;
    return body;
  }

  /** Captura el estado actual del mapa (centro, zoom y SRS).
    @returns {{center: {lat: number, lon: number}, zoom: number, srs: string}|null} Estado del mapa o null. */
  _getMapState() {
    if (!this.map_) return null;
    try {
      var center = this.map_.getCenter();
      var bbox = this.map_.getBbox();
      var state = {
        center: { lat: center.y, lon: center.x },
        zoom: this.map_.getZoom(),
        srs: this.map_.getProjection().code,
      };
      if (bbox) {
        state.extent = {
          minX: bbox.x.min,
          minY: bbox.y.min,
          maxX: bbox.x.max,
          maxY: bbox.y.max,
        };
      }
      return state;
    } catch (e) {
      return null;
    }
  }

  /** Crea una nueva conversacion en el backend y almacena su ID. */
  async _createConversation() {
    try {
      var res = await fetch(this.options.backendUrl + '/conversations/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      var data = await res.json();
      this.conversationId = data.id;
      this._addConversationId(this.conversationId);
    } catch (error) {
      console.error('Error creating conversation:', error);
      this._appendMessage('system', 'Error al iniciar la conversacion.');
    }
  }

  /** Envia un mensaje del usuario al backend y procesa la respuesta (texto o tool_calls).
      Si ``this.options.stream`` es true, usa SSE para recibir la respuesta incrementalmente.
      @param {string} [content] Contenido opcional. Si no se pasa, se lee del input. */
  async _sendMessage(content) {
    if (!this.inputElement) return;
    if (content === undefined) {
      content = this.inputElement.value.trim();
      if (!content) return;
      this.inputElement.value = '';
      this.inputElement.style.height = 'auto';
    } else if (!content) {
      return;
    }

    if (!this.conversationId) {
      await this._createConversation();
      if (!this.conversationId) return;
    }

    this._appendMessage('user', chatagentEscapeHtml(content));
    this._showLoading(true);

    try {
      if (this.options.stream) {
        await this._sendMessageStream(content);
      } else {
        await this._sendMessageClassic(content);
      }
    } catch (error) {
      console.error('Error sending message:', error);
      this._appendMessage('system', 'Error al enviar el mensaje.');
    } finally {
      this._showLoading(false);
      if (this.messagesContainer) {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
      }
    }
  }

  /** Envia un mensaje sin streaming (respuesta JSON completa).
      @param {string} content Texto del mensaje. */
  async _sendMessageClassic(content) {
    var mapState = this._getMapState();
    var body = this._buildRequestBody({ content: content, map_state: mapState });

    var res = await fetch(
      this.options.backendUrl + '/conversations/' + this.conversationId + '/chat/',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }
    );
    if (!res.ok) throw new Error('HTTP ' + res.status);
    var data = await res.json();

    var handledToolCall = false;
    console.log('[ChatAgent] Response content blocks:', JSON.stringify(data.content?.map(function(b) { return b.type; })));
    if (data.content) {
      for (var r = 0; r < data.content.length; r++) {
        var item = data.content[r];
          if (item.type === 'layer') {
            console.log('[ChatAgent] Layer block found:', item.layer?.type, item.layer?.name, 'features:', item.layer?.source?.features?.length);
            var layerInfo = item.layer;
            var layerType = layerInfo.type;
            if (layerType === 'geojson') {
              if (layerInfo.url) {
                var gOpts = { name: layerInfo.name || 'Capa', legend: layerInfo.name || 'Capa', url: layerInfo.url };
                var gLayer = new IDEE.layer.GeoJSON(gOpts);
                if (layerInfo.style) gLayer.setStyle(new IDEE.style.Generic(layerInfo.style));
                this.map_.addLayers([gLayer]);
              } else if (layerInfo.source) {
                chatagentAddOrAppendGeoJSON(this.map_, layerInfo.name || 'Capa', layerInfo.source, layerInfo.style);
              }
            } else if (layerType === 'geocoding_candidates') {
              this._appendCandidates(layerInfo.candidates);
            }
          } else if (item.type === 'tool_call' && item.toolCalls) {
          if (!handledToolCall) {
            await this._handleToolCalls(item.toolCalls);
            handledToolCall = true;
          }
        } else if (item.type === 'text') {
          this._appendMessage('assistant', item.text, data.metadata ? data.metadata.sources : null);
        }
      }
    }
  }

  /** Envia un mensaje con streaming SSE. El texto se muestra token a token.
      @param {string} content Texto del mensaje. */
  async _sendMessageStream(content) {
    var mapState = this._getMapState();
    var body = this._buildRequestBody({ content: content, map_state: mapState, stream: true });

    var res = await fetch(
      this.options.backendUrl + '/conversations/' + this.conversationId + '/chat/',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }
    );
    if (!res.ok) throw new Error('HTTP ' + res.status);

    // Crear burbuja de mensaje vacia para ir rellenando
    var msgBubble = this._appendMessage('assistant', '', null, true);
    var accumulatedText = '';
    var self = this;

    var reader = res.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';

    while (true) {
      var readResult = await reader.read();
      if (readResult.done) break;

      buffer += decoder.decode(readResult.value, { stream: true });

      // Parsear eventos SSE del buffer
      var lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Ultimo trozo incompleto queda en buffer

      var currentEventType = '';
      for (var li = 0; li < lines.length; li++) {
        var line = lines[li];
        if (line.startsWith('event: ')) {
          currentEventType = line.substring(7).trim();
        } else if (line.startsWith('data: ')) {
          var jsonStr = line.substring(6);
          try {
            var event = JSON.parse(jsonStr);
          } catch (e) {
            continue;
          }
          var evType = currentEventType || event.type || '';

          if (evType === 'text_delta') {
            accumulatedText += event.text || '';
            if (msgBubble) {
              msgBubble.innerHTML = chatagentSanitizeHtml(accumulatedText);
            }
            if (self.messagesContainer) {
              self.messagesContainer.scrollTop = self.messagesContainer.scrollHeight;
            }
          } else if (evType === 'tool_call' && event.toolCalls) {
            await self._handleToolCalls(event.toolCalls);
          } else if (evType === 'layer' && event.layer) {
            var layerInfo = event.layer;
            if (layerInfo.type === 'geojson') {
              if (layerInfo.url) {
                var gOpts = { name: layerInfo.name || 'Capa', legend: layerInfo.name || 'Capa', url: layerInfo.url };
                var gLayer = new IDEE.layer.GeoJSON(gOpts);
                if (layerInfo.style) gLayer.setStyle(new IDEE.style.Generic(layerInfo.style));
                self.map_.addLayers([gLayer]);
              } else if (layerInfo.source) {
                chatagentAddOrAppendGeoJSON(self.map_, layerInfo.name || 'Capa', layerInfo.source, layerInfo.style);
              }
            } else if (layerInfo.type === 'geocoding_candidates') {
              self._appendCandidates(layerInfo.candidates);
            }
          }
          // 'sources' y 'done' se ignoran en el frontend (sources ya se muestran inline)
          currentEventType = '';
        }
      }
    }
  }

  /** Procesa una lista de llamadas a herramientas del mapa y envia los resultados al backend.
    @param {Array<{name: string, args?: Object, id?: string}>} toolCalls Lista de herramientas a ejecutar. */
  async _handleToolCalls(toolCalls) {
    for (var i = 0; i < toolCalls.length; i++) {
      var tc = toolCalls[i];
      var result = chatagentExecuteTool(this.map_, tc.name, tc.args || {});

      try {
        var body = this._buildRequestBody({
          tool_name: tc.name,
          tool_call_id: tc.id || '',
          result: result,
          success: result.success !== false,
        });

        var res = await fetch(
          this.options.backendUrl + '/conversations/' + this.conversationId + '/tool-result/',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          }
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        var data = await res.json();

        var handledToolCall = false;
        if (data.content) {
          for (var rx = 0; rx < data.content.length; rx++) {
            var it = data.content[rx];
            if (it.type === 'text') {
              this._appendMessage('assistant', it.text, data.metadata ? data.metadata.sources : null);
            } else if (it.type === 'tool_call' && it.toolCalls) {
              if (!handledToolCall) {
                await this._handleToolCalls(it.toolCalls);
                handledToolCall = true;
              }
            } else if (it.type === 'layer') {
              var layerInfo = it.layer;
              var layerType = layerInfo.type;
              if (layerType === 'geojson') {
                if (layerInfo.url) {
                  var gOpts = { name: layerInfo.name || 'Capa', legend: layerInfo.name || 'Capa', url: layerInfo.url };
                  var gLayer = new IDEE.layer.GeoJSON(gOpts);
                  if (layerInfo.style) gLayer.setStyle(new IDEE.style.Generic(layerInfo.style));
                  this.map_.addLayers([gLayer]);
                } else if (layerInfo.source) {
                  chatagentAddOrAppendGeoJSON(this.map_, layerInfo.name || 'Capa', layerInfo.source, layerInfo.style);
                }
              } else if (layerType === 'geocoding_candidates') {
                this._appendCandidates(layerInfo.candidates);
              }
            }
          }
        }
      } catch (error) {
        console.error('Error sending tool result:', error);
        this._appendMessage('system', 'Error al ejecutar la herramienta.');
      }
    }
  }

  /* ------------------------------------------------------------------
     Ayudantes de UI
     ------------------------------------------------------------------ */

  /** Aniade un mensaje al contenedor del chat y hace scroll automatico.
    El contenido del assistant y system se sanitiza con una allowlist de
    tags para prevenir XSS. Los mensajes del usuario ya llegan escapados.
    @param {string} role Rol del mensaje (user, assistant, system).
    @param {string} content Contenido HTML del mensaje.
    @param {Array} [sources] Fuentes citadas opcionales. */
  /** Añade un mensaje al chat y opcionalmente devuelve el elemento DOM del contenido.
      @param {string} role Rol del mensaje (user, assistant, system).
      @param {string} content Contenido HTML del mensaje.
      @param {Array|null} [sources] Fuentes RAG citadas.
      @param {boolean} [returnElement] Si true, devuelve el div del mensaje para actualizarlo (streaming).
      @returns {HTMLElement|undefined} El div del mensaje si returnElement es true. */
  _appendMessage(role, content, sources, returnElement) {
    if (!this.messagesContainer) return;

    var wrapper = document.createElement('div');
    wrapper.className = 'chatagent-message-wrapper ' + role;

    var htmlContent = content;
    if (role !== 'user') {
      // Extraer HTML de bloques markdown ```html ... ``` si el LLM los envuelve
      var match = content.match(/```html\s*([\s\S]*?)```/);
      if (match && match[1].trim()) {
        htmlContent = match[1];
      }
      htmlContent = chatagentSanitizeHtml(htmlContent);
    }
    var msgDiv = document.createElement('div');
    msgDiv.className = 'chatagent-message';
    msgDiv.innerHTML = htmlContent;

    wrapper.appendChild(msgDiv);
    this.messagesContainer.appendChild(wrapper);

    if (sources && sources.length > 0) {
      var details = document.createElement('details');
      details.className = 'chatagent-sources';
      var summary = document.createElement('summary');
      summary.textContent = 'Fuentes citadas';
      details.appendChild(summary);

      var ul = document.createElement('ul');
      for (var i = 0; i < sources.length; i++) {
        var li = document.createElement('li');
        li.textContent = sources[i].source + ' (chunk ' + sources[i].chunk_index + ')';
        ul.appendChild(li);
      }
      details.appendChild(ul);
      this.messagesContainer.appendChild(details);
    }

    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;

    if (returnElement) return msgDiv;
  }

  /** Inserta candidatos del geocoder como una lista HTML numerada agrupada por tipo
      dentro del ultimo mensaje del asistente.
    @param {Array<Object>} candidates Lista de candidatos con geojsonURL. */
  _appendCandidates(candidates) {
    if (!candidates || candidates.length === 0 || !this.messagesContainer) return;
    var html = '<div class="chatagent-candidates">';
    var currentType = '';
    var olIndex = 0;
    for (var ci = 0; ci < candidates.length; ci++) {
      var c = candidates[ci];
      var ctype = c.type || '';
      if (ctype !== currentType) {
        if (currentType !== '') html += '</ol>';
        currentType = ctype;
        var typeLabel = ctype.charAt(0).toUpperCase() + ctype.slice(1);
        html += '<div class="chatagent-candidates-group-title">' + chatagentEscapeHtml(typeLabel) + '</div><ol class="chatagent-candidates-list">';
      }
      olIndex++;
      var addr = c.address || 'Sin dirección';
      var u = c.geojsonURL || '';
      var escAddr = chatagentEscapeHtml(addr).replace(/'/g, "\\'");
      var escUrl = chatagentEscapeHtml(u).replace(/'/g, "\\'");
      html += '<li data-geojson-url="' + escUrl + '" onclick="chatagentQuickReply(\'' + escAddr + '\', \'' + escUrl + '\')" class="chatagent-candidate-item">' + chatagentEscapeHtml(addr) + '</li>';
    }
    if (currentType !== '') html += '</ol>';
    html += '</div>';

    var wrappers = this.messagesContainer.querySelectorAll('.chatagent-message-wrapper.assistant');
    if (wrappers.length > 0) {
      var lastMsg = wrappers[wrappers.length - 1].querySelector('.chatagent-message');
      if (lastMsg) {
        lastMsg.insertAdjacentHTML('beforeend', html);
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        return;
      }
    }
    this._appendMessage('assistant', html);
  }

  /** Muestra u oculta el indicador de carga en el chat.
    @param {boolean} visible true para mostrar, false para ocultar. */
  _showLoading(visible) {
    if (!this.loadingEl) return;
    if (visible) {
      this.loadingEl.classList.add('visible');
    } else {
      this.loadingEl.classList.remove('visible');
    }
  }
}

/* =========================================================================
   Registrar plugin
   ========================================================================= */

if (typeof window !== 'undefined') {
  window.IDEE = window.IDEE || {};
  window.IDEE.plugin = window.IDEE.plugin || {};
  window.IDEE.plugin.ChatAgent = ChatAgent;
}
