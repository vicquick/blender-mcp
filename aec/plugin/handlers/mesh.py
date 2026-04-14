"""
Mesh & modifier handlers — add/remove/apply modifiers, boolean ops, mesh data, shading.
"""

import bpy


def register(server):
    """Register mesh handlers."""
    s = server

    def add_modifier(object_name: str, modifier_type: str, name: str = None,
                     settings: dict = None, **_):
        obj = s.get_object_or_raise(object_name)
        mod = obj.modifiers.new(name=name or modifier_type, type=modifier_type.upper())
        if settings:
            for key, val in settings.items():
                if hasattr(mod, key):
                    setattr(mod, key, val)
        return {"object": object_name, "modifier": mod.name, "type": mod.type}

    def remove_modifier(object_name: str, modifier_name: str, **_):
        obj = s.get_object_or_raise(object_name)
        mod = obj.modifiers.get(modifier_name)
        if not mod:
            raise RuntimeError(f"Modifier not found: {modifier_name}")
        obj.modifiers.remove(mod)
        return {"object": object_name, "removed": modifier_name}

    def apply_modifier(object_name: str, modifier_name: str, **_):
        obj = s.get_object_or_raise(object_name)
        mod = obj.modifiers.get(modifier_name)
        if not mod:
            raise RuntimeError(f"Modifier not found: {modifier_name}")
        bpy.context.view_layer.objects.active = obj
        with bpy.context.temp_override(active_object=obj, object=obj):
            bpy.ops.object.modifier_apply(modifier=modifier_name)
        return {"object": object_name, "applied": modifier_name}

    def list_modifiers(object_name: str, **_):
        obj = s.get_object_or_raise(object_name)
        mods = []
        for m in obj.modifiers:
            info = {"name": m.name, "type": m.type, "show_viewport": m.show_viewport}
            # Common properties
            if hasattr(m, 'levels'):
                info["levels"] = m.levels
            if hasattr(m, 'count'):
                info["count"] = m.count
            mods.append(info)
        return {"object": object_name, "modifiers": mods}

    def set_modifier_property(object_name: str, modifier_name: str,
                              property_name: str, value=None, **_):
        obj = s.get_object_or_raise(object_name)
        mod = obj.modifiers.get(modifier_name)
        if not mod:
            raise RuntimeError(f"Modifier not found: {modifier_name}")
        if not hasattr(mod, property_name):
            raise RuntimeError(f"Modifier '{modifier_name}' has no property '{property_name}'")
        setattr(mod, property_name, value)
        return {"object": object_name, "modifier": modifier_name,
                "property": property_name, "value": value}

    def boolean_operation(object_name: str, target_name: str,
                          operation: str = "DIFFERENCE", **_):
        obj = s.get_object_or_raise(object_name)
        target = s.get_object_or_raise(target_name)
        op = operation.upper()
        if op not in ("DIFFERENCE", "UNION", "INTERSECT"):
            raise RuntimeError(f"Unknown operation: {operation}. Use: DIFFERENCE, UNION, INTERSECT")
        mod = obj.modifiers.new(name=f"Boolean_{target_name}", type='BOOLEAN')
        mod.operation = op
        mod.object = target
        # Apply immediately
        bpy.context.view_layer.objects.active = obj
        with bpy.context.temp_override(active_object=obj, object=obj):
            bpy.ops.object.modifier_apply(modifier=mod.name)
        return {"object": object_name, "target": target_name, "operation": op}

    def get_mesh_data(object_name: str, **_):
        obj = s.get_object_or_raise(object_name)
        if obj.type != 'MESH':
            raise RuntimeError(f"Object '{object_name}' is not a mesh (type: {obj.type})")
        mesh = obj.data
        bb = [list(v) for v in obj.bound_box]
        return {
            "name": mesh.name,
            "vertices": len(mesh.vertices),
            "edges": len(mesh.edges),
            "polygons": len(mesh.polygons),
            "uv_layers": [uv.name for uv in mesh.uv_layers],
            "material_count": len(mesh.materials),
            "has_custom_normals": mesh.has_custom_normals,
            "bounding_box": {
                "min": [min(v[i] for v in bb) for i in range(3)],
                "max": [max(v[i] for v in bb) for i in range(3)],
            },
        }

    def set_smooth_shading(object_name: str, smooth: bool = True, **_):
        obj = s.get_object_or_raise(object_name)
        if obj.type != 'MESH':
            raise RuntimeError(f"Object '{object_name}' is not a mesh")
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        with bpy.context.temp_override(active_object=obj, object=obj):
            if smooth:
                bpy.ops.object.shade_smooth()
            else:
                bpy.ops.object.shade_flat()
        return {"object": object_name, "smooth": smooth}

    s._HANDLERS.update({
        "add_modifier": add_modifier,
        "remove_modifier": remove_modifier,
        "apply_modifier": apply_modifier,
        "list_modifiers": list_modifiers,
        "set_modifier_property": set_modifier_property,
        "boolean_operation": boolean_operation,
        "get_mesh_data": get_mesh_data,
        "set_smooth_shading": set_smooth_shading,
    })
