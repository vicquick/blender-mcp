"""
UV handlers — smart UV project, unwrap, list UV maps.
"""

import bpy


def register(server):
    """Register UV handlers."""
    s = server

    def smart_uv_project(object_name: str, angle_limit: float = 66.0,
                         island_margin: float = 0.0, **_):
        obj = s.get_object_or_raise(object_name)
        if obj.type != 'MESH':
            raise RuntimeError(f"Object '{object_name}' is not a mesh")
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        import math
        bpy.ops.uv.smart_project(angle_limit=math.radians(angle_limit),
                                  island_margin=island_margin)
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"object": object_name, "uv_layers": [uv.name for uv in obj.data.uv_layers]}

    def uv_unwrap(object_name: str, method: str = "ANGLE_BASED", **_):
        obj = s.get_object_or_raise(object_name)
        if obj.type != 'MESH':
            raise RuntimeError(f"Object '{object_name}' is not a mesh")
        m = method.upper()
        if m not in ("ANGLE_BASED", "CONFORMAL"):
            raise RuntimeError(f"Unknown method: {method}. Use: ANGLE_BASED, CONFORMAL")
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.unwrap(method=m)
        bpy.ops.object.mode_set(mode='OBJECT')
        return {"object": object_name, "method": method}

    def list_uv_maps(object_name: str, **_):
        obj = s.get_object_or_raise(object_name)
        if obj.type != 'MESH':
            raise RuntimeError(f"Object '{object_name}' is not a mesh")
        maps = []
        for uv in obj.data.uv_layers:
            maps.append({"name": uv.name, "active": uv.active})
        return {"object": object_name, "uv_maps": maps}

    s._HANDLERS.update({
        "smart_uv_project": smart_uv_project,
        "uv_unwrap": uv_unwrap,
        "list_uv_maps": list_uv_maps,
    })
