from .registry import register_tool

# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------

register_tool(
    name="getMapCenter",
    description="Get the current center coordinates of the map. Returns latitude, longitude and SRS.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)

register_tool(
    name="getCurrentZoom",
    description="Get the current zoom level of the map.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)

register_tool(
    name="listActiveLayers",
    description="List all active layers currently displayed on the map. Returns id, name, type, and visibility for each layer.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)

register_tool(
    name="getMapExtent",
    description="Get the current geographic extent (bounding box) of the map view. Returns minX, minY, maxX, maxY and SRS.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)

# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------

register_tool(
    name="addWMSLayer",
    description="Add a WMS layer to the map. Requires URL of the WMS service and the layer name.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL of the WMS service"},
            "name": {"type": "string", "description": "Name of the WMS layer"},
            "legend": {"type": "string", "description": "Legend label for the layer"},
            "transparent": {
                "type": "boolean",
                "description": "Whether the layer is transparent",
                "default": True,
            },
        },
        "required": ["url", "name"],
    },
)

register_tool(
    name="zoomTo",
    description="Move the map center to specific coordinates, optionally setting the zoom level.",
    parameters={
        "type": "object",
        "properties": {
            "lat": {"type": "number", "description": "Latitude of the target location"},
            "lon": {"type": "number", "description": "Longitude of the target location"},
            "zoom": {"type": "integer", "description": "Optional zoom level to set"},
        },
        "required": ["lat", "lon"],
    },
)

register_tool(
    name="removeLayer",
    description="Remove a layer from the map by its name.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name of the layer to remove"},
        },
        "required": ["name"],
    },
)

register_tool(
    name="setZoom",
    description="Set the zoom level of the map.",
    parameters={
        "type": "object",
        "properties": {
            "level": {"type": "integer", "description": "Zoom level to set"},
        },
        "required": ["level"],
    },
)
