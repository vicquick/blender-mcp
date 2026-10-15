"""Wave 2: BlenderConnection hardening, proven against a fake TCP stand-in
for the Blender addon's socket protocol — no real Blender needed.

FakeAddon mirrors exactly what aec/plugin/server.py's _execute() actually
does (ground-truthed by reading that file, not assumed): read
newline-delimited JSON, dispatch on `command.get("type")` /
`command.get("params", {})`, reply `{"status": "success", "result": ...}`.
Any other top-level key (like this wave's `_cid`) is never looked at, which
is exactly why adding it needed no addon-side change.
"""
import json
import os

# Must be set before blender_mcp_server is first imported: BLENDER_SOCKET_TIMEOUT
# is read into a module-level constant at import time, and the timeout test
# below needs it short rather than the real 180s default.
os.environ.setdefault("BLENDER_SOCKET_TIMEOUT", "0.5")

import socket
import threading
import time

import pytest

import blender_mcp_server as bms
from blender_mcp_server import BlenderConnection


class FakeAddon:
    """Single-slot fake server: one client at a time, re-accepts after a
    disconnect — same shape as the real addon's `_client` handling in
    `BlenderMCPServer._process()`."""

    def __init__(self, close_after=None, never_reply=False):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.host, self.port = self.sock.getsockname()
        self.close_after = close_after  # close the client conn after N replies
        # Never send a reply to any command — simulates the Blender main
        # thread wedged in a long render (recv() on the client side just
        # blocks until BLENDER_SOCKET_TIMEOUT fires).
        self.never_reply = never_reply
        self.received = []
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while self._running:
            try:
                self.sock.settimeout(1.0)
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self._handle(conn)

    def _handle(self, conn):
        buf = b""
        n = 0
        try:
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    return
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    command = json.loads(line.decode("utf-8"))
                    self.received.append(command)
                    if self.never_reply:
                        time.sleep(5)  # longer than the test's short socket timeout
                        continue
                    n += 1
                    reply = {"status": "success", "result": {"echo": command.get("params", {})}}
                    conn.sendall(json.dumps(reply).encode("utf-8") + b"\n")
                    if self.close_after and n >= self.close_after:
                        conn.close()
                        return
        except Exception:
            pass
        finally:
            try: conn.close()
            except Exception: pass

    def stop(self):
        self._running = False
        try: self.sock.close()
        except Exception: pass


@pytest.fixture
def fresh_connection_state():
    """blender_mcp_server._connection is a module-level global the real
    server reuses across tool calls — reset it between tests so one test's
    socket isn't handed to the next."""
    bms._connection = None
    yield
    if bms._connection is not None:
        bms._connection.disconnect()
    bms._connection = None


def test_round_trip_echoes_params(fresh_connection_state):
    addon = FakeAddon()
    try:
        conn = BlenderConnection(host=addon.host, port=addon.port)
        result = conn.send_command("get_scene_info", {"limit": 5})
        assert result == {"status": "success", "result": {"echo": {"limit": 5}}}
    finally:
        addon.stop()


def test_cid_is_sent_but_addon_ignores_unknown_keys(fresh_connection_state):
    """Proves the correlation-id change is addon-compatible with zero addon
    edits: the real _execute() only reads type/params, so _cid passing
    through on the wire changes nothing it can see."""
    addon = FakeAddon()
    try:
        conn = BlenderConnection(host=addon.host, port=addon.port)
        conn.send_command("ping", {})
        assert len(addon.received) == 1
        sent = addon.received[0]
        assert sent["type"] == "ping"
        assert "_cid" in sent and len(sent["_cid"]) == 8
        assert conn.last_cid == sent["_cid"]
    finally:
        addon.stop()


def test_concurrent_calls_do_not_corrupt_the_shared_stream(fresh_connection_state):
    """The lock is what prevents two threads from interleaving their sendall
    and recv on one socket — without it this test is flaky-to-broken."""
    addon = FakeAddon()
    try:
        conn = BlenderConnection(host=addon.host, port=addon.port)
        conn.connect()
        results = {}
        errors = []

        def call(i):
            try:
                r = conn.send_command("set_frame", {"marker": i})
                results[i] = r["result"]["echo"]["marker"]
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=call, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=5)

        assert not errors, f"unexpected errors: {errors}"
        assert results == {i: i for i in range(20)}, "a marker came back mismatched — stream corrupted"
    finally:
        addon.stop()


def test_dead_peer_is_detected_and_reconnected_transparently(fresh_connection_state):
    """FakeAddon closes the connection after its first reply (simulating the
    Blender addon restarting). The OLD code's sendall(b'') liveness probe
    never fails on a dead socket; this one's select()-based probe in
    send_command must notice and reconnect before the second call, not
    return a stale-socket error."""
    addon = FakeAddon(close_after=1)
    try:
        conn = BlenderConnection(host=addon.host, port=addon.port)
        first = conn.send_command("ping", {})
        assert first["status"] == "success"
        # Give the fake server's accept-loop a moment to be ready to re-accept.
        time.sleep(0.2)
        second = conn.send_command("ping", {})
        assert second["status"] == "success", f"expected transparent reconnect, got {second}"
    finally:
        addon.stop()


def test_busy_main_thread_times_out_with_busy_code(fresh_connection_state):
    """never_reply=True means the addon never replies to any command —
    simulates the Blender main thread wedged in a long render. Must hit
    socket.timeout (BLENDER_SOCKET_TIMEOUT, set to 0.5s for this test at
    import time) and return the documented BLENDER_BUSY error shape rather
    than hanging the test suite."""
    addon = FakeAddon(never_reply=True)
    try:
        conn = BlenderConnection(host=addon.host, port=addon.port)
        t0 = time.time()
        result = conn.send_command("render_image", {"filepath": "/tmp/x.png"})
        elapsed = time.time() - t0
        assert result.get("code") == "BLENDER_BUSY"
        assert "cid" in result
        assert elapsed < 3.0, "did not time out anywhere near BLENDER_SOCKET_TIMEOUT"
    finally:
        addon.stop()


def test_get_connection_reuses_live_socket_without_a_probe_write(fresh_connection_state):
    """get_connection() must NOT use the old sendall(b'') probe (it never
    fails, so the old code would have served a dead connection for a full
    request before send_command's own checks ran). Confirm it just checks
    `.socket is not None` and otherwise defers entirely to send_command —
    by pre-seeding bms._connection with an already-connected object (rather
    than patching BLENDER_HOST/BLENDER_PORT, which are bound as
    BlenderConnection.__init__'s default argument values at class-definition
    time and so are immune to patching the module attribute afterwards)."""
    addon = FakeAddon()
    try:
        bms._connection = BlenderConnection(host=addon.host, port=addon.port)
        assert bms._connection.connect()
        conn1 = bms.get_connection()
        conn2 = bms.get_connection()
        assert conn1 is conn2 is bms._connection, "a live connection should be reused, not recreated"
    finally:
        addon.stop()
