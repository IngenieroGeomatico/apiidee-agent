# API-IDEE Agent

Agente IA para el visualizador de mapas [API-IDEE](https://github.com/Desarrollos-IDEE/API-IDEE). Combina un servidor Django con RAG (Retrieval-Augmented Generation) y un plugin nativo del visualizador que permite interactuar con el mapa mediante chat.

## Arquitectura

```
                        Plugin JS (navegador)
                     ┌──────────────────────────┐
                     │  Chat UI  ←→  TOOL_MAP   │
                     │         ↕     ↕          │
                     │      IDEE.Map (OL/Cesium)│
                     └───────────┬──────────────┘
                                 │ REST
                     ┌───────────▼──────────────┐
                     │   Servidor Django         │
                     │                           │
                     │  Agent ← Skills + Tools   │
                     │    ↕         ↕             │
                     │  LLM    RAG (FAISS)       │
                     └───────────────────────────┘
```

## Conceptos clave (teoria)

### Agent

Un **agente** es un programa que percibe su entorno, razona sobre ello y ejecuta acciones para lograr un objetivo. A diferencia de un simple "LLM call", un agente:

1. **Recibe entrada** — el mensaje del usuario y el estado actual del mapa
2. **Busca contexto** — consulta RAG para obtener informacion relevante (codigo fuente, documentacion)
3. **Razona** — construye un prompt con skills activos + contexto + estado y llama al LLM
4. **Decide** — el LLM puede responder texto o solicitar la ejecucion de una tool
5. **Itera** — si se ejecuto una tool, el agente procesa el resultado y genera una respuesta final

El agente **no ejecuta las tools** directamente, solo decide cual invocar. La ejecucion ocurre en el navegador. Esto sigue el patron **"el agente piensa, el plugin actua"**.

```
Mensaje usuario
     │
     ▼
┌──────────┐   ┌────────┐   ┌──────┐
│ Buscar   │──▶│ LLM    │──▶│Text  │──▶ Respuesta
│ contexto │   │+ tools │   │o tool│
│ (RAG)    │   │        │   │_call │
└──────────┘   └────────┘   └──┬───┘
                               │ tool_call
                               ▼
                         ┌──────────┐   ┌────────┐
                         │ Plugin   │──▶│ LLM    │──▶ Texto final
                         │ ejecuta  │   │procesa │
                         │ tool     │   │result. │
                         └──────────┘   └────────┘
```

Ubicacion: `servidor/agent/agent.py`

### Tool

Una **tool** es una accion atomica que el agente puede invocar. Cada tool tiene:

- **Nombre** — identificador unico (ej: `zoomTo`)
- **Descripcion** — texto que el LLM lee para entender cuando usarla
- **Parametros** — esquema JSON con los argumentos que necesita

Las tools se definen en JSON en el servidor y se implementan en JavaScript en el plugin. El LLM nunca ejecuta la tool directamente; solo genera una solicitud de llamada (tool_call) con los argumentos adecuados. El plugin recibe la solicitud, ejecuta la tool sobre el mapa real, y devuelve el resultado al servidor.

```
LLM decide usar tool
       │
       ▼
tool_call { name: "zoomTo", args: { lat: 40.4, lon: -3.7 } }
       │
       ▼
Plugin ejecuta: map.setCenter({ x: -3.7, y: 40.4 })
       │
       ▼
Devuelve { success: true }
       │
       ▼
LLM procesa resultado y responde al usuario
```

Una tool es como una **función** que el agente puede "llamar" pero que ejecuta otro sistema. No hay logica en el servidor para la tool — solo la definicion de su interfaz.

**Donde vive**: Definicion en `servidor/agent/tools/definitions/*.json`, implementacion en `plugin/chatagent.js` (CHATAGENT_TOOL_MAP).

### Skill

Un **skill** es conocimiento de dominio que agrupa:

1. **Un conjunto de tools** relacionadas
2. **Un prompt especializado** que le dice al LLM *como* y *cuando* usarlas

Mientras que una tool solo dice "que hace", un skill dice "como usarla bien". Por ejemplo, el skill `navigation` incluye:

```yaml
tools: [getMapCenter, getCurrentZoom, zoomTo, setZoom]
prompt: |
  Cuando el usuario quiera navegar:
  1. Usa getMapCenter() para saber donde esta
  2. Usa zoomTo(lat, lon, zoom) para mover el mapa
  Siempre confirma lo que hiciste.
```

Los skills se inyectan en el system prompt del LLM, por lo que actuan como **instrucciones contextuales** que mejoran la calidad de las respuestas sin necesidad de fine-tuning.

A diferencia de las tools (que son puramente mecanicas), los skills codifican **buenas practicas** y **flujos de trabajo** especificos del dominio.

**Donde vive**: `servidor/agent/skills/definitions/*.yaml`

### Embedding

Un **embedding** es una representacion numerica de texto en forma de vector (lista de numeros). La idea clave es:

- Textos con significado similar tienen vectores **cercanos** (distancia pequena)
- Textos con significado diferente tienen vectores **lejanos** (distancia grande)

Esto permite busqueda semantica: en vez de buscar por palabras exactas (como `grep`), podemos buscar por **significado**. Por ejemplo, "como anyado una capa al mapa" y "anadir wms" generan vectores cercanos aunque no compartan palabras.

En el proyecto, los embeddings se usan en el pipeline RAG:

1. **Indexacion**: los documentos (codigo, documentacion) se trocean en chunks y cada chunk se convierte a vector con un modelo de embeddings. Los vectores se guardan en FAISS (indice de busqueda vectorial).
2. **Consulta**: el mensaje del usuario se convierte al mismo tipo de vector. FAISS busca los chunks con vectores mas cercanos y los devuelve como contexto para el LLM.

El proyecto soporta tres tipos de embeddings:

| Tipo | Modelo por defecto | Requisito | Uso recomendado |
|------|--------------------|-----------|-----------------|
| Local (FastEmbed) | `BAAI/bge-m3` (multilingüe) | Ninguno (descarga ~80MB) | Offline, privacidad total |
| OpenAI | `text-embedding-3-small` | API key de OpenAI | Alta calidad, ingles |
| Gemini | `models/embedding-001` | API key de Google | Alta calidad, multilingue |

El modelo por defecto es **local** con `BAAI/bge-m3`, un modelo multilingüe gratuito que funciona bien con espanol. El resultado de `get_embeddings()` se **cachea** para evitar recrear el modelo en cada peticion.

**Donde vive**: `servidor/agent/rag/embeddings.py`

### MCP (Model Context Protocol)

**MCP** (Model Context Protocol) es un protocolo abierto creado por Anthropic que estandariza como los modelos de IA se conectan con herramientas y fuentes de datos externas. Piensa en el como un "USB-C para la IA": define una interfaz universal donde servidores MCP exponen tools, recursos y prompts mediante JSON-RPC.

En este proyecto, MCP convive con el sistema de tools nativo:

- **Tools del mapa** (nativas): se definen en `tools/definitions/*.json`, se ejecutan en el navegador via el plugin JS.
- **Tools MCP** (externas): se descubren automaticamente via `tools/list` al arrancar el servidor, se ejecutan en el servidor via JSON-RPC.

El LLM no distingue el origen de una tool — solo ve su nombre, descripcion y parametros. Cuando el LLM decide llamar a una tool MCP, el agente la ejecuta directamente en el servidor, realimenta el resultado al LLM y continua la conversacion en un bucle. Las tools del mapa se siguen devolviendo al frontend como antes.

```
LLM decide usar tool
       │
       ▼
tool_call { name: "get_weather", args: { city: "Madrid" } }
       │
       ▼
┌─ ¿Es MCP? ─────────────────────────────┐
│ Sí → Servidor ejecuta via JSON-RPC      │
│      │                                  │
│      ▼                                  │
│ Resultado → se realimenta al LLM        │
│      │                                  │
│      ▼                                  │
│ LLM responde texto o nuevos tool_calls   │
└─────────────────────────────────────────┘
       │
       ▼
┌─ ¿Es del mapa? ────────────────────────┐
│ Sí → Se devuelve al plugin JS           │
│      (como siempre)                     │
└─────────────────────────────────────────┘
```

Las tools MCP son ideales para operaciones que no requieren el mapa: consultar APIs externas, bases de datos, sistemas de ficheros, etc.

**Donde vive**: `servidor/agent/mcp/` — configuracion en `mcp_servers.json`

### Resumen visual de las relaciones

```
SKILL (YAML)                 TOOL (JSON)                AGENT (Python)
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│ navigation        │       │ zoomTo {         │       │ Agent.run()       │
│ tools:            │──────▶│   lat, lon, zoom │       │  1. RAG context   │
│   - zoomTo        │       │ }                │       │  2. Skills prompt │
│   - setZoom       │       ├──────────────────┤       │  3. LLM call      │
│   - getMapCenter  │       │ setZoom {        │       │  4. tool_call?    │
│ prompt: |         │──────▶│   level          │       └──────────────────┘
│   "Instrucciones  │       │ }                │              │
│    para navegar"  │       ├──────────────────┤              ▼
└──────────────────┘       │ getMapCenter {}   │      ┌──────────────────┐
                            └──────────────────┘      │ PLUGIN (JS)      │
                                                       │ CHATAGENT_TOOL_MAP│
                                                       │   zoomTo: fn()    │
                                                       │   setZoom: fn()   │
                                                       └──────────────────┘

EMBEDDINGS (modelo)          FAISS (indice)
┌──────────────────┐       ┌──────────────────┐
│ "texto" ──▶ [0.1, │       │  Chunk 1: vector A│
│             0.3,  │──────▶│  Chunk 2: vector B│
│             0.8]  │       │  Chunk 3: vector C│
└──────────────────┘       └──────────────────┘
                                  │
                                  ▼
                          ┌──────────────────┐
                          │ retrieve_context  │  ← Consulta: embedding del mensaje
                          │ Devuelve top-k    │
                          │ chunks similares  │
                          └──────────────────┘
```

## Arquitectura: como se conectan Agent, Skills, Tools, Embeddings

```
                    ┌──────────────────────────────────────┐
                    │            USUARIO (Chat)             │
                    └──────────────┬───────────────────────┘
                                   │
                    ┌──────────────▼───────────────────────┐
                    │              AGENT                    │
                    │        (servidor/agent/agent.py)      │
                    │                                      │
                    │  1. Recibe el mensaje del usuario     │
                    │  2. Consulta RAG para contexto        │
                    │  3. Construye system prompt con:      │
                    │     - Prompt base                     │
                    │     - Skills activos (tools + prompt) │
                    │     - Contexto RAG                    │
                    │     - Estado del mapa                 │
                    │  4. Llama al LLM con tools disponibles│
                    │  5. Devuelve texto o tool_call        │
                    └────┬─────────┬──────────┬────────────┘
                         │         │          │
                         │         │          │
          ┌──────────────▼──┐ ┌───▼────────┐ │
          │     RAG         │ │   LLM      │ │
          │ (contexto       │ │ (Gemini /  │ │
          │  semantico)     │ │  OpenAI)   │ │
          │                 │ │            │ │
          │  FAISS stores   │ │            │ │
          │  (cacheadas)    │ │            │ │
          │  ↑              │ │            │ │
          │  Embeddings     │ │            │ │
          │  (local/API)    │ │            │ │
          │  (cache)        │ │            │ │
          └─────────────────┘ └────────────┘ │
                                             │
                         ┌───────────────────▼──────────┐
                         │        TOOLS (plugin JS)      │
                         │  Ej: zoomTo, addWMSLayer, ... │
                         │  Se ejecutan en el navegador  │
                         └──────────────────────────────┘
```

### Flujo detallado

1. **Skills** → definen herramientas + contexto de uso. Ej: el skill `navigation` agrupa `zoomTo`, `getMapCenter` y da instrucciones al LLM sobre como navegar.

2. **Tools** → acciones atomicas definidas en JSON (servidor) e implementadas en JS (plugin). El LLM decide cual invocar segun la peticion del usuario.

3. **RAG (Embeddings + FAISS)** → los documentos se trocean en chunks, se convierten a vectores con un modelo de embeddings y se guardan en FAISS. En cada consulta, el mensaje del usuario se convierte al mismo tipo de vector y se buscan los chunks mas similares. Las stores FAISS y los modelos de embeddings se **cachean en memoria** para evitar recargarlos en cada peticion.

4. **Agent** → orquesta todo: recibe el mensaje, pide contexto a RAG, inyecta los skills activos y el estado del mapa en el prompt, llama al LLM, y si el LLM devuelve un tool_call, lo reenvia al plugin para ejecutarlo.

### Donde se configura cada pieza

| Pieza | Configuracion | Proveedores |
|-------|--------------|-------------|
| **LLM** | `LLM_PROVIDER` + `LLM_MODEL` en `.env`, o API key propia desde el plugin | Gemini, OpenAI (y cualquier proveedor compatible con API OpenAI via `providers.json`) |
| **Embeddings** | `EMBEDDINGS_PROVIDER` + `EMBEDDINGS_MODEL` en `.env` | Local (FastEmbed, default `BAAI/bge-m3`), OpenAI, Gemini |
| **Tools** | JSON en `servidor/agent/tools/definitions/` | Auto-descubiertos al arrancar |
| **Skills** | YAML en `servidor/agent/skills/definitions/` | Auto-descubiertos al arrancar |
| **RAG** | `index_source` CLI + `VECTORSTORE_DIR` en `.env` | FAISS + embeddings (cacheados en memoria) |

## Requisitos

- Python 3.11+
- Git
- Una API key de un proveedor LLM:
  - [Google Gemini](https://aistudio.google.com/app/apikey) (gratuita)
  - [OpenAI](https://platform.openai.com/api-keys)
  - Cualquier proveedor compatible con API OpenAI (Groq, Cerebras, OpenRouter, etc.)

## Instalacion

### 1. Clonar el repositorio

```bash
git clone https://github.com/IngenieroGeomatico/apiidee-agent.git
cd apiidee-agent
```

### 2. Configurar el servidor

```bash
cd servidor

# Crear entorno virtual
python -m venv .venv

# Activar entorno virtual
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tu API key (ver seccion Configuracion)

# Crear base de datos
python manage.py migrate

# Arrancar servidor
python manage.py runserver
```

### 3. Servir el visualizador

En otra terminal, desde la raiz del proyecto:

```bash
python -m http.server 8080
```

### 4. Abrir el visualizador

Navegar a `http://localhost:8080/index.html`

## Configuracion

Editar `servidor/.env`:

```env
# --- Proveedor LLM ---

# Opcion A: Google Gemini (gratuita)
LLM_PROVIDER=gemini
LLM_MODEL=gemini-pro
GOOGLE_API_KEY=AIza...

# Opcion B: OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...

# --- Django ---
SECRET_KEY=cambia-esto-por-una-clave-secreta
DEBUG=True

# --- CORS ---
ALLOWED_ORIGINS=http://localhost:8080,http://localhost:3000

# --- Embeddings (opcional, por defecto local) ---
EMBEDDINGS_PROVIDER=local
EMBEDDINGS_MODEL=BAAI/bge-m3
```

### API keys desde el plugin (claves de usuario)

El usuario puede guardar sus propias API keys directamente desde el chat, con **nombre personalizado**. Las keys se guardan exclusivamente en el **navegador (localStorage)** y persisten entre sesiones. Nunca se almacenan en el servidor.

#### Cómo funciona

1. Haz clic en el icono de **engranaje (⚙)** en la cabecera del chat
2. Se abre el panel de configuración con las claves guardadas y el formulario para añadir nuevas
3. Para guardar una clave:
   - Escribe un **nombre personalizado** (ej: "Mi API de Groq", "Producción", "Test")
   - **Selecciona el proveedor** del desplegable (los disponibles en el servidor)
   - Introduce tu **API key**
   - Haz clic en **Probar** — el servidor verifica la key contra el proveedor (`GET {base_url}/models`)
   - Si la key es válida, haz clic en **Guardar**
4. Las claves guardadas aparecen listadas con el nombre, proveedor y key parcialmente oculta
5. Para eliminar una clave, haz clic en **×** a la derecha

> El botón **Guardar** solo se activa tras pulsar **Probar** y recibir validación correcta.

#### Selección en la barra superior

Las claves guardadas aparecen como opciones seleccionables en el desplegable de proveedores de la barra superior, separadas de los proveedores del servidor por una línea `─── Tus claves ───`. Cada entrada se muestra con un icono 🔑 y su **nombre personalizado**. Al seleccionar una:

- Su `api_key` se envía automáticamente con cada mensaje y resultado de tool
- El proveedor subyacente se usa para cargar los modelos disponibles
- El campo `api_key` solo viaja en memoria durante la petición HTTPS — **no se almacena en la base de datos del servidor** ni en logs

Puedes tener múltiples entradas para un mismo proveedor con distintas keys y nombres.

Puedes usar cualquier proveedor compatible con la API de OpenAI (Groq, Cerebras, OpenRouter, etc.) que esté configurado en el servidor a través de `providers.json`.

## Indexar conocimiento (RAG)

El agente necesita conocimiento para responder. Usa el comando `index_source` para indexar repositorios git o documentacion web:

```bash
cd servidor

# Indexar un repositorio git
python manage.py index_source https://github.com/Desarrollos-IDEE/API-IDEE --type git

# Indexar documentacion web (crawlea hasta 50 paginas del mismo dominio)
python manage.py index_source https://github.com/Desarrollos-IDEE/API-IDEE/wiki --type web

# Con nombre personalizado
python manage.py index_source https://componentes.idee.es/api-idee/doc/ --type web --name api-idee-docs

# Reducir batch-size si tienes poca RAM (procesa chunks de 50 en 50)
python manage.py index_source https://github.com/Desarrollos-IDEE/API-IDEE --type git --batch-size 50
```

Los indices se guardan en `servidor/vectorstore_data/` (no se suben al repo). Una vez indexados, las stores FAISS se **cachean en memoria** para que las consultas sean rapidas sin recargar de disco.

> **Nota**: `--batch-size` controla cuantos chunks se embeden a la vez. Por defecto 100. Reducirlo baja el consumo de RAM pero ralentiza el proceso.

> **Nota**: Si reindexas una fuente, usa `clear_faiss_cache()` o reinicia el servidor para que los cambios surtan efecto.

## Anadir tools

Los tools son acciones que el agente puede ejecutar en el mapa. Tienen dos partes:

### 1. Definicion (servidor)

Crear un fichero JSON en `servidor/agent/tools/definitions/`:

```json
{
  "name": "miNuevoTool",
  "description": "Descripcion de lo que hace (el LLM lee esto para decidir cuando usarlo)",
  "parameters": {
    "type": "object",
    "properties": {
      "param1": { "type": "string", "description": "Descripcion del parametro" }
    },
    "required": ["param1"]
  }
}
```

### 2. Ejecutor (plugin JS)

Anadir la implementacion en `plugin/chatagent.js`, dentro de `CHATAGENT_TOOL_MAP`:

```javascript
miNuevoTool: function(map, args) {
    // Llamar a metodos de IDEE.Map
    // ...
    return { success: true, resultado: '...' };
},
```

No hay que tocar Python. El sistema auto-descubre los JSON al arrancar.

### Tools disponibles

| Tool | Tipo | Descripcion |
|------|------|-------------|
| `getMapCenter` | Lectura | Coordenadas del centro del mapa |
| `getCurrentZoom` | Lectura | Nivel de zoom actual |
| `listActiveLayers` | Lectura | Lista de capas activas |
| `getMapExtent` | Lectura | Bounding box de la vista actual |
| `addWMSLayer` | Escritura | Anadir capa WMS al mapa |
| `zoomTo` | Escritura | Mover el mapa a coordenadas |
| `removeLayer` | Escritura | Eliminar una capa por nombre |
| `setZoom` | Escritura | Cambiar nivel de zoom |

## Anadir skills

Los skills enseñan al agente cuando y como usar un grupo de tools. Son ficheros YAML.

Crear un fichero en `servidor/agent/skills/definitions/`:

```yaml
name: mi_skill
description: Descripcion del dominio de conocimiento
tools:
  - tool1
  - tool2
  - tool3
prompt: |
  Instrucciones para el LLM sobre como usar estos tools:
  1. Primero haz X
  2. Luego haz Y
  3. Siempre confirma al usuario lo que hiciste
```

No hay que tocar Python. El sistema auto-descubre los YAML al arrancar.

### Skills disponibles

| Skill | Tools que usa | Descripcion |
|-------|---------------|-------------|
| `navigation` | getMapCenter, getCurrentZoom, getMapExtent, zoomTo, setZoom | Navegar por el mapa y buscar ubicaciones |
| `layer_management` | listActiveLayers, addWMSLayer, removeLayer | Gestionar capas del visualizador |

## Integracion MCP

Este proyecto soporta el protocolo MCP (Model Context Protocol) para conectar con servidores externos de herramientas. Las tools MCP se descubren automaticamente, se registran junto a las tools nativas del mapa y se ejecutan en el servidor.

### Como agregar un servidor MCP

Las tools del mapa y las MCP conviven sin conflicto. Si una tool MCP tiene el mismo nombre que una existente, se omite con un aviso.

### 1. Copiar el archivo de configuracion

```bash
cd servidor
cp mcp_servers.json.example mcp_servers.json
```

### 2. Configurar los servidores MCP

Editar `servidor/mcp_servers.json`:

```json
[
  {
    "name": "mi-servidor",
    "url": "http://localhost:8001",
    "timeout": 30
  }
]
```

| Campo | Descripcion |
|-------|-------------|
| `name` | Nombre identificativo del servidor (solo para logs) |
| `url` | Endpoint HTTP donde el servidor MCP acepta JSON-RPC |
| `timeout` | Tiempo maximo de espera en segundos (opcional, por defecto 30) |

### 3. Arrancar el servidor Django

Al iniciar, el sistema se conecta a los servidores MCP configurados, descubre sus tools via `tools/list` y las registra automaticamente:

```bash
python manage.py runserver
```

Veras en los logs algo como:

```
Connected to MCP server 'mi-servidor' (3 tools)
Registered 3 MCP tools in the tool registry
```

A partir de ahi, el LLM puede invocar las tools MCP como si fueran nativas. No hace falta reiniciar ni tocar codigo.

### MCP es opcional

Si no configuras servidores MCP, el sistema funciona exactamente igual que antes — el agente simplemente no tiene tools MCP registradas y todo el flujo sigue yendo al frontend. Los tres procesos posibles quedarian asi:

| Proceso | Comando | Puerto | Obligatorio |
|---------|---------|--------|-------------|
| Visualizador API-IDEE | `python -m http.server 8080` | 8080 | Recomendado (o abrir `index.html` directamente) |
| Agente Django | `python manage.py runserver` | 8000 | Sí |
| Servidor MCP | `python test_mcp_server.py` | 8001 | Solo si usas MCP |

## Mejoras de rendimiento recientes

### Cache de embeddings

El modelo de embeddings se crea una sola vez y se reusa en todas las peticiones (singleton). Esto evita el overhead de cargar el modelo en cada llamada a RAG.

### Cache de FAISS stores

Los indices FAISS se cargan desde disco una unica vez y se mantienen en memoria. Las consultas posteriores son instantaneas sin acceso a disco. Si se reindexa una fuente, llama a `clear_faiss_cache()` o reinicia el servidor.

### Modelo de embeddings multilingüe

El modelo local por defecto es `BAAI/bge-m3`, que soporta espanol y otros idiomas, a diferencia del anterior `bge-small-en-v1.5` que solo funcionaba bien en ingles.

## Estructura del proyecto

```
apiidee-agent/
├── servidor/                          # Servidor Django
│   ├── manage.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── config/                       # Configuracion Django
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── ...
│   ├── agent/                        # App del agente
│   │   ├── agent.py                  # Clase Agent (orquestador)
│   │   ├── views.py                  # Wrapper HTTP (API REST)
│   │   ├── models.py                 # Conversation, Message
│   │   ├── prompts.py                # System prompt
│   │   ├── serializers.py            # DRF serializers
│   │   ├── urls.py                   # Rutas API
│   │   ├── llm/                      # Proveedores LLM
│   │   │   ├── providers.py          # OpenAI, Gemini, OpenAICompatible
│   │   │   └── config.py             # Factory
│   │   ├── rag/                      # Pipeline RAG
│   │   │   ├── indexer.py            # BaseIndexer + GitRepoIndexer + WebIndexer
│   │   │   ├── chunking.py           # Chunking por funciones/clases/headings
│   │   │   ├── embeddings.py         # Embeddings factory (cache singleton)
│   │   │   └── retriever.py          # Query FAISS (stores cacheadas)
│   │   ├── tools/                    # Definiciones de tools
│   │   │   ├── registry.py           # Auto-descubre definitions/*.json
│   │   │   └── definitions/          # <-- ANADIR TOOLS AQUI
│   │   │       ├── getMapCenter.json
│   │   │       ├── addWMSLayer.json
│   │   │       └── ...
│   │   ├── mcp/                      # Cliente MCP (Model Context Protocol)
│   │   │   ├── client.py             # Cliente JSON-RPC sobre HTTP
│   │   │   └── manager.py            # Singleton que gestiona N servidores MCP
│   │   └── skills/                   # Definiciones de skills
│   │       ├── base.py               # Auto-descubre definitions/*.yaml
│   │       └── definitions/          # <-- ANADIR SKILLS AQUI
│   │           ├── navigation.yaml
│   │           └── layer_management.yaml
│   └── vectorstore/                  # Gestion de indices
│       ├── models.py                 # KnowledgeSource
│       ├── store.py                  # Wrapper FAISS
│       └── management/commands/
│           └── index_source.py       # CLI: python manage.py index_source
├── plugin/                           # Plugin API-IDEE (JS puro)
│   ├── chatagent.js                  # Plugin (patron IDEE.ui.Panel + IDEE.Control)
│   ├── chatagent.css                 # Estilos
│   ├── api.json                      # Definicion del plugin
│   └── README.md                     # Documentacion del plugin
├── index.html                        # Pagina de prueba con visualizador API-IDEE
└── .gitignore
```

## API REST

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| `POST` | `/api/conversations/` | Crear conversacion |
| `GET` | `/api/conversations/` | Listar conversaciones |
| `GET` | `/api/conversations/{id}/` | Obtener conversacion |
| `DELETE` | `/api/conversations/{id}/` | Eliminar conversacion |
| `GET` | `/api/conversations/{id}/messages/` | Listar mensajes |
| `POST` | `/api/conversations/{id}/chat/` | Enviar mensaje (responde texto o tool_call) |
| `POST` | `/api/conversations/{id}/tool-result/` | Enviar resultado de ejecucion de tool |
| `POST` | `/api/test-key/` | Probar API key contra un proveedor (`provider` + `api_key`) |

### Ejemplo: enviar mensaje

```
POST /api/conversations/{id}/chat/
Content-Type: application/json

{
  "content": "Llevame a Madrid",
  "map_state": {
    "center": { "lat": 40.0, "lon": -3.0 },
    "zoom": 5,
    "srs": "EPSG:3857"
  }
}
```

Respuesta texto:
```json
{
  "id": "...",
  "type": "text",
  "role": "assistant",
  "content": "Madrid es la capital de Espana...",
  "metadata": { "sources": [...] }
}
```

Respuesta tool_call:
```json
{
  "id": "...",
  "type": "tool_call",
  "role": "assistant",
  "content": "Moviendo el mapa a Madrid...",
  "tool_calls": [
    { "name": "zoomTo", "args": { "lat": 40.417, "lon": -3.703, "zoom": 14 }, "id": "..." }
  ]
}
```

### Enviar mensaje con API key propia

```json
POST /api/conversations/{id}/chat/
Content-Type: application/json

{
  "content": "Llevame a Madrid",
  "provider": "groq",
  "model": "llama-3.1-70b-versatile",
  "api_key": "gsk_tu_api_key_aqui"
}
```

El campo `api_key` es opcional. Si se omite, se usa la clave configurada en el servidor. Cuando el usuario ha guardado una API key para el proveedor seleccionado desde el plugin, el campo `api_key` se envia automaticamente con cada mensaje.

## Plugin API-IDEE

El plugin se integra como cualquier otro plugin de API-IDEE:

```html
<!-- CSS -->
<link href="plugin/chatagent.css" rel="stylesheet" />
<!-- JS -->
<script src="plugin/chatagent.js"></script>

<script>
  const map = IDEE.map({ container: 'mapjs' });

  const chatAgent = new IDEE.plugin.ChatAgent({
    position: 'TR',
    collapsed: true,
    backendUrl: 'http://localhost:8000/api',
    tooltip: 'Asistente API-IDEE',
    placeholder: 'Pregunta sobre API-IDEE...',
  });

  map.addPlugin(chatAgent);
</script>
```

El plugin incluye un boton de configuracion (⚙) en la cabecera que permite al usuario:
- Seleccionar proveedor y modelo
- Introducir su propia API key

## Flujo de ejecucion

```
1. Usuario escribe mensaje en el chat
2. Plugin JS envia POST /api/conversations/{id}/chat/ con mensaje + estado del mapa
   (y opcionalmente provider, model, api_key)
3. Servidor Django:
   a. Busca contexto relevante en FAISS (RAG) — stores cacheadas en memoria
   b. Construye system prompt = base + skills + contexto + estado del mapa
   c. Llama al LLM con tools disponibles (usando API key del usuario si se proporciono)
   d. Si el LLM decide usar un tool → responde type="tool_call"
   e. Si no → responde type="text"
4. Si tool_call:
   a. Plugin JS ejecuta el tool en IDEE.Map (TOOL_MAP)
   b. Plugin envia resultado a POST /api/conversations/{id}/tool-result/
   c. Servidor llama al LLM con el resultado → responde texto final
5. Plugin muestra la respuesta al usuario
```

## Licencia

EUPL-1.2
