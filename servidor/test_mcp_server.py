#!/usr/bin/env python3
"""Mini MCP server de prueba con 3 tools de ejemplo."""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler

TOOLS = [
    {
        "name": "saludar",
        "description": "Saluda a una persona por su nombre",
        "inputSchema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre de la persona"}
            },
            "required": ["nombre"],
        },
    },
    {
        "name": "calcular",
        "description": "Realiza una operacion aritmetica simple",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "Primer numero"},
                "b": {"type": "number", "description": "Segundo numero"},
                "operacion": {
                    "type": "string",
                    "enum": ["sumar", "restar", "multiplicar", "dividir"],
                    "description": "Operacion a realizar",
                },
            },
            "required": ["a", "b", "operacion"],
        },
    },
    {
        "name": "capital_provincia",
        "description": "Devuelve la capital de una provincia espanola",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provincia": {"type": "string", "description": "Nombre de la provincia"}
            },
            "required": ["provincia"],
        },
    },
]

CAPITALES = {
    "madrid": "Madrid",
    "barcelona": "Barcelona",
    "valencia": "Valencia",
    "sevilla": "Sevilla",
    "malaga": "Malaga",
    "bilbao": "Bilbao",
    "zaragoza": "Zaragoza",
    "murcia": "Murcia",
    "palma": "Palma de Mallorca",
    "las palmas": "Las Palmas de Gran Canaria",
    "alicante": "Alicante",
    "cordoba": "Cordoba",
    "valladolid": "Valladolid",
    "toledo": "Toledo",
}


class MCPHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        req_id = body.get("id", 1)
        method = body.get("method", "")
        params = body.get("params", {})

        try:
            if method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = self._exec_tool(params["name"], params.get("arguments", {}))
            else:
                result = {}
        except Exception as e:
            self._send_error(req_id, str(e))
            return

        self._send_ok(req_id, result)

    def _exec_tool(self, name, args):
        if name == "saludar":
            return {"content": [{"type": "text", "text": f"Hola, {args['nombre']}! Soy un servidor MCP de prueba."}]}

        if name == "calcular":
            a, b = float(args["a"]), float(args["b"])
            ops = {
                "sumar": a + b,
                "restar": a - b,
                "multiplicar": a * b,
                "dividir": a / b if b != 0 else "Error: division por cero",
            }
            r = ops[args["operacion"]]
            return {"content": [{"type": "text", "text": f"Resultado: {r}"}]}

        if name == "capital_provincia":
            p = args["provincia"].lower()
            capital = CAPITALES.get(p, f"Capital de {args['provincia']} no encontrada en la base de datos")
            return {"content": [{"type": "text", "text": f"La capital de {args['provincia']} es {capital}."}]}

        raise ValueError(f"Tool desconocida: {name}")

    def _send_ok(self, req_id, result):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}).encode())

    def _send_error(self, req_id, msg):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32000, "message": msg},
        }).encode())

    def log_message(self, format, *args):
        print(f"[MCP] {args[0]} {args[1]} {args[2]}")


if __name__ == "__main__":
    port = 8001
    server = HTTPServer(("", port), MCPHandler)
    print(f"🚀 Servidor MCP de prueba escuchando en http://localhost:{port}")
    print(f"   Tools disponibles: {[t['name'] for t in TOOLS]}")
    server.serve_forever()
