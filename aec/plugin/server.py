"""
Blender MCP Server — Non-blocking socket server with newline-delimited JSON framing.

Accepts commands from the MCP proxy and dispatches to registered handler functions.
Uses bpy.app.timers for main-thread polling (no background threads).
Blender 5.1 / Python 3.13
"""

import json
import socket
import traceback

import bpy


class BlenderMCPServer:
    """Socket server that accepts MCP commands and dispatches to registered handlers."""

    def __init__(self, host: str = "0.0.0.0", port: int = 9876):
        self.host = host
        self.port = port
        self.running = False
        self._socket: socket.socket | None = None
        self._client: socket.socket | None = None
        self._buffer = b""
        self._HANDLERS: dict = {}

    def start(self) -> bool:
        """Start listening for connections."""
        from .handlers import register_all_handlers
        register_all_handlers(self)

        self.running = True
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._socket.bind((self.host, self.port))
            self._socket.listen(1)
            self._socket.setblocking(False)
            bpy.app.timers.register(self._process, first_interval=0.1, persistent=True)
            print(f"[MCP] Server started on {self.host}:{self.port} "
                  f"({len(self._HANDLERS)} handlers registered)")
            return True
        except Exception as e:
            print(f"[MCP] Failed to start server: {e}")
            self.stop()
            return False

    def stop(self):
        """Stop the server and clean up."""
        self.running = False
        if bpy.app.timers.is_registered(self._process):
            bpy.app.timers.unregister(self._process)
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        self._buffer = b""
        print("[MCP] Server stopped")

    def _process(self) -> float | None:
        """Timer callback: accept connections and read commands. Returns interval."""
        if not self.running:
            return None
        try:
            # Accept new connections
            if not self._client and self._socket:
                try:
                    self._client, addr = self._socket.accept()
                    self._client.setblocking(False)
                    print(f"[MCP] Client connected: {addr}")
                except BlockingIOError:
                    pass
                except Exception as e:
                    print(f"[MCP] Accept error: {e}")

            # Read from client — newline-delimited JSON framing
            if self._client:
                try:
                    data = self._client.recv(65536)
                    if data:
                        self._buffer += data
                        while b"\n" in self._buffer:
                            line, self._buffer = self._buffer.split(b"\n", 1)
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                command = json.loads(line.decode("utf-8"))
                            except json.JSONDecodeError as e:
                                print(f"[MCP] Invalid JSON: {e}")
                                continue
                            response = self._execute(command)
                            self._client.sendall(
                                json.dumps(response).encode("utf-8") + b"\n"
                            )
                    else:
                        print("[MCP] Client disconnected")
                        self._client.close()
                        self._client = None
                        self._buffer = b""
                except BlockingIOError:
                    pass
                except Exception as e:
                    print(f"[MCP] Client error: {e}")
                    if self._client:
                        try:
                            self._client.close()
                        except Exception:
                            pass
                        self._client = None
                    self._buffer = b""
        except Exception as e:
            print(f"[MCP] Server error: {e}")

        return 0.1  # poll every 100ms

    def _execute(self, command: dict) -> dict:
        """Dispatch a command to the appropriate handler."""
        cmd_type = command.get("type", "")
        params = command.get("params", {})
        handler = self._HANDLERS.get(cmd_type)
        if not handler:
            return {"status": "error", "message": f"Unknown command: {cmd_type}"}
        try:
            return {"status": "success", "result": handler(**params)}
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[MCP] Error in {cmd_type}: {e}\n{tb}")
            return {"status": "error", "message": str(e), "traceback": tb}

    # ── Utility methods used by handlers ─────────────────────────

    @staticmethod
    def get_object_or_raise(name: str):
        """Look up a Blender object by name and raise if not found."""
        obj = bpy.data.objects.get(name)
        if not obj:
            raise RuntimeError(f"Object not found: {name}")
        return obj

    @staticmethod
    def get_collection_or_raise(name: str):
        """Look up a collection by name and raise if not found."""
        col = bpy.data.collections.get(name)
        if not col:
            raise RuntimeError(f"Collection not found: {name}")
        return col

    @staticmethod
    def get_material_or_raise(name: str):
        """Look up a material by name and raise if not found."""
        mat = bpy.data.materials.get(name)
        if not mat:
            raise RuntimeError(f"Material not found: {name}")
        return mat

    @staticmethod
    def object_to_dict(obj) -> dict:
        """Convert a Blender object to a summary dict."""
        d = {
            "name": obj.name,
            "type": obj.type,
            "location": [round(v, 4) for v in obj.location],
            "rotation": [round(v, 4) for v in obj.rotation_euler],
            "scale": [round(v, 4) for v in obj.scale],
            "visible": obj.visible_get(),
        }
        if obj.type == 'MESH' and obj.data:
            d["vertices"] = len(obj.data.vertices)
            d["edges"] = len(obj.data.edges)
            d["polygons"] = len(obj.data.polygons)
        return d

    @staticmethod
    def get_ifc_file():
        """Get the active IFC file from Bonsai, or raise if none."""
        try:
            import bonsai.tool as tool
            ifc_file = tool.Ifc.get()
            if not ifc_file:
                raise RuntimeError("No IFC project open. Use bim_create_project or bim_load_project first.")
            return ifc_file
        except ImportError:
            raise RuntimeError("Bonsai BIM extension is not available")

    @staticmethod
    def get_ifc_element(obj):
        """Get the IFC entity for a Blender object, or raise if not an IFC element."""
        try:
            import bonsai.tool as tool
            element = tool.Ifc.get_entity(obj)
            if not element:
                raise RuntimeError(f"Object '{obj.name}' is not an IFC element")
            return element
        except ImportError:
            raise RuntimeError("Bonsai BIM extension is not available")


# ── Module-level singleton and auto-start ────────────────────────

_server: BlenderMCPServer | None = None


def register():
    """Called when the addon is enabled."""
    def _auto_start():
        global _server
        if _server is None:
            _server = BlenderMCPServer(port=9876)
        if not _server.running:
            _server.start()
        return None  # one-shot timer
    bpy.app.timers.register(_auto_start, first_interval=3.0)


def unregister():
    """Called when the addon is disabled."""
    global _server
    if _server:
        _server.stop()
        _server = None
