import json
import os
import shlex
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from componentes.cerebro.brain import Brain


ROOT = Path(__file__).resolve().parent
UI_ROOT = ROOT / "interfaz_bios"
brain = Brain()


class BiosHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            path = "/interfaz_bios/index.html"
        self._serve_file(path)

    def do_POST(self):
        if self.path not in {"/api/chat", "/api/execute"}:
            self._send_json(404, {"error": "Ruta no encontrada"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            if self.path == "/api/chat":
                result = brain.ask_result(payload.get("message", ""))
                self._send_json(200, result)
            else:
                self._execute_code(payload)
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json(400, {"error": str(error)})
        except Exception as error:
            self._send_json(500, {"error": str(error)})

    def _execute_code(self, payload):
        language = str(payload.get("language", "")).lower()
        code = str(payload.get("code", ""))
        commands = {"python": (".py", "python3"), "bash": (".sh", "bash")}
        if language not in commands:
            raise ValueError("Solo se permite ejecutar codigo Python o Bash.")
        if not code.strip() or len(code) > 20000:
            raise ValueError("El codigo esta vacio o supera el limite permitido.")

        suffix, executable = commands[language]
        with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8") as file:
            file.write(code)
            script_path = file.name
        command = f"{executable} {shlex.quote(script_path)}; printf '\\nPulsa ENTER para cerrar...'; read"
        if os.name != "posix" or subprocess.run(["which", "osascript"], capture_output=True).returncode != 0:
            raise RuntimeError("La ejecucion en Terminal esta disponible en macOS.")
        subprocess.Popen(["osascript", "-e", f"tell application \"Terminal\" to do script {json.dumps(command)}"])
        self._send_json(200, {"status": "terminal_opened"})

    def _serve_file(self, path):
        relative_path = path.removeprefix("/interfaz_bios/")
        file_path = UI_ROOT / relative_path
        if not file_path.is_file() or UI_ROOT not in file_path.parents:
            self._send_json(404, {"error": "Recurso no encontrado"})
            return
        content_types = {".html": "text/html", ".css": "text/css", ".js": "text/javascript"}
        self.send_response(200)
        self.send_header("Content-Type", f"{content_types.get(file_path.suffix, 'text/plain')}; charset=utf-8")
        self.end_headers()
        self.wfile.write(file_path.read_bytes())

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[BIOS] {self.address_string()} - {format % args}")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8000), BiosHandler)
    print("BIOS console: http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido")
    finally:
        server.server_close()
