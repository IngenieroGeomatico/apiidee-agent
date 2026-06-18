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
   Tool executor — maps tool names to IDEE.Map calls
   ========================================================================= */

var CHATAGENT_TOOL_MAP = {
  getMapCenter: function(map) {
    var center = map.getCenter();
    return { lat: center.y, lon: center.x, srs: map.getProjection().code };
  },
  getCurrentZoom: function(map) {
    return { level: map.getZoom() };
  },
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
  addWMSLayer: function(map, args) {
    var layer = new IDEE.layer.WMS({
      url: args.url,
      name: args.name,
      legend: args.legend || args.name,
      transparent: args.transparent !== undefined ? args.transparent : true,
      tiled: false,
    });
    map.addLayers([layer]);
    return { success: true, name: args.name };
  },
  zoomTo: function(map, args) {
    map.setCenter({ x: args.lon, y: args.lat });
    if (args.zoom !== undefined) {
      map.setZoom(args.zoom);
    }
    return { success: true };
  },
  removeLayer: function(map, args) {
    var layers = map.getLayers();
    var target = layers.find(function(l) { return l.name === args.name; });
    if (target) {
      map.removeLayers([target]);
      return { success: true, name: args.name };
    }
    return { success: false, error: 'Layer not found: ' + args.name };
  },
  setZoom: function(map, args) {
    map.setZoom(args.level);
    return { success: true, level: args.level };
  },
};

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

function chatagentEscapeHtml(unsafe) {
  return unsafe
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/* =========================================================================
   Plugin class
   ========================================================================= */

var CHATAGENT_STORAGE_KEY = 'chatagent_user_keys';

class ChatAgent {
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

    // State
    this.map_ = null;
    this.panel_ = null;
    this.control_ = null;
    this.conversationId = null;
    this.messagesContainer = null;
    this.inputElement = null;
    this.loadingEl = null;
    this.providers = [];

    // Selected provider/model from the bar
    this.selectedProvider = null;
    this.selectedModel = null;

    // User-saved entries: [{ id, name, provider, apiKey }]
    this.userEntries = [];
    this._loadUserEntries();
  }

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
     User entries persistence (localStorage)
     ------------------------------------------------------------------ */

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

  _saveUserEntries() {
    try {
      localStorage.setItem(CHATAGENT_STORAGE_KEY, JSON.stringify(this.userEntries));
    } catch (e) {
      console.error('Error saving entries to localStorage:', e);
    }
  }

  _findEntryById(id) {
    return this.userEntries.find(function(e) { return e.id === id; }) || null;
  }

  /* ------------------------------------------------------------------
     Plugin lifecycle
     ------------------------------------------------------------------ */

  addTo(map) {
    var self = this;
    this.map_ = map;

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

    // 2. HTML for the chat panel
    var htmlPanel = ''
      + '<div aria-label="asistente IA" role="menuitem" id="div-contenedor-chatagent" class="m-control m-container m-chatagent-container">'
      +   '<header role="heading" tabindex="0" id="m-chatagent-title" class="m-chatagent-header">'
      +     '<span class="chatagent-header-title">Asistente API-IDEE</span>'
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
      return container;
    };

    this.panel_.addControls(this.control_);
    map.addPanels(this.panel_);

    var panelControls = document.querySelector('.g-chatagent .m-panel-controls');
    if (panelControls) {
      panelControls.innerHTML = htmlPanel;
    }

    var contentsEl = document.querySelector('#m-chatagent-body');
    if (contentsEl) {
      contentsEl.appendChild(this.control_.getElement());
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
     Lifecycle
     ------------------------------------------------------------------ */

  _onActivate() {
    this.messagesContainer = document.querySelector('#chatagent-messages');
    this.inputElement = document.querySelector('#chatagent-input');
    this.loadingEl = document.querySelector('#chatagent-loading');
    var sendBtn = document.querySelector('#chatagent-send');
    var providerSelect = document.querySelector('#chatagent-provider-select');
    var modelSelect = document.querySelector('#chatagent-model-select');
    var settingsToggle = document.querySelector('#chatagent-settings-toggle');
    var connTest = document.querySelector('#chatagent-connection-test');
    var settingsSave = document.querySelector('#chatagent-settings-save');
    var apiKeyToggle = document.querySelector('#chatagent-api-key-toggle');

    if (!this.messagesContainer || !this.inputElement || !sendBtn) {
      return;
    }

    var self = this;

    sendBtn.disabled = true;
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

    sendBtn.addEventListener('click', this._onSendClick);
    this.inputElement.addEventListener('keydown', this._onInputKeydown);
    this.inputElement.addEventListener('input', this._onInputChange);

    // Provider select in bar
    if (providerSelect) {
      providerSelect.addEventListener('change', function() {
        self._onProviderChange(providerSelect.value);
      });
    }
    if (modelSelect) {
      modelSelect.addEventListener('change', function() {
        self.selectedModel = modelSelect.value;
      });
    }

    // Settings toggle
    if (settingsToggle) {
      settingsToggle.addEventListener('click', function() {
        self._toggleSettings();
      });
    }

    // Test connection
    if (connTest) {
      connTest.addEventListener('click', function() {
        self._testKey();
      });
    }

    // Save key
    if (settingsSave) {
      settingsSave.addEventListener('click', function() {
        self._saveKey();
      });
    }

    // API key visibility toggle
    if (apiKeyToggle) {
      apiKeyToggle.addEventListener('click', function() {
        var input = document.querySelector('#chatagent-api-key');
        if (input) {
          input.type = input.type === 'password' ? 'text' : 'password';
        }
      });
    }

    // Fetch providers and populate selectors
    this._fetchProviders().then(function() {
      sendBtn.disabled = false;
      self.inputElement.disabled = false;
      self.inputElement.focus();
      var welcome = self.options.welcomeMessage
        || '<p>Soy el asistente de API-IDEE. Puedo ayudarte con:</p>'
        + '<ul>'
        + '<li>Usar el visor de mapas</li>'
        + '<li>Capas WMS, WMTS, WFS...</li>'
        + '<li>Desarrollar plugins</li>'
        + '<li>Navegar y buscar en el mapa</li>'
        + '</ul>';
      self._appendMessage('assistant', welcome);
    }).catch(function() {
      sendBtn.disabled = false;
      self.inputElement.disabled = false;
    });
  }

  _onDeactivate() {
    var sendBtn = document.querySelector('#chatagent-send');
    if (sendBtn && this._onSendClick) {
      sendBtn.removeEventListener('click', this._onSendClick);
    }
    if (this.inputElement) {
      if (this._onInputKeydown) this.inputElement.removeEventListener('keydown', this._onInputKeydown);
      if (this._onInputChange) this.inputElement.removeEventListener('input', this._onInputChange);
    }
  }

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
     Provider selection
     ------------------------------------------------------------------ */

  _onProviderChange(value) {
    if (value && value.indexOf('__entry__') === 0) {
      // User entry selected
      var entryId = value.replace('__entry__', '');
      var entry = this._findEntryById(entryId);
      if (entry) {
        this._activeEntryId = entryId;
        this.selectedProvider = entry.provider;
        this._updateModelSelect(entry.provider);
        // Trigger settings sync
        return;
      }
    }
    // Server provider selected
    this._activeEntryId = null;
    this.selectedProvider = value;
    this._updateModelSelect(value);
  }

  /* ------------------------------------------------------------------
     Provider / Model fetching
     ------------------------------------------------------------------ */

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

  _populateSelectors() {
    var providerSelect = document.querySelector('#chatagent-provider-select');
    var modelSelect = document.querySelector('#chatagent-model-select');
    var settingsProv = document.querySelector('#chatagent-settings-provider');
    if (!providerSelect || !modelSelect || !this.providers.length) return;
    var self = this;

    providerSelect.innerHTML = '';
    if (settingsProv) settingsProv.innerHTML = '';

    // Server providers
    this.providers.forEach(function(p) {
      var opt = document.createElement('option');
      opt.value = p.name;
      opt.textContent = p.name;
      providerSelect.appendChild(opt);
      if (settingsProv) {
        var opt2 = document.createElement('option');
        opt2.value = p.name;
        opt2.textContent = p.name;
        settingsProv.appendChild(opt2);
      }
    });

    // User entries
    if (this.userEntries.length > 0) {
      var sep = document.createElement('option');
      sep.disabled = true;
      sep.textContent = '─── Tus claves ───';
      providerSelect.appendChild(sep);

      this.userEntries.forEach(function(e) {
        var opt = document.createElement('option');
        opt.value = '__entry__' + e.id;
        opt.textContent = '\uD83D\uDD11 ' + e.name;
        providerSelect.appendChild(opt);
      });
    }

    // Restore selection
    if (this._activeEntryId) {
      providerSelect.value = '__entry__' + this._activeEntryId;
    } else if (this.selectedProvider) {
      providerSelect.value = this.selectedProvider;
    } else {
      this.selectedProvider = this.providers[0].name;
      providerSelect.value = this.selectedProvider;
    }

    if (settingsProv) settingsProv.value = this.selectedProvider;
    this._updateModelSelect(this.selectedProvider || this.providers[0].name);
  }

  _updateModelSelect(providerName) {
    var modelSelect = document.querySelector('#chatagent-model-select');
    if (!modelSelect) return;

    var provider = this.providers.find(function(p) { return p.name === providerName; });
    if (!provider) return;

    modelSelect.innerHTML = '';
    provider.models.forEach(function(m) {
      var opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.label;
      modelSelect.appendChild(opt);
    });

    var defaultModel = provider.default_model;
    if (defaultModel && provider.models.some(function(m) { return m.id === defaultModel; })) {
      modelSelect.value = defaultModel;
    }
    this.selectedModel = modelSelect.value;
  }

  _refreshProviderBar() {
    var providerSelect = document.querySelector('#chatagent-provider-select');
    var settingsProv = document.querySelector('#chatagent-settings-provider');
    if (!providerSelect) return;
    var self = this;

    providerSelect.innerHTML = '';
    if (settingsProv) settingsProv.innerHTML = '';

    // Server providers
    this.providers.forEach(function(p) {
      var opt = document.createElement('option');
      opt.value = p.name;
      opt.textContent = p.name;
      providerSelect.appendChild(opt);
      if (settingsProv) {
        var opt2 = document.createElement('option');
        opt2.value = p.name;
        opt2.textContent = p.name;
        settingsProv.appendChild(opt2);
      }
    });

    // User entries
    if (this.userEntries.length > 0) {
      var sep = document.createElement('option');
      sep.disabled = true;
      sep.textContent = '─── Tus claves ───';
      providerSelect.appendChild(sep);

      this.userEntries.forEach(function(e) {
        var opt = document.createElement('option');
        opt.value = '__entry__' + e.id;
        opt.textContent = '\uD83D\uDD11 ' + e.name;
        providerSelect.appendChild(opt);
      });
    }

    // Restore selection
    if (this._activeEntryId) {
      providerSelect.value = '__entry__' + this._activeEntryId;
    } else if (this.selectedProvider) {
      providerSelect.value = this.selectedProvider;
    }

    if (settingsProv && this.selectedProvider) {
      settingsProv.value = this.selectedProvider;
    }
  }

  /* ------------------------------------------------------------------
     Settings panel
     ------------------------------------------------------------------ */

  _toggleSettings() {
    var panel = document.querySelector('#chatagent-settings-panel');
    if (!panel) return;
    var isOpen = panel.classList.toggle('open');
    if (isOpen) {
      this._renderStoredKeys();
      this._clearTestResult();
      var settingsProv = document.querySelector('#chatagent-settings-provider');
      if (settingsProv && this.selectedProvider) {
        settingsProv.value = this.selectedProvider;
      }
    }
  }

  _clearTestResult() {
    var el = document.querySelector('#chatagent-test-result');
    if (el) {
      el.innerHTML = '';
      el.className = 'chatagent-test-result';
    }
    var saveBtn = document.querySelector('#chatagent-settings-save');
    if (saveBtn) saveBtn.disabled = true;
  }

  _showTestResult(ok, msg) {
    var el = document.querySelector('#chatagent-test-result');
    if (!el) return;
    el.innerHTML = msg;
    el.className = 'chatagent-test-result ' + (ok ? 'success' : 'error');

    var saveBtn = document.querySelector('#chatagent-settings-save');
    if (saveBtn) saveBtn.disabled = !ok;

    if (ok) {
      var nameInput = document.querySelector('#chatagent-key-name');
      nameInput && nameInput.focus();
    }
  }

  _renderStoredKeys() {
    var container = document.querySelector('#chatagent-stored-keys');
    if (!container) return;

    if (this.userEntries.length === 0) {
      container.innerHTML = '<div class="chatagent-stored-empty">No hay claves guardadas</div>';
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
    container.innerHTML = html;

    container.querySelectorAll('.chatagent-stored-item-del').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var id = btn.getAttribute('data-entry-id');
        self._deleteEntry(id);
      });
    });
  }

  async _testKey() {
    var provSelect = document.querySelector('#chatagent-settings-provider');
    var apiKeyInput = document.querySelector('#chatagent-api-key');

    var provider = provSelect ? provSelect.value : '';
    var apiKey = apiKeyInput ? apiKeyInput.value.trim() : '';

    if (!provider) {
      this._showTestResult(false, 'Selecciona un proveedor');
      return;
    }
    if (!apiKey) {
      this._showTestResult(false, 'Introduce la API key');
      apiKeyInput && apiKeyInput.focus();
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

  _saveKey() {
    var nameInput = document.querySelector('#chatagent-key-name');
    var provSelect = document.querySelector('#chatagent-settings-provider');
    var apiKeyInput = document.querySelector('#chatagent-api-key');

    var name = nameInput ? nameInput.value.trim() : '';
    var provider = provSelect ? provSelect.value : '';
    var apiKey = apiKeyInput ? apiKeyInput.value.trim() : '';

    if (!name) { nameInput && nameInput.focus(); return; }
    if (!provider) { provSelect && provSelect.focus(); return; }
    if (!apiKey) { apiKeyInput && apiKeyInput.focus(); return; }

    var newEntry = {
      id: 'key_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8),
      name: name,
      provider: provider,
      apiKey: apiKey,
    };
    this.userEntries.push(newEntry);
    this._saveUserEntries();

    // Select the new entry
    this._activeEntryId = newEntry.id;
    this.selectedProvider = provider;
    this._refreshProviderBar();
    this._updateModelSelect(provider);
    this._renderStoredKeys();

    // Clear form
    if (nameInput) nameInput.value = '';
    if (apiKeyInput) apiKeyInput.value = '';
    this._clearTestResult();
  }

  _deleteEntry(id) {
    if (!id) return;
    var entry = this._findEntryById(id);
    var label = entry ? entry.name : 'esta clave';
    if (!confirm('¿Eliminar "' + label + '"?')) return;

    this.userEntries = this.userEntries.filter(function(e) { return e.id !== id; });
    this._saveUserEntries();

    if (this._activeEntryId === id) {
      this._activeEntryId = null;
      // Fall back to first server provider
      if (this.providers.length > 0) {
        this.selectedProvider = this.providers[0].name;
      }
    }

    this._refreshProviderBar();
    if (this.selectedProvider) this._updateModelSelect(this.selectedProvider);
    this._renderStoredKeys();
  }

  /* ------------------------------------------------------------------
     Chat logic
     ------------------------------------------------------------------ */

  _getEffectiveApiKey() {
    if (this._activeEntryId) {
      var entry = this._findEntryById(this._activeEntryId);
      if (entry) return entry.apiKey || null;
    }
    return null;
  }

  _getMapState() {
    if (!this.map_) return null;
    try {
      var center = this.map_.getCenter();
      return {
        center: { lat: center.y, lon: center.x },
        zoom: this.map_.getZoom(),
        srs: this.map_.getProjection().code,
      };
    } catch (e) {
      return null;
    }
  }

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
    } catch (error) {
      console.error('Error creating conversation:', error);
      this._appendMessage('system', 'Error al iniciar la conversacion.');
    }
  }

  async _sendMessage() {
    if (!this.inputElement) return;
    var content = this.inputElement.value.trim();
    if (!content) return;

    this.inputElement.value = '';
    this.inputElement.style.height = 'auto';

    if (!this.conversationId) {
      await this._createConversation();
      if (!this.conversationId) return;
    }

    this._appendMessage('user', chatagentEscapeHtml(content));
    this._showLoading(true);

    try {
      var mapState = this._getMapState();
      var body = { content: content, map_state: mapState };
      if (this.selectedProvider) body.provider = this.selectedProvider;
      if (this.selectedModel) body.model = this.selectedModel;

      var apiKey = this._getEffectiveApiKey();
      if (apiKey) body.api_key = apiKey;

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

      if (data.type === 'tool_call' && data.tool_calls && data.tool_calls.length > 0) {
        if (data.content) {
          this._appendMessage('assistant', data.content);
        }
        await this._handleToolCalls(data.tool_calls);
      } else {
        this._appendMessage('assistant', data.content, data.metadata ? data.metadata.sources : null);
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

  async _handleToolCalls(toolCalls) {
    for (var i = 0; i < toolCalls.length; i++) {
      var tc = toolCalls[i];
      var result = chatagentExecuteTool(this.map_, tc.name, tc.args || {});

      try {
        var body = {
          tool_name: tc.name,
          tool_call_id: tc.id || '',
          result: result,
          success: result.success !== false,
        };
        if (this.selectedProvider) body.provider = this.selectedProvider;
        if (this.selectedModel) body.model = this.selectedModel;

        var apiKey = this._getEffectiveApiKey();
        if (apiKey) body.api_key = apiKey;

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

        if (data.type === 'tool_call' && data.tool_calls && data.tool_calls.length > 0) {
          if (data.content) {
            this._appendMessage('assistant', data.content);
          }
          await this._handleToolCalls(data.tool_calls);
        } else {
          this._appendMessage('assistant', data.content, data.metadata ? data.metadata.sources : null);
        }
      } catch (error) {
        console.error('Error sending tool result:', error);
        this._appendMessage('system', 'Error al ejecutar la herramienta.');
      }
    }
  }

  /* ------------------------------------------------------------------
     UI helpers
     ------------------------------------------------------------------ */

  _appendMessage(role, content, sources) {
    if (!this.messagesContainer) return;

    var wrapper = document.createElement('div');
    wrapper.className = 'chatagent-message-wrapper ' + role;

    var msgDiv = document.createElement('div');
    msgDiv.className = 'chatagent-message';
    msgDiv.innerHTML = content;

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
  }

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
   Register plugin
   ========================================================================= */

if (typeof window !== 'undefined') {
  window.IDEE = window.IDEE || {};
  window.IDEE.plugin = window.IDEE.plugin || {};
  window.IDEE.plugin.ChatAgent = ChatAgent;
}
