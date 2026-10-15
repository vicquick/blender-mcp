"""Unit tests for blender_paths.py (wave 1's server-side path jail).

No Blender, no network, no fastmcp import needed — this module is pure
posixpath string math, so these run anywhere.
"""
import json

import pytest

from blender_paths import PathJailError, jail_or_error, jail_path


def test_default_roots_allow_root_and_tmp(monkeypatch):
    monkeypatch.delenv("BLENDER_ALLOWED_ROOTS", raising=False)
    assert jail_path("/root/demo-ifc/model.ifc") == "/root/demo-ifc/model.ifc"
    assert jail_path("/tmp/viewport.png") == "/tmp/viewport.png"


def test_root_itself_is_allowed(monkeypatch):
    monkeypatch.delenv("BLENDER_ALLOWED_ROOTS", raising=False)
    # Exact match on the root (no trailing content) must not be rejected by
    # an off-by-one in the "startswith(root + '/')" check.
    assert jail_path("/root") == "/root"


def test_rejects_relative_path(monkeypatch):
    monkeypatch.delenv("BLENDER_ALLOWED_ROOTS", raising=False)
    with pytest.raises(PathJailError, match="absolute"):
        jail_path("relative/model.ifc")


def test_rejects_path_outside_allowed_roots(monkeypatch):
    monkeypatch.delenv("BLENDER_ALLOWED_ROOTS", raising=False)
    with pytest.raises(PathJailError, match="outside"):
        jail_path("/etc/passwd")


def test_rejects_dunder_walk_escape_even_though_substring_matches(monkeypatch):
    """The exact bypass qgis-mcp's own plan flagged: a string-prefix check on
    the RAW path would pass this (it starts with "/root"), but the path
    actually resolves outside every allowed root once '..' is collapsed."""
    monkeypatch.delenv("BLENDER_ALLOWED_ROOTS", raising=False)
    with pytest.raises(PathJailError, match="outside"):
        jail_path("/root/../etc/passwd")


def test_internal_dunder_that_stays_inside_root_is_allowed(monkeypatch):
    monkeypatch.delenv("BLENDER_ALLOWED_ROOTS", raising=False)
    assert jail_path("/root/sub/../other/model.ifc") == "/root/other/model.ifc"


def test_similarly_named_sibling_is_not_allowed_by_prefix_alone(monkeypatch):
    """"/rootkit/x" must not pass just because it starts with the string
    "/root" — the check is against a full path segment, not a raw prefix."""
    monkeypatch.delenv("BLENDER_ALLOWED_ROOTS", raising=False)
    with pytest.raises(PathJailError, match="outside"):
        jail_path("/rootkit/evil.py")


def test_rejects_non_string_and_empty(monkeypatch):
    monkeypatch.delenv("BLENDER_ALLOWED_ROOTS", raising=False)
    with pytest.raises(PathJailError):
        jail_path("")
    with pytest.raises(PathJailError):
        jail_path(None)


def test_env_override_widens_allowed_roots(monkeypatch):
    monkeypatch.setenv("BLENDER_ALLOWED_ROOTS", "/data/aec:/root:/tmp")
    assert jail_path("/data/aec/project.ifc") == "/data/aec/project.ifc"


def test_env_override_narrows_allowed_roots(monkeypatch):
    monkeypatch.setenv("BLENDER_ALLOWED_ROOTS", "/data/aec")
    with pytest.raises(PathJailError, match="outside"):
        jail_path("/tmp/viewport.png")  # default root no longer configured


def test_param_name_appears_in_error_message(monkeypatch):
    monkeypatch.delenv("BLENDER_ALLOWED_ROOTS", raising=False)
    with pytest.raises(PathJailError, match="ids_filepath"):
        jail_path("/etc/passwd", "ids_filepath")


def test_jail_or_error_success_shape(monkeypatch):
    monkeypatch.delenv("BLENDER_ALLOWED_ROOTS", raising=False)
    path, err = jail_or_error("/root/model.ifc")
    assert path == "/root/model.ifc"
    assert err is None


def test_jail_or_error_failure_shape_is_json_with_error_key(monkeypatch):
    monkeypatch.delenv("BLENDER_ALLOWED_ROOTS", raising=False)
    path, err = jail_or_error("/etc/passwd")
    assert path is None
    parsed = json.loads(err)
    assert "error" in parsed and "etc/passwd" in parsed["error"]
