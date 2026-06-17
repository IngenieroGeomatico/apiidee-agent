# API-IDEE Agent — Architecture Plan

## Overview

Django-based AI agent with RAG over the API-IDEE codebase, exposed via REST API, consumed by a native JS plugin embedded in the API-IDEE map viewer. The agent can answer questions about API-IDEE and (in later phases) control the map via tool calling.

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Backend framework | Django 5.x + Django REST Framework | User requirement |
| Agent framework | LangChain | Multi-LLM, RAG, tool calling built-in |
| LLM support | OpenAI (MVP) → Anthropic, Ollama (Phase 3) | Flexible/configurable requirement |
| Vector store | FAISS local (MVP) → pgvector (production) | SQLite for MVP, no PostgreSQL dependency |
| DB | SQLite (MVP) → PostgreSQL (production) | Minimal infra for development |
| Frontend | API-IDEE native plugin (vanilla JS, Webpack) | Must integrate into existing viewer |
| Communication | REST (MVP) → SSE streaming (Phase 2) → WebSocket (Phase 3) | Incremental complexity |
| Auth | None (MVP) → Token-based (production) | User request |
| Deployment | Local development | User request |

## Project Structure

```
apiidee-agent/
├── backend/                          # Django project
│   ├── manage.py
│   ├── requirements.txt
│   ├── config/                       # Django project settings
│   │   ├── __init__.py
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── wsgi.py
│   │   └── asgi.py
│   ├── agent/                        # Core agent app
│   │   ├── __init__.py
│   │   ├── models.py                 # Conversation, Message models
│   │   ├── serializers.py            # DRF serializers
│   │   ├── views.py                  # Chat API endpoints
│   │   ├── urls.py
│   │   ├── llm/                      # LLM provider abstraction
│   │   │   ├── __init__.py
│   │   │   ├── providers.py          # OpenAI, Anthropic, Ollama
│   │   │   └── config.py             # Provider selection logic
│   │   ├── rag/                      # RAG pipeline
│   │   │   ├── __init__.py
│   │   │   ├── indexer.py            # Repo cloning + chunking + embedding
│   │   │   ├── retriever.py          # Query vector store
│   │   │   └── chunking.py           # Code-aware chunking strategies
│   │   ├── tools/                    # Agent tools (Phase 2+)
│   │   │   ├── __init__.py
│   │   │   ├── registry.py           # Tool registration
│   │   │   ├── map_tools.py          # Map interaction tools
│   │   │   └── schemas.py            # Tool input/output schemas
│   │   └── skills/                   # Agent skills (Phase 3+)
│   │       ├── __init__.py
│   │       └── base.py
│   └── vectorstore/                  # Vector store management app
│       ├── __init__.py
│       ├── models.py                 # Repository, IndexingJob models
│       ├── store.py                  # FAISS wrapper (MVP) / pgvector (prod)
│       ├── management/
│       │   └── commands/
│       │       └── index_repo.py     # `python manage.py index_repo <url>`
│       └── embeddings/               # Stored FAISS indexes
│           └── .gitkeep
├── plugin/                           # API-IDEE plugin (JS)
│   ├── src/
│   │   ├── facade/
│   │   │   └── js/
│   │   │       └── chatagent.js      # Plugin facade (public API)
│   │   ├── impl/
│   │   │   ├── ol/
│   │   │   │   ├── js/
│   │   │   │   │   └── chatagentcontrol.js  # OL implementation
│   │   │   │   └── css/
│   │   │   │       └── chatagent.css
│   │   │   └── cesium/
│   │   │       └── js/
│   │   │           └── chatagentcontrol.js  # Cesium implementation
│   │   ├── templates/
│   │   │   └── chatagent.html        # Handlebars chat UI template
│   │   ├── api.json                  # Plugin REST API definition
│   │   └── index.js                  # Entry point
│   ├── task/
│   ├── test/
│   ├── webpack-config/
│   ├── package.json
│   └── README.md
└── docs/                             # Project documentation
    └── api.md
```

## Phase 1 — MVP: Chat Q&A with RAG (Target: this session)

### Goal
End-to-end chat: User asks about API-IDEE in the plugin → Django backend answers using RAG over API-IDEE docs/code.

### Backend Components

#### 1. Django Project Setup (`config/`)
- Django 5.x with DRF
- SQLite database
- CORS headers configured for local dev (django-cors-headers)
- Settings: LLM API key via environment variable (`OPENAI_API_KEY`)

#### 2. Agent App (`agent/`)

**Models** (`agent/models.py`):
```python
class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user"
        ASSISTANT = "assistant"
        SYSTEM = "system"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)  # RAG sources, tool calls, etc.
```

**API Endpoints** (`agent/views.py`):
- `POST /api/conversations/` → Create new conversation, returns `{id}`
- `POST /api/conversations/{id}/messages/` → Send message, returns assistant response
  - Request: `{"content": "How do I add a WMS layer?"}`
  - Response: `{"role": "assistant", "content": "...", "metadata": {"sources": [...]}}`
- `GET /api/conversations/{id}/messages/` → List conversation history

**LLM Provider** (`agent/llm/providers.py`):
- Abstract base: `BaseLLMProvider` with `chat(messages, tools=None)` method
- MVP: `OpenAIProvider` using LangChain's `ChatOpenAI`
- Config via `LLM_PROVIDER` and `LLM_MODEL` in settings

**RAG Pipeline** (`agent/rag/`):
- `indexer.py`: Clone repo → walk files → chunk → embed → store in FAISS
  - Chunking strategy: Code files by function/class boundaries (tree-sitter or AST)
  - Doc files (.md, .wiki): By heading sections
  - Skip: binary files, node_modules, dist, .git
- `retriever.py`: Query FAISS → return top-k chunks with metadata (file, line numbers)
- System prompt includes retrieved context + instruction to cite sources

#### 3. Vector Store App (`vectorstore/`)

**Models** (`vectorstore/models.py`):
```python
class Repository(models.Model):
    url = models.URLField(unique=True)
    name = models.CharField(max_length=255)
    last_indexed = models.DateTimeField(null=True)
    status = models.CharField(max_length=20)  # pending, indexing, ready, error

class IndexingJob(models.Model):
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)
    chunks_created = models.IntegerField(default=0)
    status = models.CharField(max_length=20)
    error_message = models.TextField(blank=True)
```

**Management Command**: `python manage.py index_repo https://github.com/Desarrollos-IDEE/API-IDEE`

### Frontend Plugin Components

#### 1. Plugin Scaffold
- Use API-IDEE facade pattern: `facade/js/chatagent.js` + `impl/ol/js/chatagentcontrol.js`
- Plugin name: `ChatAgent`
- Registration: `IDEE.plugin.ChatAgent`

#### 2. Chat UI
- Collapsible panel on the right side of the map
- Message list (scrollable)
- Text input + send button
- Loading indicator while waiting for response
- Source citations displayed as expandable sections

#### 3. Communication
- REST calls to Django backend via `fetch()`
- Conversation ID stored in plugin state
- Error handling: network errors, API errors displayed in chat

### Configuration

**Environment Variables** (backend):
```
OPENAI_API_KEY=sk-...
LLM_PROVIDER=openai        # openai | anthropic | ollama
LLM_MODEL=gpt-4o-mini      # Model name
ALLOWED_ORIGINS=http://localhost:8080  # CORS
```

**Plugin Config** (frontend):
```javascript
new IDEE.plugin.ChatAgent({
    position: 'TR',              // Top-right
    collapsed: true,             // Start collapsed
    backendUrl: 'http://localhost:8000/api',
    tooltip: 'Asistente API-IDEE'
});
```

### Requirements (Python)

```
django>=5.0,<6.0
djangorestframework>=3.15
django-cors-headers>=4.0
langchain>=0.3
langchain-openai>=0.2
langchain-community>=0.3
faiss-cpu>=1.8
tiktoken>=0.7
gitpython>=3.1
python-dotenv>=1.0
```

### Requirements (JS Plugin)

```json
{
  "devDependencies": {
    "webpack": "^5.88",
    "webpack-cli": "^5.1",
    "css-loader": "^6.8",
    "style-loader": "^3.3",
    "handlebars-loader": "^1.7"
  }
}
```

### QA Criteria — Phase 1 Done When

1. `python manage.py index_repo https://github.com/Desarrollos-IDEE/API-IDEE` completes successfully
2. `curl -X POST http://localhost:8000/api/conversations/ | jq .id` returns UUID
3. `curl -X POST http://localhost:8000/api/conversations/{id}/messages/ -d '{"content":"What is API-IDEE?"}'` returns coherent answer citing API-IDEE docs
4. Plugin loads in API-IDEE viewer without breaking the map
5. Chat UI sends message → receives response → displays it
6. RAG sources are included in response metadata

---

## Phase 2 — Tool Execution (read-only) — Future

### New Tools
- `getMapCenter()` → `{lat, lon, srs}`
- `getCurrentZoom()` → `{level}`
- `listActiveLayers()` → `[{id, name, type, visible}]`
- `getMapExtent()` → `{minX, minY, maxX, maxY, srs}`

### Architecture
- Tool registry in backend defines schemas (JSON Schema)
- Agent uses LangChain tool calling
- Backend sends tool call to frontend via response: `{"type": "tool_call", "tool": "getMapCenter", "args": {}}`
- Frontend executes on `IDEE.Map`, returns result via `POST /api/conversations/{id}/tool-result/`
- Agent receives result, continues reasoning

### Protocol
```
User message → Backend (LLM) → tool_call response
                                    ↓
Frontend executes tool on IDEE.Map → tool_result POST
                                    ↓
Backend (LLM with result) → final response
```

### State Sync (Critical)
- Frontend reports map state on every message (center, zoom, layers)
- Backend includes state in system prompt context
- Agent never assumes state — always queries or uses reported state

---

## Phase 3 — Full Agent — Future

### New Capabilities
- Write tools: `addLayer()`, `zoomTo()`, `drawGeometry()`, `removeLayer()`
- Multi-LLM: Anthropic, Ollama providers
- SSE streaming for responses
- Tool call validation & sandboxing
- Auth (token-based)
- Full code RAG with semantic chunking
- Rate limiting
- Audit logging

---

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| Agent-Map state desync | Frontend reports state with every message; agent never assumes |
| RAG hallucination | Cite sources (file + line); chunk at semantic boundaries; prioritize docs over code |
| Multi-LLM tool incompatibility | Test per-model; fallback to text-only for unsupported models |
| Streaming + tools conflict | MVP: no streaming; Phase 2: pause stream on tool call |
| Prompt injection | System prompt hardening; never expose API keys in context |
| CORS issues | django-cors-headers; explicit allowed origins |
| Plugin lifecycle conflicts | Proper activate/deactivate/destroy; test with other plugins |
| Scope creep on tools | Start with 3 read-only tools; tool template for consistency |

## Security Notes (MVP)

- All LLM calls go through backend (never expose API keys to frontend)
- No `eval()` of agent output on frontend
- CORS restricted to allowed origins
- Input sanitization on chat messages
- No auth in MVP, but designed so auth middleware can be added later
