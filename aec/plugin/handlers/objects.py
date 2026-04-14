"""
Object management handlers — create, delete, duplicate, select, transform, parent.
"""

import bpy
import math


def register(server):
    """Register object handlers."""
    s = server

    _MESH_OPS = {
        "cube": lambda: bpy.ops.mesh.primitive_cube_add(),
        "sphere": lambda: bpy.ops.mesh.primitive_uv_sphere_add(),
        "cylinder": lambda: bpy.ops.mesh.primitive_cylinder_add(),
        "cone": lambda: bpy.ops.mesh.primitive_cone_add(),
        "torus": lambda: bpy.ops.mesh.primitive_torus_add(),
        "plane": lambda: bpy.ops.mesh.primitive_plane_add(),
        "circle": lambda: bpy.ops.mesh.primitive_circle_add(),
        "monkey": lambda: bpy.ops.mesh.primitive_monkey_add(),
        "ico_sphere": lambda: bpy.ops.mesh.primitive_ico_sphere_add(),
        "grid": lambda: bpy.ops.mesh.primitive_grid_add(),
    }

    def create_object(type: str = "cube", name: str = None,
                      location: list = None, rotation: list = None,
                      scale: list = None, **_):
        t = type.lower()
        if t == "empty":
            bpy.ops.object.empty_add(type='PLAIN_AXES')
        elif t == "curve":
            bpy.ops.curve.primitive_bezier_curve_add()
        elif t == "text":
            bpy.ops.object.text_add()
        elif t in _MESH_OPS:
            _MESH_OPS[t]()
        else:
            avail = list(_MESH_OPS.keys()) + ["empty", "curve", "text"]
            raise RuntimeError(f"Unknown object type: {type}. Available: {', '.join(avail)}")

        obj = bpy.context.active_object
        if name:
            obj.name = name
        if location:
            obj.location = location
        if rotation:
            obj.rotation_euler = [math.radians(r) if abs(r) > 2 * math.pi else r for r in rotation]
        if scale:
            obj.scale = scale
        return s.object_to_dict(obj)

    def delete_objects(names: list, **_):
        deleted = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj:
                bpy.data.objects.remove(obj, do_unlink=True)
                deleted.append(name)
        return {"deleted": deleted, "count": len(deleted)}

    def duplicate_object(name: str, linked: bool = False, **_):
        obj = s.get_object_or_raise(name)
        if linked:
            new_obj = obj.copy()
        else:
            new_obj = obj.copy()
            if obj.data:
                new_obj.data = obj.data.copy()
        for col in obj.users_collection:
            col.objects.link(new_obj)
        return s.object_to_dict(new_obj)

    def select_objects(names: list, deselect_others: bool = True, **_):
        if deselect_others:
            bpy.ops.object.select_all(action='DESELECT')
        selected = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj:
                obj.select_set(True)
                selected.append(name)
        return {"selected": selected}

    def set_active_object(name: str, **_):
        obj = s.get_object_or_raise(name)
        bpy.context.view_layer.objects.active = obj
        return {"active": obj.name}

    def transform_object(name: str, location: list = None,
                         rotation: list = None, scale: list = None, **_):
        obj = s.get_object_or_raise(name)
        if location is not None:
            obj.location = location
        if rotation is not None:
            obj.rotation_euler = [math.radians(r) if abs(r) > 2 * math.pi else r for r in rotation]
        if scale is not None:
            obj.scale = scale
        return s.object_to_dict(obj)

    def set_parent(child_names: list, parent_name: str, **_):
        parent = s.get_object_or_raise(parent_name)
        parented = []
        for name in child_names:
            child = bpy.data.objects.get(name)
            if child:
                child.parent = parent
                parented.append(name)
        return {"parent": parent_name, "children": parented}

    def clear_parent(names: list, keep_transform: bool = True, **_):
        cleared = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj and obj.parent:
                if keep_transform:
                    mat = obj.matrix_world.copy()
                obj.parent = None
                if keep_transform:
                    obj.matrix_world = mat
                cleared.append(name)
        return {"cleared": cleared}

    def rename_object(name: str, new_name: str, **_):
        obj = s.get_object_or_raise(name)
        obj.name = new_name
        return {"old_name": name, "new_name": obj.name}

    def list_objects(type_filter: str = None, **_):
        objects = []
        for obj in bpy.data.objects:
            if type_filter and obj.type != type_filter.upper():
                continue
            objects.append({
                "name": obj.name,
                "type": obj.type,
                "location": [round(v, 4) for v in obj.location],
                "visible": obj.visible_get(),
            })
        return {"objects": objects, "count": len(objects)}

    s._HANDLERS.update({
        "create_object": create_object,
        "delete_objects": delete_objects,
        "duplicate_object": duplicate_object,
        "select_objects": select_objects,
        "set_active_object": set_active_object,
        "transform_object": transform_object,
        "set_parent": set_parent,
        "clear_parent": clear_parent,
        "rename_object": rename_object,
        "list_objects": list_objects,
    })
