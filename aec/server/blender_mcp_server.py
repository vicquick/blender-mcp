#!/usr/bin/env python3
"""
Blender MCP Server — socket proxy to Blender plugin (147 tools)
Connects to the Blender MCP plugin running inside the desktop container.
"""

import os
import logging
from contextlib import asynccontextmanager
import socket
import json
from typing import AsyncIterator, Dict, Any, Optional
# Migrated bundled mcp.server.fastmcp -> standalone fastmcp 4.x: the bundled
# build has no tags, no per-tool timeout and no middleware, so toolset
# presets, call timeouts, response caching and the progress heartbeat were
# all unreachable. See qgis-mcp's own migration (same repo family) for the
# reference shape this follows.
from fastmcp import FastMCP, Context
from mcp.types import ToolAnnotations

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BlenderMCPServer")

BLENDER_HOST = os.environ.get("DESKTOP_HOST", "aec-web")
BLENDER_PORT = int(os.environ.get("BLENDER_PORT", "9876"))

# Per-call timeout applied to every tool (qtool's default, overridable per
# tool). A render_animation over many frames is the long pole here; this
# just needs to clear whatever a client's own idle-abort window is, which
# ProgressHeartbeatMiddleware (wave 2) covers for anything slower still.
BLENDER_CALL_TIMEOUT = float(os.environ.get("BLENDER_CALL_TIMEOUT", "300"))

# MCP_TRACE_DIR-gated session trace (folded in from the April hot-patch at
# /opt/aec-web/data/mcp-patches/blender/blender_mcp_server.py — 6 days proven
# in prod, zero cost when the env var is unset). Writing it into the repo
# retires that hot-patch file; the triage cron that depended on it is already
# gone.
_TRACE_DIR = os.environ.get("MCP_TRACE_DIR")
if _TRACE_DIR:
    os.makedirs(_TRACE_DIR, exist_ok=True)


class BlenderConnection:
    def __init__(self, host=BLENDER_HOST, port=BLENDER_PORT):
        self.host = host
        self.port = port
        self.socket = None

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            return True
        except Exception as e:
            logger.error(f"Error connecting to Blender: {e}")
            return False

    def disconnect(self):
        if self.socket:
            self.socket.close()
            self.socket = None

    def send_command(self, command_type, params=None):
        """Send a newline-delimited JSON command and read the newline-delimited response."""
        if not self.socket:
            return None
        command = {"type": command_type, "params": params or {}}
        try:
            self.socket.sendall(json.dumps(command).encode('utf-8') + b'\n')
            response_data = b''
            while True:
                chunk = self.socket.recv(65536)
                if not chunk:
                    break
                response_data += chunk
                if b'\n' in response_data:
                    line = response_data.split(b'\n', 1)[0]
                    return json.loads(line.decode('utf-8'))
            if response_data.strip():
                return json.loads(response_data.strip().decode('utf-8'))
            return None
        except Exception as e:
            logger.error(f"Error sending command: {e}")
            return None


_connection = None

def get_connection():
    global _connection
    if _connection is not None:
        try:
            _connection.socket.sendall(b'')
            return _connection
        except Exception:
            try: _connection.disconnect()
            except Exception: pass
            _connection = None
    _connection = BlenderConnection()
    if not _connection.connect():
        _connection = None
        raise Exception(f"Could not connect to Blender at {BLENDER_HOST}:{BLENDER_PORT}. Start the plugin first.")
    logger.info(f"Connected to Blender at {BLENDER_HOST}:{BLENDER_PORT}")
    return _connection


def _log_trace(command_type, params, response):
    if not _TRACE_DIR:
        return
    try:
        from datetime import datetime, timezone
        entry = {"ts": datetime.now(timezone.utc).isoformat(), "mcp": "blender",
                 "tool": command_type, "args": params, "response": response}
        fn = f"{_TRACE_DIR}/trace-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
        with open(fn, "a") as f:
            f.write(json.dumps(entry, default=str)[:8192] + "\n")
    except Exception:
        pass


def cmd(command_type, params=None):
    """Send command and return JSON string."""
    response = get_connection().send_command(command_type, params)
    _log_trace(command_type, params, response)
    return json.dumps(response, indent=2)


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    logger.info("Blender MCP server starting")
    try:
        get_connection()
        logger.info("Connected to Blender on startup")
    except Exception as e:
        logger.warning(f"Could not connect on startup: {e}")
    yield {}
    global _connection
    if _connection:
        _connection.disconnect()
        _connection = None


mcp = FastMCP(
    "blender-mcp",
    instructions="Blender 5.1 + Bonsai BIM integration through MCP — 147 tools controlling live Blender desktop",
    lifespan=server_lifespan,
    # host=/port= used to live here on the FastMCP() ctor — bundled-mcp
    # behavior. Standalone fastmcp 4.x puts them on mcp.run() instead (see
    # main() below); a positional or ctor-kwarg host/port silently does
    # nothing (or throws) on the standalone build, which would have bound
    # the wrong address, failed the Dockerfile HEALTHCHECK and flipped the
    # container unhealthy/restart-looping forever. Keep instructions= as a
    # kwarg: the SDK v2 ctor's positional slot shifted.
)


from blender_tool_tags import TOOL_TAGS, PRESETS, preset_tags
from blender_paths import jail_or_error  # noqa: F401 (used at tool call sites below)

# ── Tool classification ────────────────────────────────────────────
# Derived from the tool name at registration, so adding a tool stays a
# one-decorator affair. Same heuristic shape as qgis_mcp_server.py.
_RO_PREFIXES = ("get_", "list_", "describe_", "search_")
# ping is a liveness probe (read-only); the rest are grouped by their own
# section header above despite not matching a get_/list_ prefix.
_RO_NAMES = frozenset({"ping"})
_DESTRUCTIVE_PREFIXES = ("delete_", "remove_", "clear_")
# Destructive without the prefix: replaces the whole scene/file, runs
# arbitrary input, or permanently collapses geometry (see blender_rules.py's
# apply-and-boolean-consume-their-target and new-file-open-file-no-confirm).
_DESTRUCTIVE_NAMES = frozenset({
    "execute_code", "run_tool", "new_file", "open_file",
    "apply_modifier", "boolean_operation", "bim_purge_unused",
    "bim_run_ids_check",
})
# Repeating the same call leaves the same state. set_*/assign_* qualify;
# create_*/add_*/duplicate_* (a second copy) and anything that runs
# arbitrary input do not.
_IDEMPOTENT_PREFIXES = ("set_", "assign_")

# What a tool can reach beyond the open Blender session, from its parameter
# names. Surfaced as meta "blender/reach" and in describe_tool, and drives
# openWorldHint. Informational: nothing is refused because of it (the path
# JAIL below is the actual enforcement; this is just the advertised shape).
_FILE_PARAMS = frozenset({
    "filepath", "output_dir", "texture_path", "ids_filepath",
})
_CODE_TOOLS = frozenset({"execute_code", "run_tool"})


def _reach(name, params):
    reach = set()
    if _FILE_PARAMS & set(params):
        reach.add("files")
    if name in _CODE_TOOLS:
        reach.add("code")  # can do anything files can, and more
    return sorted(reach)


# Pinned into client context instead of being discovered on demand. With tool
# search the client loads only tool NAMES up front; these few can reach
# everything else, so the first call of a session costs no search round-trip.
_ALWAYS_LOAD = frozenset({
    "ping", "get_blender_info", "execute_code", "search_tools",
})

# Tools whose honest output is large enough that a client's own
# spill-to-file-reference threshold would otherwise kick in silently.
_MAX_RESULT_CHARS = {
    "get_scene_info": 150_000,
    "bim_query_elements": 200_000,
    "bim_get_spatial_tree": 120_000,
    "get_mesh_data": 100_000,
    "execute_code": 250_000,
}

# name -> {fn, doc, tag, params, annotations, reach}: everything search_tools,
# describe_tool and run_tool need, filled in by qtool at registration. Kept
# here rather than read back from FastMCP so it also covers tools a preset
# has hidden — reaching those is what run_tool is for.
_TOOL_INDEX: Dict[str, Dict[str, Any]] = {}


def _param_info(f):
    """The tool's parameters as describe_tool reports them (ctx left out)."""
    import inspect
    out = []
    for p in inspect.signature(f).parameters.values():
        if p.name == "ctx" or p.kind in (p.VAR_KEYWORD, p.VAR_POSITIONAL):
            continue
        ann = p.annotation
        type_name = getattr(ann, "__name__", None) or (str(ann) if ann is not p.empty else "any")
        info = {"name": p.name, "type": type_name, "required": p.default is p.empty}
        if p.default is not p.empty:
            info["default"] = p.default
        out.append(info)
    return out


def qtool(fn=None, **kwargs):
    """mcp.tool() plus the annotations, tag and timeout a client can use.

    output_schema=None is the load-bearing part: without it every tool emits
    an outputSchema derived from its `-> str` return, which is dead weight in
    tools/list and has historically caused clients to drop the whole server's
    tool set. On standalone fastmcp the kwarg is output_schema, not the
    bundled build's structured_output — passing the old name silently does
    nothing.

    Wave 0 shipped this as the bare `_tool()` (output_schema suppression
    only, applied mechanically to all 147 `@mcp.tool()` sites via sed). This
    upgrades every one of those same sites — renamed `@qtool` by the same
    kind of mechanical sed, zero per-tool hand editing — to also carry tags,
    annotations and a default timeout.
    """
    def deco(f):
        name = f.__name__
        kwargs.setdefault("output_schema", None)
        kwargs.setdefault("timeout", BLENDER_CALL_TIMEOUT)
        tag = TOOL_TAGS.get(name)
        if tag:
            kwargs["tags"] = set(kwargs.get("tags") or set()) | {tag}
        params = _param_info(f)
        reach = _reach(name, [p["name"] for p in params])
        readonly = name in _RO_NAMES or name.startswith(_RO_PREFIXES)
        destructive = not readonly and (name in _DESTRUCTIVE_NAMES
                                        or name.startswith(_DESTRUCTIVE_PREFIXES))
        idempotent = readonly or (name.startswith(_IDEMPOTENT_PREFIXES)
                                  and name not in _DESTRUCTIVE_NAMES)
        open_world = "code" in reach
        annotations = ToolAnnotations(
            readOnlyHint=readonly,
            destructiveHint=destructive,
            idempotentHint=idempotent,
            openWorldHint=open_world,
        )
        kwargs.setdefault("annotations", annotations)
        injected = {}
        if name in _ALWAYS_LOAD:
            injected["anthropic/alwaysLoad"] = True
        if name in _MAX_RESULT_CHARS:
            injected["anthropic/maxResultSizeChars"] = _MAX_RESULT_CHARS[name]
        if reach:
            injected["blender/reach"] = reach
        if injected:
            # meta is a single dict, not additive — merge so a tool passing
            # its own meta= does not silently lose it.
            kwargs["meta"] = {**injected, **(kwargs.get("meta") or {})}
        _TOOL_INDEX[name] = {
            "fn": f,
            "doc": (f.__doc__ or "").strip(),
            "tag": tag,
            "params": params,
            "reach": reach,
            "annotations": {"readOnly": readonly, "destructive": destructive,
                            "idempotent": idempotent, "openWorld": open_world},
        }
        return mcp.tool(**kwargs)(f)
    return deco(fn) if callable(fn) else deco


# ═══════════════════════════════════════════════════════════════════
# Scene & System
# ═══════════════════════════════════════════════════════════════════

@qtool
def ping(ctx: Context) -> str:
    """Check connectivity to Blender."""
    return cmd("ping")

@qtool
def get_blender_info(ctx: Context) -> str:
    """Return Blender version, scene name, renderer, extensions."""
    return cmd("get_blender_info")

@qtool
def get_scene_info(ctx: Context, limit: int = 20) -> str:
    """Scene overview: objects, materials, collections, render settings."""
    return cmd("get_scene_info", {"limit": limit})

@qtool
def get_object_info(ctx: Context, name: str) -> str:
    """Detailed object info: transform, mesh stats, materials, modifiers, constraints."""
    return cmd("get_object_info", {"name": name})

@qtool
def get_viewport_screenshot(ctx: Context, filepath: str = "/tmp/viewport.png", max_size: int = 800) -> str:
    """Capture 3D viewport to image file."""
    filepath, err = jail_or_error(filepath)
    if err: return err
    return cmd("get_viewport_screenshot", {"filepath": filepath, "max_size": max_size})


# ═══════════════════════════════════════════════════════════════════
# Objects
# ═══════════════════════════════════════════════════════════════════

@qtool
def create_object(ctx: Context, type: str = "cube", name: str = None,
                  location: list = None, rotation: list = None, scale: list = None) -> str:
    """Create a mesh/empty/curve/text object. Types: cube, sphere, cylinder, cone, torus, plane, circle, monkey, ico_sphere, grid, empty, curve, text."""
    p = {"type": type}
    for k, v in {"name": name, "location": location, "rotation": rotation, "scale": scale}.items():
        if v is not None: p[k] = v
    return cmd("create_object", p)

@qtool
def delete_objects(ctx: Context, names: list) -> str:
    """Delete objects by name."""
    return cmd("delete_objects", {"names": names})

@qtool
def duplicate_object(ctx: Context, name: str, linked: bool = False) -> str:
    """Duplicate an object. linked=True shares mesh data."""
    return cmd("duplicate_object", {"name": name, "linked": linked})

@qtool
def select_objects(ctx: Context, names: list, deselect_others: bool = True) -> str:
    """Select objects by name."""
    return cmd("select_objects", {"names": names, "deselect_others": deselect_others})

@qtool
def set_active_object(ctx: Context, name: str) -> str:
    """Set the active object."""
    return cmd("set_active_object", {"name": name})

@qtool
def transform_object(ctx: Context, name: str, location: list = None,
                     rotation: list = None, scale: list = None) -> str:
    """Set object location/rotation/scale."""
    p = {"name": name}
    for k, v in {"location": location, "rotation": rotation, "scale": scale}.items():
        if v is not None: p[k] = v
    return cmd("transform_object", p)

@qtool
def set_parent(ctx: Context, child_names: list, parent_name: str) -> str:
    """Parent objects to another object."""
    return cmd("set_parent", {"child_names": child_names, "parent_name": parent_name})

@qtool
def clear_parent(ctx: Context, names: list, keep_transform: bool = True) -> str:
    """Clear parenting."""
    return cmd("clear_parent", {"names": names, "keep_transform": keep_transform})

@qtool
def rename_object(ctx: Context, name: str, new_name: str) -> str:
    """Rename an object."""
    return cmd("rename_object", {"name": name, "new_name": new_name})

@qtool
def list_objects(ctx: Context, type_filter: str = None) -> str:
    """List all objects. Optional filter: MESH, LIGHT, CAMERA, EMPTY, CURVE, etc."""
    p = {}
    if type_filter: p["type_filter"] = type_filter
    return cmd("list_objects", p)


# ═══════════════════════════════════════════════════════════════════
# Mesh & Modifiers
# ═══════════════════════════════════════════════════════════════════

@qtool
def add_modifier(ctx: Context, object_name: str, modifier_type: str,
                 name: str = None, settings: dict = None) -> str:
    """Add modifier: SUBSURF, MIRROR, ARRAY, BEVEL, SOLIDIFY, BOOLEAN, DECIMATE, etc."""
    p = {"object_name": object_name, "modifier_type": modifier_type}
    if name: p["name"] = name
    if settings: p["settings"] = settings
    return cmd("add_modifier", p)

@qtool
def remove_modifier(ctx: Context, object_name: str, modifier_name: str) -> str:
    """Remove a modifier from an object."""
    return cmd("remove_modifier", {"object_name": object_name, "modifier_name": modifier_name})

@qtool
def apply_modifier(ctx: Context, object_name: str, modifier_name: str) -> str:
    """Apply a modifier to the mesh."""
    return cmd("apply_modifier", {"object_name": object_name, "modifier_name": modifier_name})

@qtool
def list_modifiers(ctx: Context, object_name: str) -> str:
    """List all modifiers on an object."""
    return cmd("list_modifiers", {"object_name": object_name})

@qtool
def set_modifier_property(ctx: Context, object_name: str, modifier_name: str,
                          property_name: str, value=None) -> str:
    """Set a specific modifier property."""
    return cmd("set_modifier_property", {"object_name": object_name, "modifier_name": modifier_name,
                                          "property_name": property_name, "value": value})

@qtool
def boolean_operation(ctx: Context, object_name: str, target_name: str,
                      operation: str = "DIFFERENCE") -> str:
    """Boolean op: DIFFERENCE, UNION, INTERSECT. Applies immediately."""
    return cmd("boolean_operation", {"object_name": object_name, "target_name": target_name,
                                      "operation": operation})

@qtool
def get_mesh_data(ctx: Context, object_name: str) -> str:
    """Get mesh vertex/edge/face counts, UV layers, bounding box."""
    return cmd("get_mesh_data", {"object_name": object_name})

@qtool
def set_smooth_shading(ctx: Context, object_name: str, smooth: bool = True) -> str:
    """Toggle smooth/flat shading on a mesh."""
    return cmd("set_smooth_shading", {"object_name": object_name, "smooth": smooth})


# ═══════════════════════════════════════════════════════════════════
# Materials
# ═══════════════════════════════════════════════════════════════════

@qtool
def create_material(ctx: Context, name: str, color: list = None,
                    metallic: float = None, roughness: float = None) -> str:
    """Create Principled BSDF material. Color: [R,G,B] 0-1."""
    p = {"name": name}
    for k, v in {"color": color, "metallic": metallic, "roughness": roughness}.items():
        if v is not None: p[k] = v
    return cmd("create_material", p)

@qtool
def assign_material(ctx: Context, object_name: str, material_name: str,
                    slot_index: int = 0) -> str:
    """Assign material to object."""
    return cmd("assign_material", {"object_name": object_name, "material_name": material_name,
                                    "slot_index": slot_index})

@qtool
def edit_material(ctx: Context, material_name: str, color: list = None,
                  metallic: float = None, roughness: float = None,
                  emission_color: list = None, emission_strength: float = None,
                  alpha: float = None) -> str:
    """Edit Principled BSDF material properties."""
    p = {"material_name": material_name}
    for k, v in {"color": color, "metallic": metallic, "roughness": roughness,
                 "emission_color": emission_color, "emission_strength": emission_strength,
                 "alpha": alpha}.items():
        if v is not None: p[k] = v
    return cmd("edit_material", p)

@qtool
def list_materials(ctx: Context) -> str:
    """List all materials with properties."""
    return cmd("list_materials")

@qtool
def remove_material(ctx: Context, material_name: str) -> str:
    """Remove a material."""
    return cmd("remove_material", {"material_name": material_name})

@qtool
def add_texture_node(ctx: Context, material_name: str, texture_path: str,
                     node_type: str = "base_color") -> str:
    """Add image texture to material. node_type: base_color, metallic, roughness, normal, emission."""
    texture_path, err = jail_or_error(texture_path, "texture_path")
    if err: return err
    return cmd("add_texture_node", {"material_name": material_name, "texture_path": texture_path,
                                     "node_type": node_type})

@qtool
def create_node_material(ctx: Context, material_name: str, node_setup: dict = None) -> str:
    """Create material with Principled BSDF properties: {\"Base Color\": [r,g,b], \"Metallic\": 0.5}."""
    p = {"material_name": material_name}
    if node_setup: p["node_setup"] = node_setup
    return cmd("create_node_material", p)


# ═══════════════════════════════════════════════════════════════════
# Lighting
# ═══════════════════════════════════════════════════════════════════

@qtool
def create_light(ctx: Context, type: str = "POINT", name: str = None,
                 location: list = None, energy: float = 1000, color: list = None) -> str:
    """Create light: POINT, SUN, SPOT, AREA."""
    p = {"type": type, "energy": energy}
    for k, v in {"name": name, "location": location, "color": color}.items():
        if v is not None: p[k] = v
    return cmd("create_light", p)

@qtool
def edit_light(ctx: Context, name: str, energy: float = None, color: list = None,
               shadow: bool = None, size: float = None) -> str:
    """Edit light properties."""
    p = {"name": name}
    for k, v in {"energy": energy, "color": color, "shadow": shadow, "size": size}.items():
        if v is not None: p[k] = v
    return cmd("edit_light", p)

@qtool
def set_world_hdri(ctx: Context, filepath: str, strength: float = 1.0,
                   rotation: float = 0.0) -> str:
    """Set HDRI environment map."""
    filepath, err = jail_or_error(filepath)
    if err: return err
    return cmd("set_world_hdri", {"filepath": filepath, "strength": strength, "rotation": rotation})

@qtool
def set_world_color(ctx: Context, color: list = None) -> str:
    """Set solid world background color [R,G,B]."""
    return cmd("set_world_color", {"color": color})

@qtool
def list_lights(ctx: Context) -> str:
    """List all lights in the scene."""
    return cmd("list_lights")


# ═══════════════════════════════════════════════════════════════════
# Camera
# ═══════════════════════════════════════════════════════════════════

@qtool
def create_camera(ctx: Context, name: str = None, location: list = None,
                  rotation: list = None, focal_length: float = 50) -> str:
    """Create a camera."""
    p = {"focal_length": focal_length}
    for k, v in {"name": name, "location": location, "rotation": rotation}.items():
        if v is not None: p[k] = v
    return cmd("create_camera", p)

@qtool
def set_active_camera(ctx: Context, name: str) -> str:
    """Set active camera for rendering."""
    return cmd("set_active_camera", {"name": name})

@qtool
def edit_camera(ctx: Context, name: str, focal_length: float = None,
                sensor_width: float = None, clip_start: float = None,
                clip_end: float = None) -> str:
    """Edit camera lens properties."""
    p = {"name": name}
    for k, v in {"focal_length": focal_length, "sensor_width": sensor_width,
                 "clip_start": clip_start, "clip_end": clip_end}.items():
        if v is not None: p[k] = v
    return cmd("edit_camera", p)

@qtool
def set_camera_dof(ctx: Context, name: str, enabled: bool = True,
                   focus_object: str = None, focus_distance: float = None,
                   f_stop: float = 2.8) -> str:
    """Configure depth of field."""
    p = {"name": name, "enabled": enabled, "f_stop": f_stop}
    if focus_object: p["focus_object"] = focus_object
    if focus_distance is not None: p["focus_distance"] = focus_distance
    return cmd("set_camera_dof", p)

@qtool
def look_at(ctx: Context, camera_name: str, target: list) -> str:
    """Point camera at [X,Y,Z] target."""
    return cmd("look_at", {"camera_name": camera_name, "target": target})


# ═══════════════════════════════════════════════════════════════════
# Rendering
# ═══════════════════════════════════════════════════════════════════

@qtool
def set_render_engine(ctx: Context, engine: str = "CYCLES") -> str:
    """Set render engine: CYCLES, EEVEE, WORKBENCH."""
    return cmd("set_render_engine", {"engine": engine})

@qtool
def set_render_settings(ctx: Context, resolution_x: int = None, resolution_y: int = None,
                        samples: int = None, film_transparent: bool = None,
                        use_denoising: bool = None) -> str:
    """Configure render settings."""
    p = {}
    for k, v in {"resolution_x": resolution_x, "resolution_y": resolution_y,
                 "samples": samples, "film_transparent": film_transparent,
                 "use_denoising": use_denoising}.items():
        if v is not None: p[k] = v
    return cmd("set_render_settings", p)

@qtool
def render_image(ctx: Context, filepath: str, format: str = "PNG") -> str:
    """Render current frame to file. Format: PNG, JPEG, BMP, TIFF, EXR."""
    filepath, err = jail_or_error(filepath)
    if err: return err
    return cmd("render_image", {"filepath": filepath, "format": format})

@qtool
def render_animation(ctx: Context, output_dir: str, format: str = "PNG",
                     frame_start: int = None, frame_end: int = None) -> str:
    """Render animation sequence."""
    output_dir, err = jail_or_error(output_dir, "output_dir")
    if err: return err
    p = {"output_dir": output_dir, "format": format}
    if frame_start is not None: p["frame_start"] = frame_start
    if frame_end is not None: p["frame_end"] = frame_end
    return cmd("render_animation", p)

@qtool
def get_render_settings(ctx: Context) -> str:
    """Get current render configuration."""
    return cmd("get_render_settings")


# ═══════════════════════════════════════════════════════════════════
# Animation
# ═══════════════════════════════════════════════════════════════════

@qtool
def insert_keyframe(ctx: Context, object_name: str, data_path: str,
                    frame: int = None, value=None) -> str:
    """Insert keyframe. data_path: location, rotation_euler, scale, etc."""
    p = {"object_name": object_name, "data_path": data_path}
    if frame is not None: p["frame"] = frame
    if value is not None: p["value"] = value
    return cmd("insert_keyframe", p)

@qtool
def delete_keyframe(ctx: Context, object_name: str, data_path: str, frame: int) -> str:
    """Delete keyframe at frame."""
    return cmd("delete_keyframe", {"object_name": object_name, "data_path": data_path, "frame": frame})

@qtool
def set_frame(ctx: Context, frame: int) -> str:
    """Set current frame."""
    return cmd("set_frame", {"frame": frame})

@qtool
def set_frame_range(ctx: Context, start: int, end: int) -> str:
    """Set animation frame range."""
    return cmd("set_frame_range", {"start": start, "end": end})

@qtool
def get_keyframes(ctx: Context, object_name: str) -> str:
    """List all keyframes on an object."""
    return cmd("get_keyframes", {"object_name": object_name})

@qtool
def set_interpolation(ctx: Context, object_name: str, interpolation: str = "BEZIER") -> str:
    """Set keyframe interpolation: BEZIER, LINEAR, CONSTANT."""
    return cmd("set_interpolation", {"object_name": object_name, "interpolation": interpolation})


# ═══════════════════════════════════════════════════════════════════
# Collections
# ═══════════════════════════════════════════════════════════════════

@qtool
def create_collection(ctx: Context, name: str, parent: str = None) -> str:
    """Create a collection."""
    p = {"name": name}
    if parent: p["parent"] = parent
    return cmd("create_collection", p)

@qtool
def delete_collection(ctx: Context, name: str) -> str:
    """Delete a collection."""
    return cmd("delete_collection", {"name": name})

@qtool
def move_to_collection(ctx: Context, object_names: list, collection_name: str) -> str:
    """Move objects to collection."""
    return cmd("move_to_collection", {"object_names": object_names, "collection_name": collection_name})

@qtool
def set_collection_visibility(ctx: Context, name: str, visible: bool = True,
                              viewport: bool = True, render: bool = True) -> str:
    """Set collection visibility."""
    return cmd("set_collection_visibility", {"name": name, "visible": visible,
                                              "viewport": viewport, "render": render})

@qtool
def list_collections(ctx: Context) -> str:
    """List all collections with hierarchy."""
    return cmd("list_collections")


# ═══════════════════════════════════════════════════════════════════
# File Operations
# ═══════════════════════════════════════════════════════════════════

@qtool
def save_file(ctx: Context, filepath: str = None) -> str:
    """Save current .blend file."""
    p = {}
    if filepath:
        filepath, err = jail_or_error(filepath)
        if err: return err
        p["filepath"] = filepath
    return cmd("save_file", p)

@qtool
def open_file(ctx: Context, filepath: str) -> str:
    """Open a .blend file."""
    filepath, err = jail_or_error(filepath)
    if err: return err
    return cmd("open_file", {"filepath": filepath})

@qtool
def export_file(ctx: Context, filepath: str, format: str = "GLTF",
                selected_only: bool = False) -> str:
    """Export: GLTF, GLB, FBX, OBJ, STL, USD, PLY."""
    filepath, err = jail_or_error(filepath)
    if err: return err
    return cmd("export_file", {"filepath": filepath, "format": format, "selected_only": selected_only})

@qtool
def import_file(ctx: Context, filepath: str, format: str = None) -> str:
    """Import file. Auto-detects format from extension. Supports glTF, FBX, OBJ, STL, USD, IFC."""
    filepath, err = jail_or_error(filepath)
    if err: return err
    p = {"filepath": filepath}
    if format: p["format"] = format
    return cmd("import_file", p)

@qtool
def new_file(ctx: Context) -> str:
    """New empty scene."""
    return cmd("new_file")


# ═══════════════════════════════════════════════════════════════════
# Code Execution
# ═══════════════════════════════════════════════════════════════════

@qtool
def execute_code(ctx: Context, code: str) -> str:
    """Execute arbitrary Python in Blender context. bpy, mathutils, bmesh, ifcopenshell available."""
    return cmd("execute_code", {"code": code})


# ═══════════════════════════════════════════════════════════════════
# UV
# ═══════════════════════════════════════════════════════════════════

@qtool
def smart_uv_project(ctx: Context, object_name: str, angle_limit: float = 66.0,
                     island_margin: float = 0.0) -> str:
    """Smart UV Project."""
    return cmd("smart_uv_project", {"object_name": object_name, "angle_limit": angle_limit,
                                     "island_margin": island_margin})

@qtool
def uv_unwrap(ctx: Context, object_name: str, method: str = "ANGLE_BASED") -> str:
    """UV Unwrap: ANGLE_BASED, CONFORMAL."""
    return cmd("uv_unwrap", {"object_name": object_name, "method": method})

@qtool
def list_uv_maps(ctx: Context, object_name: str) -> str:
    """List UV maps on an object."""
    return cmd("list_uv_maps", {"object_name": object_name})


# ═══════════════════════════════════════════════════════════════════
# BIM: Project
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_create_project(ctx: Context, schema: str = "IFC4") -> str:
    """Create new IFC project with full spatial hierarchy."""
    return cmd("bim_create_project", {"schema": schema})

@qtool
def bim_load_project(ctx: Context, filepath: str) -> str:
    """Load IFC file."""
    filepath, err = jail_or_error(filepath)
    if err: return err
    return cmd("bim_load_project", {"filepath": filepath})

@qtool
def bim_save_project(ctx: Context, filepath: str = None) -> str:
    """Save IFC file to disk."""
    p = {}
    if filepath:
        filepath, err = jail_or_error(filepath)
        if err: return err
        p["filepath"] = filepath
    return cmd("bim_save_project", p)

@qtool
def bim_get_project_info(ctx: Context) -> str:
    """Get IFC schema, units, spatial tree summary, entity count."""
    return cmd("bim_get_project_info")

@qtool
def bim_set_units(ctx: Context, length: str = "MILLIMETRE", area: str = "SQUARE_METRE") -> str:
    """Set project units: METRE, MILLIMETRE, CENTIMETRE."""
    return cmd("bim_set_units", {"length": length, "area": area})


# ═══════════════════════════════════════════════════════════════════
# BIM: Spatial Structure
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_create_spatial_element(ctx: Context, ifc_class: str, name: str = None,
                                parent: str = None) -> str:
    """Create spatial element: IfcSite, IfcBuilding, IfcBuildingStorey, IfcSpace."""
    p = {"ifc_class": ifc_class}
    if name: p["name"] = name
    if parent: p["parent"] = parent
    return cmd("bim_create_spatial_element", p)

@qtool
def bim_get_spatial_tree(ctx: Context) -> str:
    """Get full spatial decomposition tree."""
    return cmd("bim_get_spatial_tree")

@qtool
def bim_assign_container(ctx: Context, object_names: list, container_name: str) -> str:
    """Assign products to a spatial container (storey, building, etc.)."""
    return cmd("bim_assign_container", {"object_names": object_names, "container_name": container_name})

@qtool
def bim_remove_container(ctx: Context, name: str) -> str:
    """Remove spatial element."""
    return cmd("bim_remove_container", {"name": name})

@qtool
def bim_set_default_container(ctx: Context, name: str) -> str:
    """Set default container for new elements."""
    return cmd("bim_set_default_container", {"name": name})

@qtool
def bim_get_container_elements(ctx: Context, name: str) -> str:
    """List elements in a container."""
    return cmd("bim_get_container_elements", {"name": name})


# ═══════════════════════════════════════════════════════════════════
# BIM: Elements
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_add_wall(ctx: Context, coords: list, height: float = 3.0,
                 thickness: float = 0.2, name: str = None) -> str:
    """Create wall from coordinate pairs: [[x1,y1,z1], [x2,y2,z2]]."""
    p = {"coords": coords, "height": height, "thickness": thickness}
    if name: p["name"] = name
    return cmd("bim_add_wall", p)

@qtool
def bim_add_slab(ctx: Context, coords: list, thickness: float = 0.2,
                 name: str = None) -> str:
    """Create slab from outline: [[x1,y1], [x2,y2], [x3,y3], ...]."""
    p = {"coords": coords, "thickness": thickness}
    if name: p["name"] = name
    return cmd("bim_add_slab", p)

@qtool
def bim_add_column(ctx: Context, location: list, height: float = 3.0,
                   width: float = 0.3, depth: float = 0.3, name: str = None) -> str:
    """Create column at location with given dimensions."""
    p = {"location": location, "height": height, "width": width, "depth": depth}
    if name: p["name"] = name
    return cmd("bim_add_column", p)

@qtool
def bim_add_beam(ctx: Context, start: list, end: list, width: float = 0.2,
                 depth: float = 0.4, name: str = None) -> str:
    """Create beam between two points."""
    p = {"start": start, "end": end, "width": width, "depth": depth}
    if name: p["name"] = name
    return cmd("bim_add_beam", p)

@qtool
def bim_add_door(ctx: Context, wall_name: str, width: float = 0.9,
                 height: float = 2.1, location: float = None, name: str = None) -> str:
    """Add door to wall. location is distance along wall."""
    p = {"wall_name": wall_name, "width": width, "height": height}
    if location is not None: p["location"] = location
    if name: p["name"] = name
    return cmd("bim_add_door", p)

@qtool
def bim_add_window(ctx: Context, wall_name: str, width: float = 1.2,
                   height: float = 1.5, sill_height: float = 0.9,
                   location: float = None, name: str = None) -> str:
    """Add window to wall."""
    p = {"wall_name": wall_name, "width": width, "height": height, "sill_height": sill_height}
    if location is not None: p["location"] = location
    if name: p["name"] = name
    return cmd("bim_add_window", p)

@qtool
def bim_add_stair(ctx: Context, location: list = None, width: float = 1.2,
                  height: float = 3.0, treads: int = 16, name: str = None) -> str:
    """Create a straight stair."""
    p = {"width": width, "height": height, "treads": treads}
    if location: p["location"] = location
    if name: p["name"] = name
    return cmd("bim_add_stair", p)

@qtool
def bim_remove_element(ctx: Context, name: str) -> str:
    """Remove BIM element by name."""
    return cmd("bim_remove_element", {"name": name})


# ═══════════════════════════════════════════════════════════════════
# BIM: Properties
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_add_pset(ctx: Context, object_name: str, pset_name: str, properties: dict) -> str:
    """Add/edit property set on an element."""
    return cmd("bim_add_pset", {"object_name": object_name, "pset_name": pset_name, "properties": properties})

@qtool
def bim_get_psets(ctx: Context, object_name: str) -> str:
    """Get all property sets for an element."""
    return cmd("bim_get_psets", {"object_name": object_name})

@qtool
def bim_add_qto(ctx: Context, object_name: str, qto_name: str, quantities: dict) -> str:
    """Add quantity take-off set."""
    return cmd("bim_add_qto", {"object_name": object_name, "qto_name": qto_name, "quantities": quantities})

@qtool
def bim_get_attributes(ctx: Context, object_name: str) -> str:
    """Get IFC attributes (GlobalId, Name, Description, etc.)."""
    return cmd("bim_get_attributes", {"object_name": object_name})

@qtool
def bim_edit_attribute(ctx: Context, object_name: str, attribute: str, value: str) -> str:
    """Edit an IFC attribute."""
    return cmd("bim_edit_attribute", {"object_name": object_name, "attribute": attribute, "value": value})

@qtool
def bim_query_elements(ctx: Context, ifc_class: str = None, pset_filter: str = None,
                       container: str = None, limit: int = 50) -> str:
    """Query elements by class/property/container. pset_filter: 'PsetName.PropName=Value'."""
    p = {"limit": limit}
    if ifc_class: p["ifc_class"] = ifc_class
    if pset_filter: p["pset_filter"] = pset_filter
    if container: p["container"] = container
    return cmd("bim_query_elements", p)


# ═══════════════════════════════════════════════════════════════════
# BIM: Materials
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_add_material(ctx: Context, name: str, category: str = None) -> str:
    """Create IFC material."""
    p = {"name": name}
    if category: p["category"] = category
    return cmd("bim_add_material", p)

@qtool
def bim_assign_material(ctx: Context, object_name: str, material_name: str) -> str:
    """Assign IFC material to element."""
    return cmd("bim_assign_material", {"object_name": object_name, "material_name": material_name})

@qtool
def bim_add_material_layer_set(ctx: Context, name: str, layers: list) -> str:
    """Create layered material. layers: [{\"material\": \"name\", \"thickness\": 0.1}, ...]."""
    return cmd("bim_add_material_layer_set", {"name": name, "layers": layers})

@qtool
def bim_add_material_profile_set(ctx: Context, name: str, profiles: list) -> str:
    """Create profile material for structural elements."""
    return cmd("bim_add_material_profile_set", {"name": name, "profiles": profiles})

@qtool
def bim_list_materials(ctx: Context) -> str:
    """List all IFC materials and material sets."""
    return cmd("bim_list_materials")


# ═══════════════════════════════════════════════════════════════════
# BIM: Types
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_create_type(ctx: Context, ifc_class: str, name: str = None,
                    predefined_type: str = None) -> str:
    """Create element type (e.g., IfcWallType, IfcSlabType)."""
    p = {"ifc_class": ifc_class}
    if name: p["name"] = name
    if predefined_type: p["predefined_type"] = predefined_type
    return cmd("bim_create_type", p)

@qtool
def bim_assign_type(ctx: Context, object_name: str, type_name: str) -> str:
    """Assign type to element occurrence."""
    return cmd("bim_assign_type", {"object_name": object_name, "type_name": type_name})

@qtool
def bim_list_types(ctx: Context, ifc_class: str = None) -> str:
    """List element types. Optional filter by class."""
    p = {}
    if ifc_class: p["ifc_class"] = ifc_class
    return cmd("bim_list_types", p)

@qtool
def bim_get_type_info(ctx: Context, name: str) -> str:
    """Get type details: material, geometry, properties."""
    return cmd("bim_get_type_info", {"name": name})


# ═══════════════════════════════════════════════════════════════════
# BIM: Geometry
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_add_opening(ctx: Context, element_name: str, location: list,
                    width: float, height: float, depth: float = 1.0) -> str:
    """Add void/opening to a wall or slab."""
    return cmd("bim_add_opening", {"element_name": element_name, "location": location,
                                    "width": width, "height": height, "depth": depth})

@qtool
def bim_add_filling(ctx: Context, opening_name: str, filling_name: str) -> str:
    """Fill opening with door/window element."""
    return cmd("bim_add_filling", {"opening_name": opening_name, "filling_name": filling_name})

@qtool
def bim_join_walls(ctx: Context, wall_names: list) -> str:
    """Join wall endpoints."""
    return cmd("bim_join_walls", {"wall_names": wall_names})

@qtool
def bim_align_element(ctx: Context, name: str, target_name: str, axis: str = "Z") -> str:
    """Align element to another on X, Y, or Z axis."""
    return cmd("bim_align_element", {"name": name, "target_name": target_name, "axis": axis})

@qtool
def bim_edit_placement(ctx: Context, name: str, location: list = None,
                       rotation: list = None) -> str:
    """Edit object placement in IFC."""
    p = {"name": name}
    if location: p["location"] = location
    if rotation: p["rotation"] = rotation
    return cmd("bim_edit_placement", p)


# ═══════════════════════════════════════════════════════════════════
# BIM: Classification
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_add_classification(ctx: Context, source: str, name: str = None,
                            edition: str = None) -> str:
    """Add classification system (Uniclass, OmniClass, etc.)."""
    p = {"source": source}
    if name: p["name"] = name
    if edition: p["edition"] = edition
    return cmd("bim_add_classification", p)

@qtool
def bim_classify_element(ctx: Context, object_name: str, reference: str,
                          classification: str = None) -> str:
    """Assign classification reference to element."""
    p = {"object_name": object_name, "reference": reference}
    if classification: p["classification"] = classification
    return cmd("bim_classify_element", p)

@qtool
def bim_list_classifications(ctx: Context) -> str:
    """List active classification systems."""
    return cmd("bim_list_classifications")

@qtool
def bim_get_element_classifications(ctx: Context, object_name: str) -> str:
    """Get classifications assigned to element."""
    return cmd("bim_get_element_classifications", {"object_name": object_name})


# ═══════════════════════════════════════════════════════════════════
# BIM: Cost (5D)
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_add_cost_schedule(ctx: Context, name: str, predefined_type: str = "BUDGET") -> str:
    """Create cost schedule."""
    return cmd("bim_add_cost_schedule", {"name": name, "predefined_type": predefined_type})

@qtool
def bim_add_cost_item(ctx: Context, schedule_name: str, name: str,
                      quantity: float = None, unit_cost: float = None) -> str:
    """Add cost line item."""
    p = {"schedule_name": schedule_name, "name": name}
    if quantity is not None: p["quantity"] = quantity
    if unit_cost is not None: p["unit_cost"] = unit_cost
    return cmd("bim_add_cost_item", p)

@qtool
def bim_assign_cost_to_element(ctx: Context, cost_item_id: int, object_names: list) -> str:
    """Link cost items to building elements."""
    return cmd("bim_assign_cost_to_element", {"cost_item_id": cost_item_id, "object_names": object_names})

@qtool
def bim_calculate_costs(ctx: Context, schedule_name: str) -> str:
    """Calculate cost totals."""
    return cmd("bim_calculate_costs", {"schedule_name": schedule_name})

@qtool
def bim_export_cost_schedule(ctx: Context, schedule_name: str, filepath: str,
                              format: str = "CSV") -> str:
    """Export cost schedule: CSV, XLSX."""
    filepath, err = jail_or_error(filepath)
    if err: return err
    return cmd("bim_export_cost_schedule", {"schedule_name": schedule_name,
                                             "filepath": filepath, "format": format})


# ═══════════════════════════════════════════════════════════════════
# BIM: Schedule (4D)
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_add_work_schedule(ctx: Context, name: str) -> str:
    """Create work schedule."""
    return cmd("bim_add_work_schedule", {"name": name})

@qtool
def bim_add_task(ctx: Context, schedule_name: str, name: str, start: str = None,
                 finish: str = None, duration: str = None) -> str:
    """Add task to schedule. Dates: ISO format."""
    p = {"schedule_name": schedule_name, "name": name}
    for k, v in {"start": start, "finish": finish, "duration": duration}.items():
        if v: p[k] = v
    return cmd("bim_add_task", p)

@qtool
def bim_assign_task_to_element(ctx: Context, task_id: int, object_names: list) -> str:
    """Link tasks to building products."""
    return cmd("bim_assign_task_to_element", {"task_id": task_id, "object_names": object_names})

@qtool
def bim_add_task_sequence(ctx: Context, predecessor_id: int, successor_id: int,
                           type: str = "FINISH_START") -> str:
    """Add predecessor relationship."""
    return cmd("bim_add_task_sequence", {"predecessor_id": predecessor_id,
                                          "successor_id": successor_id, "type": type})

@qtool
def bim_calculate_schedule(ctx: Context, schedule_name: str) -> str:
    """Recalculate critical path."""
    return cmd("bim_calculate_schedule", {"schedule_name": schedule_name})

@qtool
def bim_get_schedule_info(ctx: Context, schedule_name: str) -> str:
    """Get tasks, durations, sequences."""
    return cmd("bim_get_schedule_info", {"schedule_name": schedule_name})


# ═══════════════════════════════════════════════════════════════════
# BIM: Clash Detection
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_create_clash_set(ctx: Context, name: str, group_a: list, group_b: list,
                          tolerance: float = 0.01) -> str:
    """Define clash detection between two groups of elements."""
    return cmd("bim_create_clash_set", {"name": name, "group_a": group_a,
                                         "group_b": group_b, "tolerance": tolerance})

@qtool
def bim_run_clash_detection(ctx: Context, clash_set_name: str = None) -> str:
    """Run clash detection."""
    p = {}
    if clash_set_name: p["clash_set_name"] = clash_set_name
    return cmd("bim_run_clash_detection", p)

@qtool
def bim_get_clash_results(ctx: Context, clash_set_name: str = None) -> str:
    """Get clash detection results."""
    p = {}
    if clash_set_name: p["clash_set_name"] = clash_set_name
    return cmd("bim_get_clash_results", p)

@qtool
def bim_select_clashing_elements(ctx: Context, clash_id: int = 0,
                                  clash_set_name: str = None) -> str:
    """Select clashing elements in viewport."""
    p = {"clash_id": clash_id}
    if clash_set_name: p["clash_set_name"] = clash_set_name
    return cmd("bim_select_clashing_elements", p)


# ═══════════════════════════════════════════════════════════════════
# BIM: Drawing
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_add_drawing(ctx: Context, name: str, type: str = "PLAN",
                    location: list = None) -> str:
    """Create drawing: PLAN, ELEVATION, SECTION, DETAIL, MODEL."""
    p = {"name": name, "type": type}
    if location: p["location"] = location
    return cmd("bim_add_drawing", p)

@qtool
def bim_add_sheet(ctx: Context, name: str, titleblock: str = None) -> str:
    """Create drawing sheet."""
    p = {"name": name}
    if titleblock: p["titleblock"] = titleblock
    return cmd("bim_add_sheet", p)

@qtool
def bim_add_drawing_to_sheet(ctx: Context, drawing_name: str, sheet_name: str) -> str:
    """Place drawing on sheet."""
    return cmd("bim_add_drawing_to_sheet", {"drawing_name": drawing_name, "sheet_name": sheet_name})

@qtool
def bim_add_annotation(ctx: Context, drawing_name: str, type: str,
                       text: str = None) -> str:
    """Add annotation: TEXT, DIMENSION, LEADER, STAIR_ARROW, etc."""
    p = {"drawing_name": drawing_name, "type": type}
    if text: p["text"] = text
    return cmd("bim_add_annotation", p)

@qtool
def bim_export_drawing(ctx: Context, sheet_name: str = None, filepath: str = None,
                       format: str = "PDF") -> str:
    """Export drawings: PDF, SVG."""
    p = {"format": format}
    if sheet_name: p["sheet_name"] = sheet_name
    if filepath:
        filepath, err = jail_or_error(filepath)
        if err: return err
        p["filepath"] = filepath
    return cmd("bim_export_drawing", p)


# ═══════════════════════════════════════════════════════════════════
# BIM: Systems (MEP)
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_add_system(ctx: Context, name: str,
                   ifc_class: str = "IfcDistributionSystem") -> str:
    """Create MEP system (HVAC, plumbing, electrical)."""
    return cmd("bim_add_system", {"name": name, "ifc_class": ifc_class})

@qtool
def bim_assign_to_system(ctx: Context, object_names: list, system_name: str) -> str:
    """Assign elements to system."""
    return cmd("bim_assign_to_system", {"object_names": object_names, "system_name": system_name})

@qtool
def bim_connect_ports(ctx: Context, element_a: str, element_b: str,
                      port_a: int = 0, port_b: int = 0) -> str:
    """Connect distribution element ports."""
    return cmd("bim_connect_ports", {"element_a": element_a, "element_b": element_b,
                                      "port_a": port_a, "port_b": port_b})

@qtool
def bim_list_systems(ctx: Context) -> str:
    """List all MEP systems."""
    return cmd("bim_list_systems")


# ═══════════════════════════════════════════════════════════════════
# BIM: Georeference
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_set_georeferencing(ctx: Context, crs: str, eastings: float = 0,
                            northings: float = 0, height: float = 0) -> str:
    """Set CRS and map conversion (EPSG code)."""
    return cmd("bim_set_georeferencing", {"crs": crs, "eastings": eastings,
                                           "northings": northings, "height": height})

@qtool
def bim_set_true_north(ctx: Context, angle: float) -> str:
    """Set true north angle (degrees from Y-axis)."""
    return cmd("bim_set_true_north", {"angle": angle})

@qtool
def bim_get_georeferencing(ctx: Context) -> str:
    """Get current georeferencing info."""
    return cmd("bim_get_georeferencing")


# ═══════════════════════════════════════════════════════════════════
# BIM: BCF Collaboration
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_create_bcf_project(ctx: Context, name: str) -> str:
    """Create BCF project for issue tracking."""
    return cmd("bim_create_bcf_project", {"name": name})

@qtool
def bim_add_bcf_topic(ctx: Context, title: str, description: str = None,
                      type: str = "Issue", priority: str = "Normal") -> str:
    """Add BCF issue/topic."""
    p = {"title": title, "type": type, "priority": priority}
    if description: p["description"] = description
    return cmd("bim_add_bcf_topic", p)

@qtool
def bim_add_bcf_viewpoint(ctx: Context, topic_id: int = 0) -> str:
    """Capture current viewport as BCF viewpoint."""
    return cmd("bim_add_bcf_viewpoint", {"topic_id": topic_id})

@qtool
def bim_list_bcf_topics(ctx: Context) -> str:
    """List all BCF topics."""
    return cmd("bim_list_bcf_topics")

@qtool
def bim_export_bcf(ctx: Context, filepath: str) -> str:
    """Export BCF file."""
    filepath, err = jail_or_error(filepath)
    if err: return err
    return cmd("bim_export_bcf", {"filepath": filepath})


# ═══════════════════════════════════════════════════════════════════
# BIM: Structural
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_add_structural_model(ctx: Context, name: str) -> str:
    """Create structural analysis model."""
    return cmd("bim_add_structural_model", {"name": name})

@qtool
def bim_add_structural_load(ctx: Context, name: str, load_type: str,
                             values: dict = None) -> str:
    """Add structural load."""
    p = {"name": name, "load_type": load_type}
    if values: p["values"] = values
    return cmd("bim_add_structural_load", p)

@qtool
def bim_add_load_case(ctx: Context, name: str, load_type: str = "DEAD_LOAD_G") -> str:
    """Create load case."""
    return cmd("bim_add_load_case", {"name": name, "load_type": load_type})

@qtool
def bim_add_boundary_condition(ctx: Context, element_name: str,
                                condition_type: str = "FIXED") -> str:
    """Add boundary condition: FIXED, PINNED."""
    return cmd("bim_add_boundary_condition", {"element_name": element_name,
                                               "condition_type": condition_type})


# ═══════════════════════════════════════════════════════════════════
# BIM: Validation
# ═══════════════════════════════════════════════════════════════════

@qtool
def bim_validate_ifc(ctx: Context, filepath: str = None) -> str:
    """Validate IFC file against schema rules."""
    p = {}
    if filepath:
        filepath, err = jail_or_error(filepath)
        if err: return err
        p["filepath"] = filepath
    return cmd("bim_validate_ifc", p)

@qtool
def bim_run_ids_check(ctx: Context, ids_filepath: str) -> str:
    """Run IDS (Information Delivery Specification) check."""
    ids_filepath, err = jail_or_error(ids_filepath, "ids_filepath")
    if err: return err
    return cmd("bim_run_ids_check", {"ids_filepath": ids_filepath})

@qtool
def bim_purge_unused(ctx: Context) -> str:
    """Purge unused IFC entities."""
    return cmd("bim_purge_unused")


# ═══════════════════════════════════════════════════════════════════
# Discovery — find, describe and run any tool, also ones a preset hides
# ═══════════════════════════════════════════════════════════════════
# A narrow preset (or a client that loads only a few tools) keeps the context
# small; these three keep everything else one search away. Plain word
# scoring, no embeddings: tool names and docstrings are short and literal.
# Direct port of qgis-mcp's own search_tools/describe_tool/run_tool, same
# signatures.

# Tags currently visible (None = all), kept in step with set_toolset/main so
# search_tools can say whether a hit is callable directly or needs run_tool.
_ACTIVE_TAGS: Optional[set] = None


def _query_words(query):
    import re
    words = []
    for w in re.split(r"[^0-9a-zäöüß]+", (query or "").lower()):
        if len(w) > 3 and w.endswith("s"):
            w = w[:-1]
        if len(w) > 1:
            words.append(w)
    return words[:12]


def _score(words, fields):
    """Each word scores by the best field it appears in (earlier = better)."""
    weights = (3, 2, 1)
    total = 0
    for w in words:
        total += max((wt for wt, f in zip(weights, fields) if w in f), default=0)
    return total


def _summary(doc):
    return doc.split("\n", 1)[0].strip()[:200]


@qtool
def search_tools(ctx: Context, query: str, limit: int = 12) -> str:
    """Find blender-mcp tools by words ("add wall", "render image", "cost
    item"). Returns name, tag, one-line summary, parameters and whether the
    tool is loaded in the current toolset; call loaded ones directly, the
    rest through run_tool."""
    words = _query_words(query)
    if not words:
        return json.dumps({"error": "query needs at least one word of two or more letters"})
    hits = []
    for name, t in _TOOL_INDEX.items():
        fields = (name.replace("_", " "), t["tag"] or "", t["doc"].lower())
        sc = _score(words, fields)
        if sc:
            hits.append((sc, name, t))
    hits.sort(key=lambda h: (-h[0], h[1]))
    limit = max(1, min(int(limit or 12), 40))
    tools = [{
        "name": name,
        "tag": t["tag"],
        "summary": _summary(t["doc"]),
        "params": ", ".join(p["name"] + ("" if p["required"] else "?") for p in t["params"]),
        "loaded": _ACTIVE_TAGS is None or t["tag"] in _ACTIVE_TAGS,
    } for _, name, t in hits[:limit]]
    return json.dumps({"matches": len(hits), "tools": tools}, ensure_ascii=False)


@qtool
def describe_tool(ctx: Context, name: str) -> str:
    """Full description of one tool: docstring, parameters (type, required,
    default), annotations and reach (files / code)."""
    t = _TOOL_INDEX.get(name)
    if t is None:
        return json.dumps({"error": f"no tool '{name}'; find names with search_tools"})
    return json.dumps({
        "name": name, "tag": t["tag"], "doc": t["doc"], "params": t["params"],
        "annotations": t["annotations"], "reach": t["reach"],
        "loaded": _ACTIVE_TAGS is None or t["tag"] in _ACTIVE_TAGS,
    }, ensure_ascii=False, default=str)


@qtool
def run_tool(ctx: Context, name: str, arguments: dict = None):
    """Run any blender-mcp tool by name with a JSON object of arguments —
    also tools the current toolset does not load. Arguments are checked
    against the tool's parameters first: an unknown or missing one is an
    error that lists the valid ones, never a silent fallback to defaults."""
    if name in ("run_tool",):
        return json.dumps({"error": "run_tool cannot run itself"})
    t = _TOOL_INDEX.get(name)
    if t is None:
        return json.dumps({"error": f"no tool '{name}'; find names with search_tools"})
    args = arguments or {}
    if isinstance(args, str):  # some models send the object as JSON text
        try:
            args = json.loads(args) if args.strip() else {}
        except ValueError as e:
            return json.dumps({"error": f"arguments is not valid JSON: {e}"})
    if not isinstance(args, dict):
        return json.dumps({"error": "arguments must be a JSON object"})
    known = {p["name"] for p in t["params"]}
    unknown = sorted(set(args) - known)
    missing = [p["name"] for p in t["params"] if p["required"] and p["name"] not in args]
    if unknown or missing:
        return json.dumps({"error": "arguments do not match the tool",
                           "unknown": unknown, "missing": missing,
                           "params": t["params"]}, ensure_ascii=False, default=str)
    try:
        return t["fn"](ctx, **args)
    except Exception as e:
        return json.dumps({"error": f"{name} failed: {e}"}, ensure_ascii=False)


@qtool
def set_toolset(ctx: Context, preset: str) -> str:
    """Reshape the visible toolset in place: full | generic_blender | bim_authoring | bim_costing | rendering | minimal.

    Switching emits tools/list_changed, so the client picks up the new
    surface without reconnecting. 'full' restores everything."""
    if preset not in PRESETS:
        return json.dumps({"error": f"unknown preset '{preset}'",
                           "available": sorted(PRESETS)}, ensure_ascii=False)
    # 'full' means every tag, not "no argument": a bare mcp.enable() does not
    # clear a previously applied only=True filter.
    global _ACTIVE_TAGS
    tags = preset_tags(preset) or set(TOOL_TAGS.values())
    mcp.enable(tags=tags, only=True)
    _ACTIVE_TAGS = None if preset == "full" else set(tags)
    count = len([n for n, t in TOOL_TAGS.items() if t in tags])
    return json.dumps({"status": "ok", "preset": preset, "tools": count,
                       "tags": sorted(tags)}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════
# Rules — crash, hang and data-loss patterns, as resources and a tool
# ═══════════════════════════════════════════════════════════════════

from blender_rules import RULES, by_slug as _rule_by_slug


def _rule_markdown(r):
    return f"# {r['title']}\n\n_severity: {r['severity']}_\n\n{r['text']}\n"


def _register_rule_resources():
    # Tagged 'escape' like the discovery tools: every preset includes that
    # tag, and enable(only=True) would otherwise hide untagged resources too.
    @mcp.resource("blender://rules", name="blender-rules-index", mime_type="text/markdown",
                  description="Index of known Blender/Bonsai crash and data-loss rules",
                  tags={"escape"})
    def _rules_index() -> str:
        lines = ["# blender-mcp rules", ""]
        lines += [f"- `blender://rules/{r['slug']}` ({r['severity']}): {r['title']}" for r in RULES]
        return "\n".join(lines) + "\n"

    for rule in RULES:
        def make(r):
            def read() -> str:
                return _rule_markdown(r)
            read.__name__ = "rule_" + r["slug"].replace("-", "_")
            return read
        mcp.resource(f"blender://rules/{rule['slug']}", name=f"blender-rule-{rule['slug']}",
                     title=rule["title"], mime_type="text/markdown",
                     description=f"{rule['severity']}: {rule['title']}",
                     tags={"escape"})(make(rule))


_register_rule_resources()


@qtool
def search_rules(ctx: Context, query: str = None, limit: int = 5) -> str:
    """Known Blender/Bonsai crash, data-loss and resource-contention patterns
    with the safe way to do it instead. No query: the index (slug, severity,
    title). With words ("factory startup", "cycles render", "boolean"): the
    matching rules in full. Read these before execute_code, a save that
    overwrites a source IFC, or a heavy render."""
    if not query:
        return json.dumps({"rules": [{"slug": r["slug"], "severity": r["severity"],
                                      "title": r["title"]} for r in RULES]},
                          ensure_ascii=False)
    exact = _rule_by_slug(query.strip())
    if exact:
        return json.dumps({"rules": [{**{k: exact[k] for k in ("slug", "severity", "title", "text")}}]},
                          ensure_ascii=False)
    words = _query_words(query)
    hits = []
    for r in RULES:
        sc = _score(words, (r["title"].lower() + " " + r["keywords"], r["slug"], r["text"].lower()))
        if sc:
            hits.append((sc, r))
    hits.sort(key=lambda h: -h[0])
    limit = max(1, min(int(limit or 5), len(RULES)))
    return json.dumps({"matches": len(hits), "rules": [
        {"slug": r["slug"], "severity": r["severity"], "title": r["title"], "text": r["text"]}
        for _, r in hits[:limit]]}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════

def main():
    # BLENDER_TOOLSET=generic_blender|bim_authoring|bim_costing|rendering|minimal|full (default full).
    sel = os.environ.get("BLENDER_TOOLSET", "full")
    tags = preset_tags(sel)
    if tags:
        global _ACTIVE_TAGS
        mcp.enable(tags=tags, only=True)
        _ACTIVE_TAGS = set(tags)
        logger.info(f"BLENDER_TOOLSET={sel}: limited to tags {sorted(tags)}")

    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport in ("http", "streamable-http", "sse"):
        # host=/port= moved here from the FastMCP() ctor (see the comment
        # there) — the Dockerfile's HEALTHCHECK connects to localhost on
        # FASTMCP_PORT, so an unbound or wrongly-bound port fails it and the
        # container flips unhealthy/restart-looping.
        mcp.run(
            transport=transport,
            host=os.environ.get("FASTMCP_HOST", "0.0.0.0"),
            port=int(os.environ.get("FASTMCP_PORT", "8082")),
        )
    else:
        mcp.run(transport=transport)

if __name__ == "__main__":
    main()
