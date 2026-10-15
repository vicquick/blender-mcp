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


# ═══════════════════════════════════════════════════════════════════
# Wave 2 review fix: BlenderStateCacheMiddleware (defect #1) and the single
# source of truth it shares with the readOnlyHint annotation (defect #2).
#
# Appended to this file (rather than a separate test module) deliberately:
# these tests import `bms` too, and blender_mcp_server.py reads
# BLENDER_SOCKET_TIMEOUT into a module-level constant on its FIRST import
# anywhere in the test session (see the os.environ.setdefault at the top of
# this file) — a second test module importing it first, before that
# setdefault runs, would bake in a different value and break
# test_busy_main_thread_times_out_with_busy_code above. Living in the same
# file sidesteps that import-order trap entirely.
# ═══════════════════════════════════════════════════════════════════

import asyncio


class _FakeToolMessage:
    def __init__(self, name, arguments=None):
        self.name = name
        self.arguments = arguments


class _FakeToolContext:
    def __init__(self, name, arguments=None):
        self.message = _FakeToolMessage(name, arguments)


class _FakeToolResult:
    """Stands in for fastmcp's ToolResult: the middleware only ever reads
    `.is_error` off it and otherwise treats it as an opaque value."""

    def __init__(self, value, is_error=False):
        self.value = value
        self.is_error = is_error


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _counting_call_next(counter):
    async def call_next(context):
        counter[context.message.name] = counter.get(context.message.name, 0) + 1
        return _FakeToolResult((context.message.name, counter[context.message.name]))
    return call_next


def test_repeat_read_without_mutation_is_served_from_cache():
    mw = bms.BlenderStateCacheMiddleware(cacheable={"get_scene_info"}, ttl=30)
    counter = {}
    call_next = _counting_call_next(counter)
    ctx = _FakeToolContext("get_scene_info", {"limit": 20})
    r1 = _run(mw.on_call_tool(ctx, call_next))
    r2 = _run(mw.on_call_tool(ctx, call_next))
    assert r1.value == r2.value, "identical reads should share one cache entry"
    assert counter["get_scene_info"] == 1, "second read should NOT have reached Blender again"


def test_mutation_invalidates_the_cached_read():
    """The exact scenario proven live in the review against a fake Blender
    addon: a cached read must not be served again once an intervening
    mutating tool call has run, even with identical arguments and well
    inside the TTL. Before this fix, two identical get_scene_info() calls
    around a create_object() both returned call_number 1 — the second read
    never reached Blender at all."""
    mw = bms.BlenderStateCacheMiddleware(cacheable={"get_scene_info"}, ttl=30)
    counter = {}
    call_next = _counting_call_next(counter)
    read_ctx = _FakeToolContext("get_scene_info", {"limit": 20})
    write_ctx = _FakeToolContext("create_object", {"type": "cube"})

    r1 = _run(mw.on_call_tool(read_ctx, call_next))
    _run(mw.on_call_tool(write_ctx, call_next))  # mutation in between, same key untouched
    r2 = _run(mw.on_call_tool(read_ctx, call_next))

    assert r1.value != r2.value, "cache served pre-mutation state after a write"
    assert counter["get_scene_info"] == 2, "the post-mutation read should hit Blender again"


def test_run_tool_itself_also_invalidates_the_cache():
    """run_tool is not in the cacheable set (same as every tool this server
    cannot classify as a pure state read), so a mutation dispatched THROUGH
    run_tool must still bump the generation and invalidate prior reads —
    this is what keeps review defect #1's fix correct even though run_tool
    bypasses the cache's own lookup/store path for whatever it dispatches
    internally (review defect #4)."""
    mw = bms.BlenderStateCacheMiddleware(cacheable={"get_scene_info"}, ttl=30)
    counter = {}
    call_next = _counting_call_next(counter)
    read_ctx = _FakeToolContext("get_scene_info", {"limit": 20})
    run_tool_ctx = _FakeToolContext("run_tool", {"name": "create_object", "arguments": {"type": "cube"}})

    r1 = _run(mw.on_call_tool(read_ctx, call_next))
    _run(mw.on_call_tool(run_tool_ctx, call_next))
    r2 = _run(mw.on_call_tool(read_ctx, call_next))

    assert r1.value != r2.value


def test_different_arguments_use_different_cache_entries():
    mw = bms.BlenderStateCacheMiddleware(cacheable={"get_scene_info"}, ttl=30)
    counter = {}
    call_next = _counting_call_next(counter)
    r1 = _run(mw.on_call_tool(_FakeToolContext("get_scene_info", {"limit": 20}), call_next))
    r2 = _run(mw.on_call_tool(_FakeToolContext("get_scene_info", {"limit": 50}), call_next))
    assert r1.value != r2.value
    assert counter["get_scene_info"] == 2


def test_error_results_are_never_cached():
    mw = bms.BlenderStateCacheMiddleware(cacheable={"get_scene_info"}, ttl=30)

    async def erroring_call_next(context):
        return _FakeToolResult("boom", is_error=True)

    ctx = _FakeToolContext("get_scene_info", {"limit": 20})
    _run(mw.on_call_tool(ctx, erroring_call_next))

    async def fresh_call_next(context):
        return _FakeToolResult("fresh", is_error=False)

    r2 = _run(mw.on_call_tool(ctx, fresh_call_next))
    assert r2.value == "fresh", "an error result must not be served from the cache on retry"


def test_ttl_expiry_forces_a_fresh_read():
    mw = bms.BlenderStateCacheMiddleware(cacheable={"get_scene_info"}, ttl=30)
    counter = {}
    call_next = _counting_call_next(counter)
    ctx = _FakeToolContext("get_scene_info", {"limit": 20})
    _run(mw.on_call_tool(ctx, call_next))
    # Force the stored entry into the past rather than sleeping 30s in a test.
    key = ("get_scene_info", mw._args_key({"limit": 20}))
    _expires_at, generation, cached_result = mw._store[key]
    mw._store[key] = (0.0, generation, cached_result)
    _run(mw.on_call_tool(ctx, call_next))
    assert counter["get_scene_info"] == 2


def test_cacheable_allowlist_and_readonly_annotation_never_drift_apart():
    """Review defect #2: `_cacheable_tools()` and the readOnlyHint/
    idempotentHint annotation used to be two independently hand-maintained
    prefix lists that disagreed on 16 bim_get_*/bim_list_*/bim_query_elements
    tools — the annotation called them unsafe to retry while the cache
    middleware correctly served them from a TTL cache. Both are now built
    from the same _STATE_READ_PREFIXES/_STATE_READ_NAMES pair; this pins the
    invariant so an edit to one without the other fails loudly here instead
    of shipping a silent re-drift."""
    for name in bms._cacheable_tools():
        info = bms._TOOL_INDEX[name]
        assert info["annotations"]["readOnly"] is True, (
            f"{name} is cacheable but its own readOnlyHint says otherwise"
        )


def test_all_sixteen_bim_get_list_query_tools_are_readonly():
    expected = {
        "bim_get_project_info", "bim_get_spatial_tree", "bim_get_container_elements",
        "bim_get_psets", "bim_get_attributes", "bim_get_type_info",
        "bim_get_element_classifications", "bim_get_schedule_info",
        "bim_get_clash_results", "bim_get_georeferencing",
        "bim_list_materials", "bim_list_types", "bim_list_classifications",
        "bim_list_systems", "bim_list_bcf_topics", "bim_query_elements",
    }
    assert expected <= set(bms._TOOL_INDEX)
    for name in expected:
        assert bms._TOOL_INDEX[name]["annotations"]["readOnly"] is True, name


def test_ping_and_viewport_screenshot_stay_out_of_the_cache():
    """ping's entire job is telling a live connection from a dead one —
    caching that would serve a stale "still connected" answer after Blender
    drops off. get_viewport_screenshot has a real side effect (a new file
    written) on every call. Neither belongs in the cache regardless of
    matching a read-only prefix/name."""
    cacheable = bms._cacheable_tools()
    assert "ping" not in cacheable
    assert "get_viewport_screenshot" not in cacheable
