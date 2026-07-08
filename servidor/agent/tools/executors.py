"""
Ejecutores de Herramientas — Manejadores del lado del servidor para herramientas
que se ejecutan en el backend en lugar del frontend.

Las herramientas definidas aquí se ejecutan en Python cuando el LLM las llama,
similar a las herramientas MCP pero sin requerir un servidor MCP externo.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, Optional
from urllib.request import Request, urlopen
from urllib.parse import urlencode

from agent.utils.html_parser import TextExtractor

logger = logging.getLogger(__name__)

_executors: Dict[str, Callable] = {}


def register(name: str):
    """Decorador para registrar un ejecutor de herramienta del lado del servidor."""
    def wrapper(fn: Callable):
        _executors[name] = fn
        return fn
    return wrapper


def get_executor(name: str) -> Optional[Callable]:
    """Obtiene la función ejecutora para un nombre de herramienta."""
    return _executors.get(name)


def has_executor(name: str) -> bool:
    """Verifica si una herramienta tiene un ejecutor del lado del servidor."""
    return name in _executors


@register("fetchWebPage")
def fetch_web_page(url: str, **kwargs) -> str:
    """Fetch a web page and return its text content."""
    logger.info("Fetching web page: %s", url)
    req = Request(url, headers={'User-Agent': 'APIIDEEAgent/1.0'})
    with urlopen(req, timeout=15) as resp:
        if 'text/html' not in resp.headers.get('Content-Type', ''):
            return resp.read().decode('utf-8', errors='ignore')[:50000]
        html = resp.read().decode('utf-8', errors='ignore')

    parser = TextExtractor()
    parser.feed(html)
    text = ''.join(parser.text_parts)

    lines = [l.strip() for l in text.split('\n')]
    text = '\n'.join(l for l in lines if l)
    return text[:50000]


def _geo_find_url(params: dict) -> str:
    return "https://www.cartociudad.es/geocoder/api/geocoder/find?" + urlencode(params)


def _geo_candidates_url(q: str) -> str:
    params = {"q": q, "limit": "33", "no_process": "expendeduria",
              "countrycode": "es", "autocancel": "true"}
    return "https://www.cartociudad.es/geocoder/api/geocoder/candidates?" + urlencode(params)


def _format_candidate(idx: int, c: dict) -> dict:
    """Formatea un candidato del geocoder como dict estructurado."""
    addr = c.get("address", "")
    ctype = c.get("type", "")
    muni = c.get("muni", "")
    cid = c.get("id", "")
    lat = c.get("lat", 0)
    lng = c.get("lng", 0)
    find_params = {"id": cid, "type": ctype, "outputformat": "geoJson"}
    if addr:
        find_params["q"] = addr
    url = _geo_find_url(find_params)
    candidate = {
        "index": idx + 1,
        "address": addr,
        "type": ctype,
        "municipality": muni,
        "id": cid,
        "geojsonURL": url,
    }
    if lat and lng and float(lat) != 0 and float(lng) != 0:
        candidate["lat"] = float(lat)
        candidate["lon"] = float(lng)
    return candidate


def _fetch_candidates(url: str) -> list | None:
    try:
        req = Request(url, headers={"User-Agent": "APIIDEEAgent/1.0"})
        with urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw)
        if isinstance(data, list) and data:
            return data[:10]
        return None
    except Exception as exc:
        logger.warning("Candidates lookup failed: %s", exc)
        return None


@register("geocodePlace")
def geocode_place(q: str = "", id: str = "", type: str = "",
                  portal: str = "", **kwargs) -> dict:
    """Busca un lugar con el geocoder de Cartociudad y devuelve su geometría."""
    logger.info("Geocoding place: q=%s, id=%s, type=%s, portal=%s", q, id, type, portal)

    if id and type:
        params = {"id": id, "type": type, "outputformat": "geoJson"}
        if q:
            params["q"] = q
        if portal:
            params["portal"] = portal
        geojson_url = _geo_find_url(params)
        name = q or id
        # Return structured result with URL and name
        return {"geojsonURL": geojson_url, "name": name}

    geojson_url = _geo_find_url({"q": q, "outputformat": "geoJson"})
    candidates_url = _geo_candidates_url(q)
    candidates = _fetch_candidates(candidates_url)

    if candidates is not None:
        formatted = [_format_candidate(i, c) for i, c in enumerate(candidates)]
        return {
            "message": f"Se encontraron {len(formatted)} candidatos para «{q}».",
            "_layers": [{
                "type": "geocoding_candidates",
                "candidates": formatted,
                "query": q,
            }],
        }

    fallback_msg = f"No candidates found for: {q}"
    # Return fallback with GeoJSON URL
    return {"geojsonURL": geojson_url, "name": q, "message": fallback_msg}


# ────────────────────────────── Directorio de Servicios IDEE ──────────────────────────────

_IDEE_PORTLET = "es_igncnig_dirserv72_DirectorioServiciosPortlet_INSTANCE_YZFuNrhnVi4f"
_IDEE_BASE = "https://www.idee.es/web/idee/segun-tipo-de-servicio"

# ID de categoría → mapeo de tipo addLayer
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


def _fetch_idee_category(cat_id: str, layer_type: str, cat_label: str,
                         query_lower: str) -> list:
    """Descarga y filtra servicios de una categoría IDEE.

    Se ejecuta en un hilo del pool para paralelizar las peticiones HTTP.
    """
    url = _idee_api_url(cat_id)
    matches = []
    try:
        req = Request(url, headers={"User-Agent": "APIIDEEAgent/1.0"})
        with urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(raw)
    except Exception as e:
        logger.warning("Error fetching category %s (%s): %s", cat_id, cat_label, e)
        return matches

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
                    if query_lower in srv_name.lower():
                        matches.append({
                            "name": srv_name,
                            "url": srv_url,
                            "type": layer_type,
                            "category": cat_label,
                            "organization": org_name,
                        })
    return matches


@register("searchIdeeService")
def search_idee_service(query: str, **kwargs) -> str:
    """Search for a service by name in the IDEE service directory.

    Queries all service categories in parallel using a thread pool,
    and returns matching services with their URL and correct addLayer type.
    """
    q = query.strip().lower()
    if not q:
        return json.dumps({"error": "Se necesita un término de búsqueda"}, ensure_ascii=False)

    results = []

    with ThreadPoolExecutor(max_workers=len(_IDEE_CATEGORIES)) as pool:
        futures = {
            pool.submit(_fetch_idee_category, cat_id, layer_type, cat_label, q): cat_label
            for cat_id, layer_type, cat_label in _IDEE_CATEGORIES
        }
        for future in as_completed(futures):
            try:
                results.extend(future.result())
            except Exception as e:
                logger.warning("Error in IDEE category %s: %s", futures[future], e)

    if not results:
        return json.dumps(
            {"error": f"No se encontró ningún servicio con el nombre '{query}'. "
                       "Puedes buscar manualmente en https://www.idee.es/segun-tipo-de-servicio"},
            ensure_ascii=False,
        )

    # Desduplicar por URL
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
                        image_width: int = None, image_height: int = None,
                        **kwargs) -> str:
    """Ejecuta un detector ML sobre la zona indicada y devuelve GeoJSON.

    El resultado GeoJSON se propaga automáticamente como capa ``layer`` en la
    respuesta del asistente a través del mecanismo ``AgentResponse.layers``.

    Args:
        detector: Nombre del detector a usar (ver listDetectors).
        bbox: Extensión geográfica ``{minX, minY, maxX, maxY}``.
        srs: SRS del bbox (por defecto EPSG:3857).
        wms_url: URL del WMS (por defecto ortofoto PNOA).
        wms_layer: Capa del WMS.
        image_width: Ancho de imagen WMS en píxeles (por defecto 2048).
        image_height: Alto de imagen WMS en píxeles (por defecto 2048).
    """
    from agent.ml.inference import run_detection

    # Solo pasar image_width/image_height si el LLM los especificó explícitamente
    det_kwargs = dict(
        detector_name=detector,
        bbox=bbox,
        srs=srs,
        wms_url=wms_url,
        wms_layer=wms_layer,
    )
    if image_width is not None:
        det_kwargs["image_width"] = image_width
    if image_height is not None:
        det_kwargs["image_height"] = image_height

    result = run_detection(**det_kwargs)
    return result
