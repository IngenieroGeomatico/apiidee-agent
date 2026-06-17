# API-IDEE Agent

Agente IA para el visor de mapas [API-IDEE](https://github.com/Desarrollos-IDEE/API-IDEE). Combina un servidor Django con RAG (Retrieval-Augmented Generation) y un plugin nativo del visor que permite interactuar con el mapa mediante chat.

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

### Conceptos clave

| Concepto | Que es | Donde vive |
|----------|--------|------------|
| **Agent** | El cerebro. Orquesta RAG, skills, tools y LLM para responder al usuario | `backend/agent/agent.py` |
| **Tool** | Una accion atomica que el agente puede invocar en el mapa (se ejecuta en el navegador) | `backend/agent/tools/definitions/*.json` + `plugin/chatagent.js` (TOOL_MAP) |
| **Skill** | Conocimiento de dominio: agrupa tools + prompt especializado que ensena al agente cuando y como usarlos | `backend/agent/skills/definitions/*.yaml` |
| **RAG** | Busqueda semantica sobre repositorios y webs indexadas para dar contexto al agente | `backend/agent/rag/` + `backend/vectorstore/` |

## Requisitos

- Python 3.11+
- Git
- Una API key de un proveedor LLM:
  - [Google Gemini](https://aistudio.google.com/app/apikey) (gratuita)
  - [OpenAI](https://platform.openai.com/api-keys)

## Instalacion

### 1. Clonar el repositorio

```bash
git clone https://github.com/IngenieroGeomatico/apiidee-agent.git
cd apiidee-agent
```

### 2. Configurar el servidor

```bash
cd backend

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

### 3. Servir el visor

En otra terminal, desde la raiz del proyecto:

```bash
python -m http.server 8080
```

### 4. Abrir el visor

Navegar a `http://localhost:8080/index.html`

## Configuracion

Editar `backend/.env`:

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
```

## Indexar conocimiento (RAG)

El agente necesita conocimiento para responder. Usa el comando `index_source` para indexar repositorios git o documentacion web:

```bash
cd backend

# Indexar un repositorio git
python manage.py index_source https://github.com/Desarrollos-IDEE/API-IDEE --type git

# Indexar documentacion web (crawlea hasta 50 paginas del mismo dominio)
python manage.py index_source https://github.com/Desarrollos-IDEE/API-IDEE/wiki --type web

# Con nombre personalizado
python manage.py index_source https://componentes.idee.es/api-idee/doc/ --type web --name api-idee-docs
```

Los indices se guardan en `backend/vectorstore_data/` (no se suben al repo).

## Anadir tools

Los tools son acciones que el agente puede ejecutar en el mapa. Tienen dos partes:

### 1. Definicion (servidor)

Crear un fichero JSON en `backend/agent/tools/definitions/`:

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

Los skills ensenyan al agente cuando y como usar un grupo de tools. Son ficheros YAML.

Crear un fichero en `backend/agent/skills/definitions/`:

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
| `layer_management` | listActiveLayers, addWMSLayer, removeLayer | Gestionar capas del visor |

## Estructura del proyecto

```
apiidee-agent/
├── backend/                          # Servidor Django
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
│   │   │   ├── providers.py          # OpenAI, Gemini
│   │   │   └── config.py             # Factory
│   │   ├── rag/                      # Pipeline RAG
│   │   │   ├── indexer.py            # BaseIndexer + GitRepoIndexer + WebIndexer
│   │   │   ├── chunking.py           # Chunking por funciones/clases/headings
│   │   │   └── retriever.py          # Query FAISS
│   │   ├── tools/                    # Definiciones de tools
│   │   │   ├── registry.py           # Auto-descubre definitions/*.json
│   │   │   └── definitions/          # <-- ANADIR TOOLS AQUI
│   │   │       ├── getMapCenter.json
│   │   │       ├── addWMSLayer.json
│   │   │       └── ...
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
├── index.html                        # Pagina de prueba con visor API-IDEE
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

## Flujo de ejecucion

```
1. Usuario escribe mensaje en el chat
2. Plugin JS envia POST /api/conversations/{id}/chat/ con mensaje + estado del mapa
3. Servidor Django:
   a. Busca contexto relevante en FAISS (RAG)
   b. Construye system prompt = base + skills + contexto + estado del mapa
   c. Llama al LLM con tools disponibles
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
