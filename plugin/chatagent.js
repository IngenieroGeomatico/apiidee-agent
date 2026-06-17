
(function() {
  // Inlined CSS (as a string literal)
  const CSS_STYLES = `
    .chatagent-panel-container {
      position: fixed;
      bottom: 20px;
      right: 20px;
      z-index: 1000; /* Ensure it's above the map */
      transition: all 0.3s ease-in-out;
    }

    .m-plugin-chatagent {
      width: 380px;
      max-height: 500px;
      background-color: var(--chatagent-bg, #ffffff);
      border-radius: 8px;
      box-shadow: var(--chatagent-shadow, 0 4px 12px rgba(0, 0, 0, 0.15));
      display: flex;
      flex-direction: column;
      overflow: hidden;
      font-family: 'Arial', sans-serif;
      border: 1px solid var(--chatagent-border, #e5e7eb);
      position: relative; /* For toggle button positioning */
    }

    .m-plugin-chatagent.collapsed {
      width: 50px; /* Adjust for just icon/toggle */
      max-height: 50px;
      border-radius: 50%;
    }

    .chatagent-header {
      background-color: var(--chatagent-primary, #2563eb);
      color: var(--chatagent-user-text, #ffffff);
      padding: 10px 15px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      cursor: pointer;
      user-select: none;
    }

    .m-plugin-chatagent.collapsed .chatagent-header {
      border-radius: 50%;
      width: 50px;
      height: 50px;
      padding: 0;
      justify-content: center;
      align-items: center;
    }

    .m-plugin-chatagent.collapsed .chatagent-title {
      display: none;
    }

    .m-plugin-chatagent.collapsed .chatagent-toggle {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%) rotate(180deg);
      background: none;
      border: none;
      color: inherit;
      font-size: 24px;
      line-height: 1;
      cursor: pointer;
      outline: none;
    }
    .m-plugin-chatagent.collapsed .chatagent-toggle span {
        display: none;
    }
    .m-plugin-chatagent.collapsed .chatagent-toggle:before {
        content: '\u{1F4AC}'; /* Chat bubble icon */
        font-size: 24px;
    }

    .chatagent-title {
      font-size: 1.1em;
      font-weight: bold;
    }

    .chatagent-toggle {
      background: none;
      border: none;
      color: inherit;
      font-size: 24px;
      line-height: 1;
      cursor: pointer;
      outline: none;
      transform: rotate(0deg);
      transition: transform 0.3s ease-in-out;
    }
    .chatagent-toggle:hover {
      opacity: 0.8;
    }
    .m-plugin-chatagent.collapsed .chatagent-toggle {
      transform: rotate(180deg);
    }
    .chatagent-body {
      flex-grow: 1;
      display: flex;
      flex-direction: column;
      padding: 10px;
      background-color: var(--chatagent-bg, #ffffff);
      transition: max-height 0.3s ease-in-out;
    }

    .m-plugin-chatagent.collapsed .chatagent-body {
      display: none;
    }

    .chatagent-messages {
      flex-grow: 1;
      overflow-y: auto;
      padding-right: 5px; /* For scrollbar space */
      margin-bottom: 10px;
      max-height: 350px;
    }

    .chatagent-message-wrapper {
      display: flex;
      margin-bottom: 8px;
    }

    .chatagent-message-wrapper.user {
      justify-content: flex-end;
    }

    .chatagent-message-wrapper.assistant {
      justify-content: flex-start;
    }

    .chatagent-message {
      max-width: 80%;
      padding: 8px 12px;
      border-radius: 18px;
      line-height: 1.4;
      word-wrap: break-word;
      font-size: 0.9em;
    }

    .chatagent-message-wrapper.user .chatagent-message {
      background-color: var(--chatagent-user-bg, #2563eb);
      color: var(--chatagent-user-text, #ffffff);
      border-bottom-right-radius: 2px;
    }

    .chatagent-message-wrapper.assistant .chatagent-message {
      background-color: var(--chatagent-assistant-bg, #f3f4f6);
      color: var(--chatagent-assistant-text, #1f2937);
      border-bottom-left-radius: 2px;
    }

    .chatagent-welcome {
      background-color: #e0f2f7;
      border-left: 4px solid #0288d1;
      padding: 10px;
      border-radius: 4px;
      margin-bottom: 10px;
      font-size: 0.9em;
    }

    .chatagent-welcome ul {
      padding-left: 20px;
      margin-top: 5px;
    }

    .chatagent-input-area {
      display: flex;
      border-top: 1px solid var(--chatagent-border, #e5e7eb);
      padding-top: 10px;
      align-items: flex-end;
      position: relative;
    }

    .chatagent-input {
      flex-grow: 1;
      border: 1px solid var(--chatagent-border, #e5e7eb);
      border-radius: 18px;
      padding: 8px 12px;
      font-size: 0.9em;
      line-height: 1.4;
      resize: none;
      overflow-y: auto;
      max-height: 80px; /* Approx 4 lines */
      margin-right: 8px;
    }

    .chatagent-input:focus {
      outline: none;
      border-color: var(--chatagent-primary, #2563eb);
      box-shadow: 0 0 0 1px var(--chatagent-primary, #2563eb);
    }

    .chatagent-send {
      background-color: var(--chatagent-primary, #2563eb);
      color: white;
      border: none;
      border-radius: 50%;
      width: 36px;
      height: 36px;
      display: flex;
      justify-content: center;
      align-items: center;
      cursor: pointer;
      font-size: 1.2em;
      outline: none;
      transition: background-color 0.2s ease-in-out;
    }

    .chatagent-send:hover {
      background-color: #1d4ed8; /* Darker blue */
    }

    .chatagent-loading-indicator {
      position: absolute;
      bottom: 55px; /* Adjust based on input area height */
      left: 15px;
      display: flex;
      gap: 4px;
      opacity: 0;
      transition: opacity 0.3s ease-in-out;
    }

    .chatagent-loading-indicator.visible {
      opacity: 1;
    }

    .chatagent-loading-indicator .dot {
      width: 8px;
      height: 8px;
      background-color: var(--chatagent-primary, #2563eb);
      border-radius: 50%;
      animation: bounce 1.4s infinite ease-in-out both;
    }

    .chatagent-loading-indicator .dot:nth-child(1) { animation-delay: -0.32s; }
    .chatagent-loading-indicator .dot:nth-child(2) { animation-delay: -0.16s; }
    .chatagent-loading-indicator .dot:nth-child(3) { animation-delay: 0s; }

    @keyframes bounce {
      0%, 80%, 100% { transform: translateY(0); }
      40% { transform: translateY(-10px); }
    }

    .chatagent-sources {
      margin-top: 10px;
      font-size: 0.8em;
      color: #6b7280;
      background-color: #f9fafb;
      border-left: 3px solid #d1d5db;
      padding: 8px;
      border-radius: 4px;
    }
    .chatagent-sources summary {
      cursor: pointer;
      font-weight: bold;
    }
    .chatagent-sources details ul {
      margin-top: 5px;
      padding-left: 20px;
    }
    .chatagent-sources details ul li {
      margin-bottom: 3px;
    }
  `;

  // Inlined HTML Template (as a string literal)
  const HTML_TEMPLATE = `
    <div class="m-plugin-chatagent">
      <div class="chatagent-header">
        <span class="chatagent-title">Asistente API-IDEE</span>
        <button class="chatagent-toggle" title="Minimizar"><span>−</span></button>
      </div>
      <div class="chatagent-body">
        <div class="chatagent-messages" id="chatagent-messages">
          <!-- Messages will be appended here -->
        </div>
        <div class="chatagent-input-area">
          <textarea class="chatagent-input" placeholder="{{placeholder}}" rows="1"></textarea>
          <button class="chatagent-send" title="Enviar">
            <span>➤</span>
          </button>
        </div>
      </div>
    </div>
  `;

  // Tool executor — maps tool names to IDEE.Map calls
  const TOOL_MAP = {
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

  function executeTool(map, toolName, args) {
    var executor = TOOL_MAP[toolName];
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

  // Helper functions for DOM manipulation and messaging
  function escapeHtml(unsafe) {
    return unsafe
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // ChatAgentControl Class
  class ChatAgentControl {
    constructor(options, map) {
      this.options = options;
      this.map_ = map;
      this.conversationId = null;
      this.backendUrl = options.backendUrl;
      this.element = null; // Main chat panel DOM element
      this.messagesContainer = null;
      this.inputElement = null;
      this.sendButton = null;
      this.toggleButton = null;
      this.loadingIndicator = null;

      this.sendMessage = this.sendMessage.bind(this);
      this.handleInputKeydown = this.handleInputKeydown.bind(this);
      this.togglePanel = this.togglePanel.bind(this);
      this.appendMessage = this.appendMessage.bind(this);
      this.showLoading = this.showLoading.bind(this);
      this.adjustInputHeight = this.adjustInputHeight.bind(this);
    }

    init() {
      this.panelElement = document.createElement('div');
      this.panelElement.className = 'chatagent-panel-container';
      this.panelElement.innerHTML = HTML_TEMPLATE.replace('{{placeholder}}', escapeHtml(this.options.placeholder));
      document.body.appendChild(this.panelElement);

      const styleTag = document.createElement('style');
      styleTag.innerHTML = CSS_STYLES;
      document.head.appendChild(styleTag); // Append to head for better style management

      this.element = this.panelElement.querySelector('.m-plugin-chatagent');
      this.messagesContainer = this.element.querySelector('#chatagent-messages');
      this.inputElement = this.element.querySelector('.chatagent-input');
      this.sendButton = this.element.querySelector('.chatagent-send');
      this.toggleButton = this.element.querySelector('.chatagent-toggle');
      
      this.loadingIndicator = document.createElement('div');
      this.loadingIndicator.className = 'chatagent-loading-indicator';
      this.loadingIndicator.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
      this.inputElement.parentNode.insertBefore(this.loadingIndicator, this.inputElement.nextSibling);
      this.showLoading(false);

      // if (this.options.collapsed) { // Temporarily disable collapsed state for debugging
      //   this.element.classList.add('collapsed');
      // }


      this.sendButton.addEventListener('click', this.sendMessage);
      this.inputElement.addEventListener('keydown', this.handleInputKeydown);
      this.inputElement.addEventListener('input', this.adjustInputHeight);
      this.toggleButton.addEventListener('click', this.togglePanel);

      this.appendMessage('assistant', this.options.welcomeMessage ||
        '¡Hola! Soy el asistente de API-IDEE. Puedo ayudarte con:<ul><li>Cómo usar el visor de mapas</li><li>Añadir capas WMS, WMTS, WFS...</li><li>Desarrollar plugins</li><li>Navegar y buscar en el mapa</li></ul>');
    }

    destroy() {
      if (this.panelElement && this.panelElement.parentNode) {
        this.panelElement.parentNode.removeChild(this.panelElement);
      }
      const styleTag = document.querySelector('style[data-chatagent-plugin]'); // Assuming we add a data-attribute
      if (styleTag) { styleTag.parentNode.removeChild(styleTag); }
      
      this.sendButton.removeEventListener('click', this.sendMessage);
      this.inputElement.removeEventListener('keydown', this.handleInputKeydown);
      this.inputElement.removeEventListener('input', this.adjustInputHeight);
      this.toggleButton.removeEventListener('click', this.togglePanel);
    }

    async createConversation() {
      try {
        const res = await fetch(`${this.backendUrl}/conversations/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        const data = await res.json();
        this.conversationId = data.id;
      } catch (error) {
        console.error('Error creating conversation:', error);
        this.appendMessage('system', 'Error al iniciar la conversación. Por favor, inténtalo de nuevo más tarde.');
      }
    }

    getMapState() {
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

    async sendMessage(event) {
      if (event && event.preventDefault) { event.preventDefault(); }
      const content = this.inputElement.value.trim();
      if (!content) return;

      this.inputElement.value = '';
      this.adjustInputHeight();

      if (!this.conversationId) {
        await this.createConversation();
        if (!this.conversationId) return;
      }

      this.appendMessage('user', content);
      this.showLoading(true);

      try {
        const mapState = this.getMapState();
        const res = await fetch(
          `${this.backendUrl}/conversations/${this.conversationId}/chat/`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content, map_state: mapState }),
          }
        );
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        const data = await res.json();

        // Handle tool calls from the server
        if (data.type === 'tool_call' && data.tool_calls && data.tool_calls.length > 0) {
          if (data.content) {
            this.appendMessage('assistant', data.content);
          }
          await this.handleToolCalls(data.tool_calls);
        } else {
          this.appendMessage('assistant', data.content, data.metadata?.sources);
        }
      } catch (error) {
        console.error('Error sending message:', error);
        this.appendMessage('system', 'Error al enviar el mensaje. Por favor, inténtalo de nuevo.');
      } finally {
        this.showLoading(false);
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
      }
    }

    async handleToolCalls(toolCalls) {
      for (const tc of toolCalls) {
        const toolName = tc.name;
        const toolArgs = tc.args || {};
        const toolCallId = tc.id || '';

        // Execute tool on the map
        const result = executeTool(this.map_, toolName, toolArgs);

        // Send result back to the server
        try {
          const res = await fetch(
            `${this.backendUrl}/conversations/${this.conversationId}/tool-result/`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                tool_name: toolName,
                tool_call_id: toolCallId,
                result: result,
                success: result.success !== false,
              }),
            }
          );
          if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
          const data = await res.json();

          // The server returns the final LLM response after processing the tool result
          if (data.type === 'tool_call' && data.tool_calls && data.tool_calls.length > 0) {
            // Chain: more tool calls needed
            if (data.content) {
              this.appendMessage('assistant', data.content);
            }
            await this.handleToolCalls(data.tool_calls);
          } else {
            this.appendMessage('assistant', data.content, data.metadata?.sources);
          }
        } catch (error) {
          console.error('Error sending tool result:', error);
          this.appendMessage('system', 'Error al ejecutar la herramienta. Por favor, inténtalo de nuevo.');
        }
      }
    }

    handleInputKeydown(event) {
      if (event.key === 'Enter' && !event.shiftKey) {
        this.sendMessage(event);
      }
    }
    
    appendMessage(role, content, sources = []) {
      const messageWrapper = document.createElement('div');
      messageWrapper.className = `chatagent-message-wrapper ${role}`;

      const messageDiv = document.createElement('div');
      messageDiv.className = 'chatagent-message';
      messageDiv.innerHTML = content; // Using innerHTML for formatting, but sanitize if user input

      messageWrapper.appendChild(messageDiv);
      this.messagesContainer.appendChild(messageWrapper);

      if (sources && sources.length > 0) {
        const sourcesDetails = document.createElement('details');
        sourcesDetails.className = 'chatagent-sources';
        const summary = document.createElement('summary');
        summary.textContent = 'Fuentes citadas';
        sourcesDetails.appendChild(summary);

        const ul = document.createElement('ul');
        sources.forEach(source => {
          const li = document.createElement('li');
          li.textContent = `${source.source} (chunk ${source.chunk_index})`;
          ul.appendChild(li);
        });
        sourcesDetails.appendChild(ul);
        this.messagesContainer.appendChild(sourcesDetails);
      }
      this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }

    showLoading(visible) {
      if (visible) {
        this.loadingIndicator.classList.add('visible');
      } else {
        this.loadingIndicator.classList.remove('visible');
      }
    }

    togglePanel() {
      this.element.classList.toggle('collapsed');
      const toggleText = this.toggleButton.querySelector('span');
      if (this.element.classList.contains('collapsed')) {
        toggleText.textContent = '+ ';
        this.toggleButton.setAttribute('title', 'Maximizar');
      } else {
        toggleText.textContent = '−';
        this.toggleButton.setAttribute('title', 'Minimizar');
      }
    }

    adjustInputHeight() {
      this.inputElement.style.height = 'auto'; // Reset height
      this.inputElement.style.height = this.inputElement.scrollHeight + 'px';
    }
  }

  // ChatAgent Facade Class
  class ChatAgent extends (window.IDEE && window.IDEE.Plugin ? IDEE.Plugin : Object) {
    constructor(options = {}) {
      super();
      this.options = {
        position: 'TR',
        collapsed: true,
        collapsible: true,
        backendUrl: 'http://localhost:8000/api',
        tooltip: 'Asistente API-IDEE',
        placeholder: 'Pregunta sobre API-IDEE...',
        welcomeMessage: undefined,
        ...options
      };
      this.control_ = null;
    }

    addTo(map) {
      this.map_ = map;
      this.control_ = new ChatAgentControl(this.options, map);
      this.control_.init();
    }

    destroy() {
      if (this.control_) {
        this.control_.destroy();
      }
      this.control_ = null;
    }

    open() {
      if (this.control_ && this.control_.element) { this.control_.element.classList.remove('collapsed'); }
    }

    close() {
      if (this.control_ && this.control_.element) { this.control_.element.classList.add('collapsed'); }
    }

    toggle() {
      if (this.control_ && this.control_.element) { this.control_.togglePanel(); }
    }
  }

  // Register the plugin with IDEE
  if (window.IDEE) {
    if (!IDEE.plugin) {
      IDEE.plugin = {};
    }
    IDEE.plugin.ChatAgent = ChatAgent;
  }
})();
