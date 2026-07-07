"""
Tool Executors — Server-side handlers for tools that run on the backend
instead of the frontend.

Tools defined here execute in Python when called by the LLM, similar to
MCP tools but without requiring an external MCP server.
"""
import json
import logging
from typing import Any, Callable, Dict, Optional
from urllib.request import Request, urlopen

from html.parser import HTMLParser

logger = logging.getLogger(__name__)

_executors: Dict[str, Callable] = {}


def register(name: str):
    """Decorator to register a server-side tool executor."""
    def wrapper(fn: Callable):
        _executors[name] = fn
        return fn
    return wrapper


def get_executor(name: str) -> Optional[Callable]:
    """Get the executor function for a tool name."""
    return _executors.get(name)


def has_executor(name: str) -> bool:
    """Check if a tool has a server-side executor."""
    return name in _executors


class _TextExtractor(HTMLParser):
    """Extrae texto plano de HTML, ignorando script/style/nav/footer/header.

    Usa un contador de profundidad en vez de un booleano para que los tags
    anidados (p.ej. ``<nav><footer>...</footer></nav>``) se manejen correctamente.
    """

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self._skip_depth = 0
        self._skip_tags = {'script', 'style', 'nav', 'footer', 'header'}

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip_depth += 1
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.text_parts.append('\n' + '#' * int(tag[1]) + ' ')
        if tag in ('p', 'div', 'li', 'br', 'tr', 'td', 'th', 'section'):
            self.text_parts.append('\n')

    def handle_endtag(self, tag):
        if tag in self._skip_tags and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            self.text_parts.append(data)


@register("fetchWebPage")
def fetch_web_page(url: str, **kwargs) -> str:
    """Fetch a web page and return its text content."""
    logger.info("Fetching web page: %s", url)
    req = Request(url, headers={'User-Agent': 'APIIDEEAgent/1.0'})
    with urlopen(req, timeout=15) as resp:
        if 'text/html' not in resp.headers.get('Content-Type', ''):
            return resp.read().decode('utf-8', errors='ignore')[:50000]
        html = resp.read().decode('utf-8', errors='ignore')

    parser = _TextExtractor()
    parser.feed(html)
    text = ''.join(parser.text_parts)

    lines = [l.strip() for l in text.split('\n')]
    text = '\n'.join(l for l in lines if l)
    return text[:50000]


@register("geocodePlace")
def geocode_place(q: str = "", id: str = "", type: str = "",
                  portal: str = "", **kwargs) -> str:
    """Search for a place using the Cartociudad geocoder and return its geometry."""
    from urllib.parse import urlencode
    import json as json_module

    logger.info("Geocoding place: q=%s, id=%s, type=%s, portal=%s", q, id, type, portal)

    if id and type:
        params = {"id": id, "type": type, "outputformat": "geoJson"}
        if q:
            params["q"] = q
        if portal:
            params["portal"] = portal
        find_q = q or id
    else:
        params = {"q": q, "outputformat": "geoJson"}
        find_q = q

    geojson_url = "https://www.cartociudad.es/geocoder/api/geocoder/find?" + urlencode(params)
    logger.info("Cartociudad find URL: %s", geojson_url)

    # When called with id+type, skip candidates and go straight to result
    if id and type:
        safe_name = json_module.dumps(q or id, ensure_ascii=False)
        return (
            f"GeoJSON URL for candidate {safe_name}:"
            f"\n{geojson_url}"
            f"\nCall addLayer(type='GEOJSON', url=\"{geojson_url}\", name={safe_name}, fit=true)"
        )

    # Free-text search: get candidates
    candidates_params = {
        "q": find_q,
        "limit": "33",
        "no_process": "expendeduria",
        "countrycode": "es",
        "autocancel": "true",
    }
    candidates_url = "https://www.cartociudad.es/geocoder/api/geocoder/candidates?" + urlencode(candidates_params)
    try:
        req = Request(candidates_url, headers={"User-Agent": "APIIDEEAgent/1.0"})
        with urlopen(req, timeout=15) as resp:
            candidates_raw = resp.read().decode("utf-8", errors="ignore")
        candidates_data = json_module.loads(candidates_raw)
        if isinstance(candidates_data, list) and candidates_data:
            lines = []
            for idx, c in enumerate(candidates_data[:10]):
                addr = c.get("address", q)
                ctype = c.get("type", "")
                muni = c.get("muni", "")
                cid = c.get("id", "")
                lat = c.get("lat", 0)
                lng = c.get("lng", 0)
                find_params = {"id": cid, "type": ctype, "outputformat": "geoJson"}
                if addr:
                    find_params["q"] = addr
                candidate_find_url = "https://www.cartociudad.es/geocoder/api/geocoder/find?" + urlencode(find_params)
                coords = f"lat={lat}, lon={lng}" if lat and lng and float(lat) != 0 and float(lng) != 0 else ""
                lines.append(
                    f"[{idx+1}] {addr} — {ctype} — {muni}"
                    + (f" ({coords})" if coords else "")
                    + f"\n    url={candidate_find_url}"
                )
            summary = (
                f"Candidates for {json_module.dumps(q, ensure_ascii=False)}:\n"
                + "\n".join(lines)
                + "\n\nShow candidates as a clean numbered list."
                + "\nEach candidate is a clickable DIV:"
                + '\n<div class="candidate-btn" onclick="window.chatagentQuickReply(\'ADD LAYER: candidate_find_url | ADDR (CTYPE)\')">NÚMERO. ADDR <span class="candidate-meta">CTYPE — MUNI</span></div>'
                + "\nReplace candidate_find_url, ADDR, CTYPE, MUNI, NÚMERO with actual values."
                + "\n\nAfter showing the list, ask: ¿Cuál quieres cargar en el mapa?"
                + "\nWhen user sends 'ADD LAYER: url | name', extract the url and name and call addLayer(type='GEOJSON', url=url, name=name, fit=true)."
                + "\nDo NOT call geocodePlace again."
            )
        else:
            summary = f"No candidates found for: {q}\nGeoJSON URL: {geojson_url}"
            summary += f"\nCall addLayer(type='GEOJSON', url=\"{geojson_url}\", name={json_module.dumps(q, ensure_ascii=False)}, fit=true)"
    except Exception as e:
        logger.warning("Candidates lookup failed: %s", e)
        summary = f"Search for: {q}\nGeoJSON URL: {geojson_url}"
        summary += f"\nCall addLayer(type='GEOJSON', url=\"{geojson_url}\", name={json_module.dumps(q, ensure_ascii=False)}, fit=true)"

    return summary


# ────────────────────────────── IDEE Service Directory ──────────────────────────────

_IDEE_PORTLET = "es_igncnig_dirserv72_DirectorioServiciosPortlet_INSTANCE_YZFuNrhnVi4f"
_IDEE_BASE = "https://www.idee.es/web/idee/segun-tipo-de-servicio"

# Category ID → addLayer type mapping
_IDEE_CATEGORIES = [
    ("sup-vis-rts", "TMS",     "XYZ de Teselas ráster"),
    ("sup-vis-vts", "MVT",     "Teselas vectoriales"),
    ("sup-vis-wmts","WMTS",    "WMTS"),
    ("sup-des-wfs", "WFS",     "WFS"),
    ("sup-ogc-api", "OGCAPIFeatures", "OGC API"),
    ("supVisWmsEst","WMS",     "WMS"),
]


def _idee_api_url(cat_id: str) -> str:
    params = (
        f"p_p_id={_IDEE_PORTLET}&p_p_lifecycle=2&p_p_state=normal&p_p_mode=view"
        f"&p_p_cacheability=cacheLevelPage"
        f"&_{_IDEE_PORTLET}_id={cat_id}"
        f"&_{_IDEE_PORTLET}_actionName=cargaTablaSrv"
    )
    return f"{_IDEE_BASE}?{params}"


@register("searchIdeeService")
def search_idee_service(query: str, **kwargs) -> str:
    """Search for a service by name in the IDEE service directory.

    Iterates through service categories, calls the IDEE JSON API,
    and returns matching services with their URL and correct addLayer type.
    """
    q = query.strip().lower()
    if not q:
        return json.dumps({"error": "Se necesita un término de búsqueda"}, ensure_ascii=False)

    results = []

    for cat_id, layer_type, cat_label in _IDEE_CATEGORIES:
        url = _idee_api_url(cat_id)
        try:
            req = Request(url, headers={"User-Agent": "APIIDEEAgent/1.0"})
            with urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(raw)
        except Exception as e:
            logger.warning("Error fetching category %s (%s): %s", cat_id, cat_label, e)
            continue

        servicios = data.get("datos", {})
        for org_level in ("est", "aut", "loc", "pve"):
            orgs = servicios.get(org_level, [])
            if not isinstance(orgs, list):
                continue
            for org in orgs:
                org_name = org.get("name", "")
                for org_item in org.get("listorg", []):
                    for srv in org_item.get("listserv", []):
                        srv_name = srv.get("name", "")
                        srv_url = srv.get("url", "")
                        if not srv_name or not srv_url:
                            continue
                        if q in srv_name.lower():
                            results.append({
                                "name": srv_name,
                                "url": srv_url,
                                "type": layer_type,
                                "category": cat_label,
                                "organization": org_name,
                            })

    if not results:
        return json.dumps(
            {"error": f"No se encontró ningún servicio con el nombre '{query}'. "
                       "Puedes buscar manualmente en https://www.idee.es/segun-tipo-de-servicio"},
            ensure_ascii=False,
        )

    # Deduplicate by URL
    seen = set()
    deduped = []
    for r in results:
        if r["url"] not in seen:
            seen.add(r["url"])
            deduped.append(r)

    summary_lines = [
        f"Se encontraron {len(deduped)} servicios para '{query}':",
        "",
    ]
    for r in deduped[:5]:
        summary_lines.append(f"• **{r['name']}** — `{r['type']}`")
        summary_lines.append(f"  URL: `{r['url']}`")
        summary_lines.append(f"  Organización: {r['organization']}")
        summary_lines.append("")

    if len(deduped) > 5:
        summary_lines.append(f"... y {len(deduped) - 5} resultados más.")

    summary_lines.append(
        "Selecciona el servicio correcto y llama a "
        "`addLayer(type='<TIPO>', url='<URL>', name='<NOMBRE>', fit=true)`."
    )

    return "\n".join(summary_lines)


# ────────────────────────────── Detección de objetos ML ──────────────────────────────

@register("listDetectors")
def list_detectors_tool(**kwargs) -> str:
    """Lista los detectores ML disponibles en el servidor."""
    from agent.ml.registry import list_detectors

    detectors = list_detectors()
    if not detectors:
        return json.dumps(
            {"message": "No hay detectores ML registrados en el servidor."},
            ensure_ascii=False,
        )

    lines = [f"Detectores disponibles ({len(detectors)}):"]
    for d in detectors:
        lines.append(f"• **{d['label']}** (`{d['name']}`): {d['description']}")

    return "\n".join(lines)


@register("detectObjects")
def detect_objects_tool(detector: str, bbox: dict, srs: str = "EPSG:3857",
                        wms_url: str = None, wms_layer: str = None,
                        **kwargs) -> str:
    """Ejecuta un detector ML sobre la zona indicada y devuelve GeoJSON."""
    from agent.ml.inference import run_detection

    return run_detection(
        detector_name=detector,
        bbox=bbox,
        srs=srs,
        wms_url=wms_url,
        wms_layer=wms_layer,
    )
