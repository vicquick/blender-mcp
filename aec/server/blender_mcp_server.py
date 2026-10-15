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
from typing import AsyncIterator, Dict, Any
# Migrated bundled mcp.server.fastmcp -> standalone fastmcp 4.x: the bundled
# build has no tags, no per-tool timeout and no middleware, so toolset
# presets, call timeouts, response caching and the progress heartbeat were
# all unreachable. See qgis-mcp's own migration (same repo family) for the
# reference shape this follows.
from fastmcp import FastMCP, Context

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BlenderMCPServer")

BLENDER_HOST = os.environ.get("DESKTOP_HOST", "aec-web")
BLENDER_PORT = int(os.environ.get("BLENDER_PORT", "9876"))

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


def _tool(fn=None, **kwargs):
    """mcp.tool() with output_schema suppressed by default.

    output_schema=None is the load-bearing part: without it every tool emits
    an outputSchema derived from its `-> str` return, which is dead weight in
    tools/list and has historically caused clients to drop the whole server's
    tool set. On standalone fastmcp the kwarg is output_schema, not the
    bundled build's structured_output — passing the old name silently does
    nothing. Mechanically replaced every `@mcp.tool()` site (147 of them)
    with `@_tool` by sed: no per-tool hand editing, no rename risk. Upgraded
    to the full qtool() (tags, timeout, annotations) in wave 1.
    """
    def deco(f):
        kwargs.setdefault("output_schema", None)
        return mcp.tool(**kwargs)(f)
    return deco(fn) if callable(fn) else deco


# ═══════════════════════════════════════════════════════════════════
# Scene & System
# ═══════════════════════════════════════════════════════════════════

@_tool
def ping(ctx: Context) -> str:
    """Check connectivity to Blender."""
    return cmd("ping")

@_tool
def get_blender_info(ctx: Context) -> str:
    """Return Blender version, scene name, renderer, extensions."""
    return cmd("get_blender_info")

@_tool
def get_scene_info(ctx: Context, limit: int = 20) -> str:
    """Scene overview: objects, materials, collections, render settings."""
    return cmd("get_scene_info", {"limit": limit})

@_tool
def get_object_info(ctx: Context, name: str) -> str:
    """Detailed object info: transform, mesh stats, materials, modifiers, constraints."""
    return cmd("get_object_info", {"name": name})

@_tool
def get_viewport_screenshot(ctx: Context, filepath: str = "/tmp/viewport.png", max_size: int = 800) -> str:
    """Capture 3D viewport to image file."""
    return cmd("get_viewport_screenshot", {"filepath": filepath, "max_size": max_size})


# ═══════════════════════════════════════════════════════════════════
# Objects
# ═══════════════════════════════════════════════════════════════════

@_tool
def create_object(ctx: Context, type: str = "cube", name: str = None,
                  location: list = None, rotation: list = None, scale: list = None) -> str:
    """Create a mesh/empty/curve/text object. Types: cube, sphere, cylinder, cone, torus, plane, circle, monkey, ico_sphere, grid, empty, curve, text."""
    p = {"type": type}
    for k, v in {"name": name, "location": location, "rotation": rotation, "scale": scale}.items():
        if v is not None: p[k] = v
    return cmd("create_object", p)

@_tool
def delete_objects(ctx: Context, names: list) -> str:
    """Delete objects by name."""
    return cmd("delete_objects", {"names": names})

@_tool
def duplicate_object(ctx: Context, name: str, linked: bool = False) -> str:
    """Duplicate an object. linked=True shares mesh data."""
    return cmd("duplicate_object", {"name": name, "linked": linked})

@_tool
def select_objects(ctx: Context, names: list, deselect_others: bool = True) -> str:
    """Select objects by name."""
    return cmd("select_objects", {"names": names, "deselect_others": deselect_others})

@_tool
def set_active_object(ctx: Context, name: str) -> str:
    """Set the active object."""
    return cmd("set_active_object", {"name": name})

@_tool
def transform_object(ctx: Context, name: str, location: list = None,
                     rotation: list = None, scale: list = None) -> str:
    """Set object location/rotation/scale."""
    p = {"name": name}
    for k, v in {"location": location, "rotation": rotation, "scale": scale}.items():
        if v is not None: p[k] = v
    return cmd("transform_object", p)

@_tool
def set_parent(ctx: Context, child_names: list, parent_name: str) -> str:
    """Parent objects to another object."""
    return cmd("set_parent", {"child_names": child_names, "parent_name": parent_name})

@_tool
def clear_parent(ctx: Context, names: list, keep_transform: bool = True) -> str:
    """Clear parenting."""
    return cmd("clear_parent", {"names": names, "keep_transform": keep_transform})

@_tool
def rename_object(ctx: Context, name: str, new_name: str) -> str:
    """Rename an object."""
    return cmd("rename_object", {"name": name, "new_name": new_name})

@_tool
def list_objects(ctx: Context, type_filter: str = None) -> str:
    """List all objects. Optional filter: MESH, LIGHT, CAMERA, EMPTY, CURVE, etc."""
    p = {}
    if type_filter: p["type_filter"] = type_filter
    return cmd("list_objects", p)


# ═══════════════════════════════════════════════════════════════════
# Mesh & Modifiers
# ═══════════════════════════════════════════════════════════════════

@_tool
def add_modifier(ctx: Context, object_name: str, modifier_type: str,
                 name: str = None, settings: dict = None) -> str:
    """Add modifier: SUBSURF, MIRROR, ARRAY, BEVEL, SOLIDIFY, BOOLEAN, DECIMATE, etc."""
    p = {"object_name": object_name, "modifier_type": modifier_type}
    if name: p["name"] = name
    if settings: p["settings"] = settings
    return cmd("add_modifier", p)

@_tool
def remove_modifier(ctx: Context, object_name: str, modifier_name: str) -> str:
    """Remove a modifier from an object."""
    return cmd("remove_modifier", {"object_name": object_name, "modifier_name": modifier_name})

@_tool
def apply_modifier(ctx: Context, object_name: str, modifier_name: str) -> str:
    """Apply a modifier to the mesh."""
    return cmd("apply_modifier", {"object_name": object_name, "modifier_name": modifier_name})

@_tool
def list_modifiers(ctx: Context, object_name: str) -> str:
    """List all modifiers on an object."""
    return cmd("list_modifiers", {"object_name": object_name})

@_tool
def set_modifier_property(ctx: Context, object_name: str, modifier_name: str,
                          property_name: str, value=None) -> str:
    """Set a specific modifier property."""
    return cmd("set_modifier_property", {"object_name": object_name, "modifier_name": modifier_name,
                                          "property_name": property_name, "value": value})

@_tool
def boolean_operation(ctx: Context, object_name: str, target_name: str,
                      operation: str = "DIFFERENCE") -> str:
    """Boolean op: DIFFERENCE, UNION, INTERSECT. Applies immediately."""
    return cmd("boolean_operation", {"object_name": object_name, "target_name": target_name,
                                      "operation": operation})

@_tool
def get_mesh_data(ctx: Context, object_name: str) -> str:
    """Get mesh vertex/edge/face counts, UV layers, bounding box."""
    return cmd("get_mesh_data", {"object_name": object_name})

@_tool
def set_smooth_shading(ctx: Context, object_name: str, smooth: bool = True) -> str:
    """Toggle smooth/flat shading on a mesh."""
    return cmd("set_smooth_shading", {"object_name": object_name, "smooth": smooth})


# ═══════════════════════════════════════════════════════════════════
# Materials
# ═══════════════════════════════════════════════════════════════════

@_tool
def create_material(ctx: Context, name: str, color: list = None,
                    metallic: float = None, roughness: float = None) -> str:
    """Create Principled BSDF material. Color: [R,G,B] 0-1."""
    p = {"name": name}
    for k, v in {"color": color, "metallic": metallic, "roughness": roughness}.items():
        if v is not None: p[k] = v
    return cmd("create_material", p)

@_tool
def assign_material(ctx: Context, object_name: str, material_name: str,
                    slot_index: int = 0) -> str:
    """Assign material to object."""
    return cmd("assign_material", {"object_name": object_name, "material_name": material_name,
                                    "slot_index": slot_index})

@_tool
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

@_tool
def list_materials(ctx: Context) -> str:
    """List all materials with properties."""
    return cmd("list_materials")

@_tool
def remove_material(ctx: Context, material_name: str) -> str:
    """Remove a material."""
    return cmd("remove_material", {"material_name": material_name})

@_tool
def add_texture_node(ctx: Context, material_name: str, texture_path: str,
                     node_type: str = "base_color") -> str:
    """Add image texture to material. node_type: base_color, metallic, roughness, normal, emission."""
    return cmd("add_texture_node", {"material_name": material_name, "texture_path": texture_path,
                                     "node_type": node_type})

@_tool
def create_node_material(ctx: Context, material_name: str, node_setup: dict = None) -> str:
    """Create material with Principled BSDF properties: {\"Base Color\": [r,g,b], \"Metallic\": 0.5}."""
    p = {"material_name": material_name}
    if node_setup: p["node_setup"] = node_setup
    return cmd("create_node_material", p)


# ═══════════════════════════════════════════════════════════════════
# Lighting
# ═══════════════════════════════════════════════════════════════════

@_tool
def create_light(ctx: Context, type: str = "POINT", name: str = None,
                 location: list = None, energy: float = 1000, color: list = None) -> str:
    """Create light: POINT, SUN, SPOT, AREA."""
    p = {"type": type, "energy": energy}
    for k, v in {"name": name, "location": location, "color": color}.items():
        if v is not None: p[k] = v
    return cmd("create_light", p)

@_tool
def edit_light(ctx: Context, name: str, energy: float = None, color: list = None,
               shadow: bool = None, size: float = None) -> str:
    """Edit light properties."""
    p = {"name": name}
    for k, v in {"energy": energy, "color": color, "shadow": shadow, "size": size}.items():
        if v is not None: p[k] = v
    return cmd("edit_light", p)

@_tool
def set_world_hdri(ctx: Context, filepath: str, strength: float = 1.0,
                   rotation: float = 0.0) -> str:
    """Set HDRI environment map."""
    return cmd("set_world_hdri", {"filepath": filepath, "strength": strength, "rotation": rotation})

@_tool
def set_world_color(ctx: Context, color: list = None) -> str:
    """Set solid world background color [R,G,B]."""
    return cmd("set_world_color", {"color": color})

@_tool
def list_lights(ctx: Context) -> str:
    """List all lights in the scene."""
    return cmd("list_lights")


# ═══════════════════════════════════════════════════════════════════
# Camera
# ═══════════════════════════════════════════════════════════════════

@_tool
def create_camera(ctx: Context, name: str = None, location: list = None,
                  rotation: list = None, focal_length: float = 50) -> str:
    """Create a camera."""
    p = {"focal_length": focal_length}
    for k, v in {"name": name, "location": location, "rotation": rotation}.items():
        if v is not None: p[k] = v
    return cmd("create_camera", p)

@_tool
def set_active_camera(ctx: Context, name: str) -> str:
    """Set active camera for rendering."""
    return cmd("set_active_camera", {"name": name})

@_tool
def edit_camera(ctx: Context, name: str, focal_length: float = None,
                sensor_width: float = None, clip_start: float = None,
                clip_end: float = None) -> str:
    """Edit camera lens properties."""
    p = {"name": name}
    for k, v in {"focal_length": focal_length, "sensor_width": sensor_width,
                 "clip_start": clip_start, "clip_end": clip_end}.items():
        if v is not None: p[k] = v
    return cmd("edit_camera", p)

@_tool
def set_camera_dof(ctx: Context, name: str, enabled: bool = True,
                   focus_object: str = None, focus_distance: float = None,
                   f_stop: float = 2.8) -> str:
    """Configure depth of field."""
    p = {"name": name, "enabled": enabled, "f_stop": f_stop}
    if focus_object: p["focus_object"] = focus_object
    if focus_distance is not None: p["focus_distance"] = focus_distance
    return cmd("set_camera_dof", p)

@_tool
def look_at(ctx: Context, camera_name: str, target: list) -> str:
    """Point camera at [X,Y,Z] target."""
    return cmd("look_at", {"camera_name": camera_name, "target": target})


# ═══════════════════════════════════════════════════════════════════
# Rendering
# ═══════════════════════════════════════════════════════════════════

@_tool
def set_render_engine(ctx: Context, engine: str = "CYCLES") -> str:
    """Set render engine: CYCLES, EEVEE, WORKBENCH."""
    return cmd("set_render_engine", {"engine": engine})

@_tool
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

@_tool
def render_image(ctx: Context, filepath: str, format: str = "PNG") -> str:
    """Render current frame to file. Format: PNG, JPEG, BMP, TIFF, EXR."""
    return cmd("render_image", {"filepath": filepath, "format": format})

@_tool
def render_animation(ctx: Context, output_dir: str, format: str = "PNG",
                     frame_start: int = None, frame_end: int = None) -> str:
    """Render animation sequence."""
    p = {"output_dir": output_dir, "format": format}
    if frame_start is not None: p["frame_start"] = frame_start
    if frame_end is not None: p["frame_end"] = frame_end
    return cmd("render_animation", p)

@_tool
def get_render_settings(ctx: Context) -> str:
    """Get current render configuration."""
    return cmd("get_render_settings")


# ═══════════════════════════════════════════════════════════════════
# Animation
# ═══════════════════════════════════════════════════════════════════

@_tool
def insert_keyframe(ctx: Context, object_name: str, data_path: str,
                    frame: int = None, value=None) -> str:
    """Insert keyframe. data_path: location, rotation_euler, scale, etc."""
    p = {"object_name": object_name, "data_path": data_path}
    if frame is not None: p["frame"] = frame
    if value is not None: p["value"] = value
    return cmd("insert_keyframe", p)

@_tool
def delete_keyframe(ctx: Context, object_name: str, data_path: str, frame: int) -> str:
    """Delete keyframe at frame."""
    return cmd("delete_keyframe", {"object_name": object_name, "data_path": data_path, "frame": frame})

@_tool
def set_frame(ctx: Context, frame: int) -> str:
    """Set current frame."""
    return cmd("set_frame", {"frame": frame})

@_tool
def set_frame_range(ctx: Context, start: int, end: int) -> str:
    """Set animation frame range."""
    return cmd("set_frame_range", {"start": start, "end": end})

@_tool
def get_keyframes(ctx: Context, object_name: str) -> str:
    """List all keyframes on an object."""
    return cmd("get_keyframes", {"object_name": object_name})

@_tool
def set_interpolation(ctx: Context, object_name: str, interpolation: str = "BEZIER") -> str:
    """Set keyframe interpolation: BEZIER, LINEAR, CONSTANT."""
    return cmd("set_interpolation", {"object_name": object_name, "interpolation": interpolation})


# ═══════════════════════════════════════════════════════════════════
# Collections
# ═══════════════════════════════════════════════════════════════════

@_tool
def create_collection(ctx: Context, name: str, parent: str = None) -> str:
    """Create a collection."""
    p = {"name": name}
    if parent: p["parent"] = parent
    return cmd("create_collection", p)

@_tool
def delete_collection(ctx: Context, name: str) -> str:
    """Delete a collection."""
    return cmd("delete_collection", {"name": name})

@_tool
def move_to_collection(ctx: Context, object_names: list, collection_name: str) -> str:
    """Move objects to collection."""
    return cmd("move_to_collection", {"object_names": object_names, "collection_name": collection_name})

@_tool
def set_collection_visibility(ctx: Context, name: str, visible: bool = True,
                              viewport: bool = True, render: bool = True) -> str:
    """Set collection visibility."""
    return cmd("set_collection_visibility", {"name": name, "visible": visible,
                                              "viewport": viewport, "render": render})

@_tool
def list_collections(ctx: Context) -> str:
    """List all collections with hierarchy."""
    return cmd("list_collections")


# ═══════════════════════════════════════════════════════════════════
# File Operations
# ═══════════════════════════════════════════════════════════════════

@_tool
def save_file(ctx: Context, filepath: str = None) -> str:
    """Save current .blend file."""
    p = {}
    if filepath: p["filepath"] = filepath
    return cmd("save_file", p)

@_tool
def open_file(ctx: Context, filepath: str) -> str:
    """Open a .blend file."""
    return cmd("open_file", {"filepath": filepath})

@_tool
def export_file(ctx: Context, filepath: str, format: str = "GLTF",
                selected_only: bool = False) -> str:
    """Export: GLTF, GLB, FBX, OBJ, STL, USD, PLY."""
    return cmd("export_file", {"filepath": filepath, "format": format, "selected_only": selected_only})

@_tool
def import_file(ctx: Context, filepath: str, format: str = None) -> str:
    """Import file. Auto-detects format from extension. Supports glTF, FBX, OBJ, STL, USD, IFC."""
    p = {"filepath": filepath}
    if format: p["format"] = format
    return cmd("import_file", p)

@_tool
def new_file(ctx: Context) -> str:
    """New empty scene."""
    return cmd("new_file")


# ═══════════════════════════════════════════════════════════════════
# Code Execution
# ═══════════════════════════════════════════════════════════════════

@_tool
def execute_code(ctx: Context, code: str) -> str:
    """Execute arbitrary Python in Blender context. bpy, mathutils, bmesh, ifcopenshell available."""
    return cmd("execute_code", {"code": code})


# ═══════════════════════════════════════════════════════════════════
# UV
# ═══════════════════════════════════════════════════════════════════

@_tool
def smart_uv_project(ctx: Context, object_name: str, angle_limit: float = 66.0,
                     island_margin: float = 0.0) -> str:
    """Smart UV Project."""
    return cmd("smart_uv_project", {"object_name": object_name, "angle_limit": angle_limit,
                                     "island_margin": island_margin})

@_tool
def uv_unwrap(ctx: Context, object_name: str, method: str = "ANGLE_BASED") -> str:
    """UV Unwrap: ANGLE_BASED, CONFORMAL."""
    return cmd("uv_unwrap", {"object_name": object_name, "method": method})

@_tool
def list_uv_maps(ctx: Context, object_name: str) -> str:
    """List UV maps on an object."""
    return cmd("list_uv_maps", {"object_name": object_name})


# ═══════════════════════════════════════════════════════════════════
# BIM: Project
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_create_project(ctx: Context, schema: str = "IFC4") -> str:
    """Create new IFC project with full spatial hierarchy."""
    return cmd("bim_create_project", {"schema": schema})

@_tool
def bim_load_project(ctx: Context, filepath: str) -> str:
    """Load IFC file."""
    return cmd("bim_load_project", {"filepath": filepath})

@_tool
def bim_save_project(ctx: Context, filepath: str = None) -> str:
    """Save IFC file to disk."""
    p = {}
    if filepath: p["filepath"] = filepath
    return cmd("bim_save_project", p)

@_tool
def bim_get_project_info(ctx: Context) -> str:
    """Get IFC schema, units, spatial tree summary, entity count."""
    return cmd("bim_get_project_info")

@_tool
def bim_set_units(ctx: Context, length: str = "MILLIMETRE", area: str = "SQUARE_METRE") -> str:
    """Set project units: METRE, MILLIMETRE, CENTIMETRE."""
    return cmd("bim_set_units", {"length": length, "area": area})


# ═══════════════════════════════════════════════════════════════════
# BIM: Spatial Structure
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_create_spatial_element(ctx: Context, ifc_class: str, name: str = None,
                                parent: str = None) -> str:
    """Create spatial element: IfcSite, IfcBuilding, IfcBuildingStorey, IfcSpace."""
    p = {"ifc_class": ifc_class}
    if name: p["name"] = name
    if parent: p["parent"] = parent
    return cmd("bim_create_spatial_element", p)

@_tool
def bim_get_spatial_tree(ctx: Context) -> str:
    """Get full spatial decomposition tree."""
    return cmd("bim_get_spatial_tree")

@_tool
def bim_assign_container(ctx: Context, object_names: list, container_name: str) -> str:
    """Assign products to a spatial container (storey, building, etc.)."""
    return cmd("bim_assign_container", {"object_names": object_names, "container_name": container_name})

@_tool
def bim_remove_container(ctx: Context, name: str) -> str:
    """Remove spatial element."""
    return cmd("bim_remove_container", {"name": name})

@_tool
def bim_set_default_container(ctx: Context, name: str) -> str:
    """Set default container for new elements."""
    return cmd("bim_set_default_container", {"name": name})

@_tool
def bim_get_container_elements(ctx: Context, name: str) -> str:
    """List elements in a container."""
    return cmd("bim_get_container_elements", {"name": name})


# ═══════════════════════════════════════════════════════════════════
# BIM: Elements
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_add_wall(ctx: Context, coords: list, height: float = 3.0,
                 thickness: float = 0.2, name: str = None) -> str:
    """Create wall from coordinate pairs: [[x1,y1,z1], [x2,y2,z2]]."""
    p = {"coords": coords, "height": height, "thickness": thickness}
    if name: p["name"] = name
    return cmd("bim_add_wall", p)

@_tool
def bim_add_slab(ctx: Context, coords: list, thickness: float = 0.2,
                 name: str = None) -> str:
    """Create slab from outline: [[x1,y1], [x2,y2], [x3,y3], ...]."""
    p = {"coords": coords, "thickness": thickness}
    if name: p["name"] = name
    return cmd("bim_add_slab", p)

@_tool
def bim_add_column(ctx: Context, location: list, height: float = 3.0,
                   width: float = 0.3, depth: float = 0.3, name: str = None) -> str:
    """Create column at location with given dimensions."""
    p = {"location": location, "height": height, "width": width, "depth": depth}
    if name: p["name"] = name
    return cmd("bim_add_column", p)

@_tool
def bim_add_beam(ctx: Context, start: list, end: list, width: float = 0.2,
                 depth: float = 0.4, name: str = None) -> str:
    """Create beam between two points."""
    p = {"start": start, "end": end, "width": width, "depth": depth}
    if name: p["name"] = name
    return cmd("bim_add_beam", p)

@_tool
def bim_add_door(ctx: Context, wall_name: str, width: float = 0.9,
                 height: float = 2.1, location: float = None, name: str = None) -> str:
    """Add door to wall. location is distance along wall."""
    p = {"wall_name": wall_name, "width": width, "height": height}
    if location is not None: p["location"] = location
    if name: p["name"] = name
    return cmd("bim_add_door", p)

@_tool
def bim_add_window(ctx: Context, wall_name: str, width: float = 1.2,
                   height: float = 1.5, sill_height: float = 0.9,
                   location: float = None, name: str = None) -> str:
    """Add window to wall."""
    p = {"wall_name": wall_name, "width": width, "height": height, "sill_height": sill_height}
    if location is not None: p["location"] = location
    if name: p["name"] = name
    return cmd("bim_add_window", p)

@_tool
def bim_add_stair(ctx: Context, location: list = None, width: float = 1.2,
                  height: float = 3.0, treads: int = 16, name: str = None) -> str:
    """Create a straight stair."""
    p = {"width": width, "height": height, "treads": treads}
    if location: p["location"] = location
    if name: p["name"] = name
    return cmd("bim_add_stair", p)

@_tool
def bim_remove_element(ctx: Context, name: str) -> str:
    """Remove BIM element by name."""
    return cmd("bim_remove_element", {"name": name})


# ═══════════════════════════════════════════════════════════════════
# BIM: Properties
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_add_pset(ctx: Context, object_name: str, pset_name: str, properties: dict) -> str:
    """Add/edit property set on an element."""
    return cmd("bim_add_pset", {"object_name": object_name, "pset_name": pset_name, "properties": properties})

@_tool
def bim_get_psets(ctx: Context, object_name: str) -> str:
    """Get all property sets for an element."""
    return cmd("bim_get_psets", {"object_name": object_name})

@_tool
def bim_add_qto(ctx: Context, object_name: str, qto_name: str, quantities: dict) -> str:
    """Add quantity take-off set."""
    return cmd("bim_add_qto", {"object_name": object_name, "qto_name": qto_name, "quantities": quantities})

@_tool
def bim_get_attributes(ctx: Context, object_name: str) -> str:
    """Get IFC attributes (GlobalId, Name, Description, etc.)."""
    return cmd("bim_get_attributes", {"object_name": object_name})

@_tool
def bim_edit_attribute(ctx: Context, object_name: str, attribute: str, value: str) -> str:
    """Edit an IFC attribute."""
    return cmd("bim_edit_attribute", {"object_name": object_name, "attribute": attribute, "value": value})

@_tool
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

@_tool
def bim_add_material(ctx: Context, name: str, category: str = None) -> str:
    """Create IFC material."""
    p = {"name": name}
    if category: p["category"] = category
    return cmd("bim_add_material", p)

@_tool
def bim_assign_material(ctx: Context, object_name: str, material_name: str) -> str:
    """Assign IFC material to element."""
    return cmd("bim_assign_material", {"object_name": object_name, "material_name": material_name})

@_tool
def bim_add_material_layer_set(ctx: Context, name: str, layers: list) -> str:
    """Create layered material. layers: [{\"material\": \"name\", \"thickness\": 0.1}, ...]."""
    return cmd("bim_add_material_layer_set", {"name": name, "layers": layers})

@_tool
def bim_add_material_profile_set(ctx: Context, name: str, profiles: list) -> str:
    """Create profile material for structural elements."""
    return cmd("bim_add_material_profile_set", {"name": name, "profiles": profiles})

@_tool
def bim_list_materials(ctx: Context) -> str:
    """List all IFC materials and material sets."""
    return cmd("bim_list_materials")


# ═══════════════════════════════════════════════════════════════════
# BIM: Types
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_create_type(ctx: Context, ifc_class: str, name: str = None,
                    predefined_type: str = None) -> str:
    """Create element type (e.g., IfcWallType, IfcSlabType)."""
    p = {"ifc_class": ifc_class}
    if name: p["name"] = name
    if predefined_type: p["predefined_type"] = predefined_type
    return cmd("bim_create_type", p)

@_tool
def bim_assign_type(ctx: Context, object_name: str, type_name: str) -> str:
    """Assign type to element occurrence."""
    return cmd("bim_assign_type", {"object_name": object_name, "type_name": type_name})

@_tool
def bim_list_types(ctx: Context, ifc_class: str = None) -> str:
    """List element types. Optional filter by class."""
    p = {}
    if ifc_class: p["ifc_class"] = ifc_class
    return cmd("bim_list_types", p)

@_tool
def bim_get_type_info(ctx: Context, name: str) -> str:
    """Get type details: material, geometry, properties."""
    return cmd("bim_get_type_info", {"name": name})


# ═══════════════════════════════════════════════════════════════════
# BIM: Geometry
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_add_opening(ctx: Context, element_name: str, location: list,
                    width: float, height: float, depth: float = 1.0) -> str:
    """Add void/opening to a wall or slab."""
    return cmd("bim_add_opening", {"element_name": element_name, "location": location,
                                    "width": width, "height": height, "depth": depth})

@_tool
def bim_add_filling(ctx: Context, opening_name: str, filling_name: str) -> str:
    """Fill opening with door/window element."""
    return cmd("bim_add_filling", {"opening_name": opening_name, "filling_name": filling_name})

@_tool
def bim_join_walls(ctx: Context, wall_names: list) -> str:
    """Join wall endpoints."""
    return cmd("bim_join_walls", {"wall_names": wall_names})

@_tool
def bim_align_element(ctx: Context, name: str, target_name: str, axis: str = "Z") -> str:
    """Align element to another on X, Y, or Z axis."""
    return cmd("bim_align_element", {"name": name, "target_name": target_name, "axis": axis})

@_tool
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

@_tool
def bim_add_classification(ctx: Context, source: str, name: str = None,
                            edition: str = None) -> str:
    """Add classification system (Uniclass, OmniClass, etc.)."""
    p = {"source": source}
    if name: p["name"] = name
    if edition: p["edition"] = edition
    return cmd("bim_add_classification", p)

@_tool
def bim_classify_element(ctx: Context, object_name: str, reference: str,
                          classification: str = None) -> str:
    """Assign classification reference to element."""
    p = {"object_name": object_name, "reference": reference}
    if classification: p["classification"] = classification
    return cmd("bim_classify_element", p)

@_tool
def bim_list_classifications(ctx: Context) -> str:
    """List active classification systems."""
    return cmd("bim_list_classifications")

@_tool
def bim_get_element_classifications(ctx: Context, object_name: str) -> str:
    """Get classifications assigned to element."""
    return cmd("bim_get_element_classifications", {"object_name": object_name})


# ═══════════════════════════════════════════════════════════════════
# BIM: Cost (5D)
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_add_cost_schedule(ctx: Context, name: str, predefined_type: str = "BUDGET") -> str:
    """Create cost schedule."""
    return cmd("bim_add_cost_schedule", {"name": name, "predefined_type": predefined_type})

@_tool
def bim_add_cost_item(ctx: Context, schedule_name: str, name: str,
                      quantity: float = None, unit_cost: float = None) -> str:
    """Add cost line item."""
    p = {"schedule_name": schedule_name, "name": name}
    if quantity is not None: p["quantity"] = quantity
    if unit_cost is not None: p["unit_cost"] = unit_cost
    return cmd("bim_add_cost_item", p)

@_tool
def bim_assign_cost_to_element(ctx: Context, cost_item_id: int, object_names: list) -> str:
    """Link cost items to building elements."""
    return cmd("bim_assign_cost_to_element", {"cost_item_id": cost_item_id, "object_names": object_names})

@_tool
def bim_calculate_costs(ctx: Context, schedule_name: str) -> str:
    """Calculate cost totals."""
    return cmd("bim_calculate_costs", {"schedule_name": schedule_name})

@_tool
def bim_export_cost_schedule(ctx: Context, schedule_name: str, filepath: str,
                              format: str = "CSV") -> str:
    """Export cost schedule: CSV, XLSX."""
    return cmd("bim_export_cost_schedule", {"schedule_name": schedule_name,
                                             "filepath": filepath, "format": format})


# ═══════════════════════════════════════════════════════════════════
# BIM: Schedule (4D)
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_add_work_schedule(ctx: Context, name: str) -> str:
    """Create work schedule."""
    return cmd("bim_add_work_schedule", {"name": name})

@_tool
def bim_add_task(ctx: Context, schedule_name: str, name: str, start: str = None,
                 finish: str = None, duration: str = None) -> str:
    """Add task to schedule. Dates: ISO format."""
    p = {"schedule_name": schedule_name, "name": name}
    for k, v in {"start": start, "finish": finish, "duration": duration}.items():
        if v: p[k] = v
    return cmd("bim_add_task", p)

@_tool
def bim_assign_task_to_element(ctx: Context, task_id: int, object_names: list) -> str:
    """Link tasks to building products."""
    return cmd("bim_assign_task_to_element", {"task_id": task_id, "object_names": object_names})

@_tool
def bim_add_task_sequence(ctx: Context, predecessor_id: int, successor_id: int,
                           type: str = "FINISH_START") -> str:
    """Add predecessor relationship."""
    return cmd("bim_add_task_sequence", {"predecessor_id": predecessor_id,
                                          "successor_id": successor_id, "type": type})

@_tool
def bim_calculate_schedule(ctx: Context, schedule_name: str) -> str:
    """Recalculate critical path."""
    return cmd("bim_calculate_schedule", {"schedule_name": schedule_name})

@_tool
def bim_get_schedule_info(ctx: Context, schedule_name: str) -> str:
    """Get tasks, durations, sequences."""
    return cmd("bim_get_schedule_info", {"schedule_name": schedule_name})


# ═══════════════════════════════════════════════════════════════════
# BIM: Clash Detection
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_create_clash_set(ctx: Context, name: str, group_a: list, group_b: list,
                          tolerance: float = 0.01) -> str:
    """Define clash detection between two groups of elements."""
    return cmd("bim_create_clash_set", {"name": name, "group_a": group_a,
                                         "group_b": group_b, "tolerance": tolerance})

@_tool
def bim_run_clash_detection(ctx: Context, clash_set_name: str = None) -> str:
    """Run clash detection."""
    p = {}
    if clash_set_name: p["clash_set_name"] = clash_set_name
    return cmd("bim_run_clash_detection", p)

@_tool
def bim_get_clash_results(ctx: Context, clash_set_name: str = None) -> str:
    """Get clash detection results."""
    p = {}
    if clash_set_name: p["clash_set_name"] = clash_set_name
    return cmd("bim_get_clash_results", p)

@_tool
def bim_select_clashing_elements(ctx: Context, clash_id: int = 0,
                                  clash_set_name: str = None) -> str:
    """Select clashing elements in viewport."""
    p = {"clash_id": clash_id}
    if clash_set_name: p["clash_set_name"] = clash_set_name
    return cmd("bim_select_clashing_elements", p)


# ═══════════════════════════════════════════════════════════════════
# BIM: Drawing
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_add_drawing(ctx: Context, name: str, type: str = "PLAN",
                    location: list = None) -> str:
    """Create drawing: PLAN, ELEVATION, SECTION, DETAIL, MODEL."""
    p = {"name": name, "type": type}
    if location: p["location"] = location
    return cmd("bim_add_drawing", p)

@_tool
def bim_add_sheet(ctx: Context, name: str, titleblock: str = None) -> str:
    """Create drawing sheet."""
    p = {"name": name}
    if titleblock: p["titleblock"] = titleblock
    return cmd("bim_add_sheet", p)

@_tool
def bim_add_drawing_to_sheet(ctx: Context, drawing_name: str, sheet_name: str) -> str:
    """Place drawing on sheet."""
    return cmd("bim_add_drawing_to_sheet", {"drawing_name": drawing_name, "sheet_name": sheet_name})

@_tool
def bim_add_annotation(ctx: Context, drawing_name: str, type: str,
                       text: str = None) -> str:
    """Add annotation: TEXT, DIMENSION, LEADER, STAIR_ARROW, etc."""
    p = {"drawing_name": drawing_name, "type": type}
    if text: p["text"] = text
    return cmd("bim_add_annotation", p)

@_tool
def bim_export_drawing(ctx: Context, sheet_name: str = None, filepath: str = None,
                       format: str = "PDF") -> str:
    """Export drawings: PDF, SVG."""
    p = {"format": format}
    if sheet_name: p["sheet_name"] = sheet_name
    if filepath: p["filepath"] = filepath
    return cmd("bim_export_drawing", p)


# ═══════════════════════════════════════════════════════════════════
# BIM: Systems (MEP)
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_add_system(ctx: Context, name: str,
                   ifc_class: str = "IfcDistributionSystem") -> str:
    """Create MEP system (HVAC, plumbing, electrical)."""
    return cmd("bim_add_system", {"name": name, "ifc_class": ifc_class})

@_tool
def bim_assign_to_system(ctx: Context, object_names: list, system_name: str) -> str:
    """Assign elements to system."""
    return cmd("bim_assign_to_system", {"object_names": object_names, "system_name": system_name})

@_tool
def bim_connect_ports(ctx: Context, element_a: str, element_b: str,
                      port_a: int = 0, port_b: int = 0) -> str:
    """Connect distribution element ports."""
    return cmd("bim_connect_ports", {"element_a": element_a, "element_b": element_b,
                                      "port_a": port_a, "port_b": port_b})

@_tool
def bim_list_systems(ctx: Context) -> str:
    """List all MEP systems."""
    return cmd("bim_list_systems")


# ═══════════════════════════════════════════════════════════════════
# BIM: Georeference
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_set_georeferencing(ctx: Context, crs: str, eastings: float = 0,
                            northings: float = 0, height: float = 0) -> str:
    """Set CRS and map conversion (EPSG code)."""
    return cmd("bim_set_georeferencing", {"crs": crs, "eastings": eastings,
                                           "northings": northings, "height": height})

@_tool
def bim_set_true_north(ctx: Context, angle: float) -> str:
    """Set true north angle (degrees from Y-axis)."""
    return cmd("bim_set_true_north", {"angle": angle})

@_tool
def bim_get_georeferencing(ctx: Context) -> str:
    """Get current georeferencing info."""
    return cmd("bim_get_georeferencing")


# ═══════════════════════════════════════════════════════════════════
# BIM: BCF Collaboration
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_create_bcf_project(ctx: Context, name: str) -> str:
    """Create BCF project for issue tracking."""
    return cmd("bim_create_bcf_project", {"name": name})

@_tool
def bim_add_bcf_topic(ctx: Context, title: str, description: str = None,
                      type: str = "Issue", priority: str = "Normal") -> str:
    """Add BCF issue/topic."""
    p = {"title": title, "type": type, "priority": priority}
    if description: p["description"] = description
    return cmd("bim_add_bcf_topic", p)

@_tool
def bim_add_bcf_viewpoint(ctx: Context, topic_id: int = 0) -> str:
    """Capture current viewport as BCF viewpoint."""
    return cmd("bim_add_bcf_viewpoint", {"topic_id": topic_id})

@_tool
def bim_list_bcf_topics(ctx: Context) -> str:
    """List all BCF topics."""
    return cmd("bim_list_bcf_topics")

@_tool
def bim_export_bcf(ctx: Context, filepath: str) -> str:
    """Export BCF file."""
    return cmd("bim_export_bcf", {"filepath": filepath})


# ═══════════════════════════════════════════════════════════════════
# BIM: Structural
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_add_structural_model(ctx: Context, name: str) -> str:
    """Create structural analysis model."""
    return cmd("bim_add_structural_model", {"name": name})

@_tool
def bim_add_structural_load(ctx: Context, name: str, load_type: str,
                             values: dict = None) -> str:
    """Add structural load."""
    p = {"name": name, "load_type": load_type}
    if values: p["values"] = values
    return cmd("bim_add_structural_load", p)

@_tool
def bim_add_load_case(ctx: Context, name: str, load_type: str = "DEAD_LOAD_G") -> str:
    """Create load case."""
    return cmd("bim_add_load_case", {"name": name, "load_type": load_type})

@_tool
def bim_add_boundary_condition(ctx: Context, element_name: str,
                                condition_type: str = "FIXED") -> str:
    """Add boundary condition: FIXED, PINNED."""
    return cmd("bim_add_boundary_condition", {"element_name": element_name,
                                               "condition_type": condition_type})


# ═══════════════════════════════════════════════════════════════════
# BIM: Validation
# ═══════════════════════════════════════════════════════════════════

@_tool
def bim_validate_ifc(ctx: Context, filepath: str = None) -> str:
    """Validate IFC file against schema rules."""
    p = {}
    if filepath: p["filepath"] = filepath
    return cmd("bim_validate_ifc", p)

@_tool
def bim_run_ids_check(ctx: Context, ids_filepath: str) -> str:
    """Run IDS (Information Delivery Specification) check."""
    return cmd("bim_run_ids_check", {"ids_filepath": ids_filepath})

@_tool
def bim_purge_unused(ctx: Context) -> str:
    """Purge unused IFC entities."""
    return cmd("bim_purge_unused")


# ═══════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════

def main():
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
