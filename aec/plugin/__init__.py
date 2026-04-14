"""
Blender MCP Plugin — AI control of Blender + Bonsai BIM via MCP.

Registers a non-blocking TCP socket server polled by bpy.app.timers,
with modular handler dispatch matching the QGIS MCP plugin architecture.
"""

bl_info = {
    "name": "Blender MCP",
    "author": "vicquick",
    "version": (2, 0, 0),
    "blender": (5, 1, 0),
    "location": "View3D > Sidebar > MCP",
    "description": "MCP socket server for AI control of Blender + Bonsai BIM (134 tools)",
    "category": "Interface",
}


def register():
    from .server import register as server_register
    server_register()


def unregister():
    from .server import unregister as server_unregister
    server_unregister()
