"""Review defect #3 (fastmcp4-ausbau wave 2): BLENDER_SOCKET_TIMEOUT used to
default to a fixed 180s, shorter than BLENDER_CALL_TIMEOUT's own 300s
default — a real call legitimately running past 180s hit socket.timeout and
reported BLENDER_BUSY ("retry the call") while Blender kept working on it
regardless, and the per-tool call timeout / heartbeat middleware never got a
chance to matter because the inner socket timeout always won first.

This test runs in a FRESH subprocess with a controlled environment rather
than importing blender_mcp_server in-process: that module reads both
timeouts into module-level constants on its very first import anywhere in
the test session, and test_connection.py's own
`os.environ.setdefault("BLENDER_SOCKET_TIMEOUT", "0.5")` (needed for ITS
busy-timeout test to run fast) would otherwise poison this test's view of
the real default — or, if this file's import happened to run first, poison
test_connection.py's. A subprocess sidesteps that shared-module-cache trap
entirely: no environment or import order in the parent pytest process can
affect it.
"""
import json
import os
import subprocess
import sys

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

_PROBE = (
    "import sys; sys.path.insert(0, {server_dir!r}); "
    "import blender_mcp_server as bms; "
    "import json; "
    "print(json.dumps({{'socket': bms.BLENDER_SOCKET_TIMEOUT, "
    "'call': bms.BLENDER_CALL_TIMEOUT}}))"
)


def _probe(env_overrides):
    env = {"PATH": os.environ.get("PATH", "")}
    env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, "-c", _PROBE.format(server_dir=SERVER_DIR)],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"probe subprocess failed: {result.stderr}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_default_socket_timeout_is_above_default_call_timeout():
    values = _probe({})
    assert values["socket"] > values["call"], values


def test_socket_timeout_default_tracks_a_raised_call_timeout():
    """The margin must hold even when an operator raises BLENDER_CALL_TIMEOUT
    via env without also touching BLENDER_SOCKET_TIMEOUT — the exact
    misconfiguration the review's defect describes (two independently-set
    envs that can silently invert)."""
    values = _probe({"BLENDER_CALL_TIMEOUT": "900"})
    assert values["call"] == 900.0
    assert values["socket"] > values["call"], values


def test_explicit_socket_timeout_override_still_wins():
    """An operator who deliberately sets BLENDER_SOCKET_TIMEOUT must still be
    able to — this is a safer default, not a hardcoded floor."""
    values = _probe({"BLENDER_SOCKET_TIMEOUT": "12"})
    assert values["socket"] == 12.0


def test_socket_timeout_margin_is_configurable():
    values = _probe({"BLENDER_SOCKET_TIMEOUT_MARGIN": "5"})
    assert values["socket"] == values["call"] + 5.0
