"""
Scene & system handlers — ping, blender info, scene info, object info, viewport screenshot.
"""

import bpy


def register(server):
    """Register scene handlers."""
    s = server

    def ping(**_):
        return {"pong": True}

    def get_blender_info(**_):
        return {
            "blender_version": ".".join(str(v) for v in bpy.app.version),
            "scene_name": bpy.context.scene.name,
            "render_engine": bpy.context.scene.render.engine,
            "object_count": len(bpy.data.objects),
            "material_count": len(bpy.data.materials),
            "collection_count": len(bpy.data.collections),
            "file_path": bpy.data.filepath or None,
            "addons": [a.module for a in bpy.context.preferences.addons],
        }

    def get_scene_info(limit: int = 20, **_):
        scene = bpy.context.scene
        objects_list = []
        for i, obj in enumerate(scene.objects):
            if i >= limit:
                break
            objects_list.append(s.object_to_dict(obj))

        collections_list = []
        for col in bpy.data.collections:
            collections_list.append({
                "name": col.name,
                "object_count": len(col.objects),
            })

        materials_list = []
        for mat in bpy.data.materials:
            materials_list.append({"name": mat.name, "users": mat.users})

        return {
            "scene_name": scene.name,
            "object_count": len(scene.objects),
            "objects": objects_list,
            "collection_count": len(bpy.data.collections),
            "collections": collections_list,
            "material_count": len(bpy.data.materials),
            "materials": materials_list,
            "frame_current": scene.frame_current,
            "frame_start": scene.frame_start,
            "frame_end": scene.frame_end,
            "render_engine": scene.render.engine,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        }

    def get_object_info(name: str, **_):
        obj = s.get_object_or_raise(name)
        info = s.object_to_dict(obj)
        # Materials
        info["materials"] = [slot.material.name if slot.material else None
                             for slot in obj.material_slots]
        # Modifiers
        info["modifiers"] = [{"name": m.name, "type": m.type} for m in obj.modifiers]
        # Constraints
        info["constraints"] = [{"name": c.name, "type": c.type} for c in obj.constraints]
        # Parent
        info["parent"] = obj.parent.name if obj.parent else None
        # Children
        info["children"] = [c.name for c in obj.children]
        # Collections
        info["collections"] = [c.name for c in obj.users_collection]
        # Bounding box
        if obj.bound_box:
            coords = [obj.matrix_world @ bpy.types.Object.bl_rna.properties["bound_box"].fixed_type.from_id(0)]
            # Simpler: just give local bbox
            bb = [list(v) for v in obj.bound_box]
            info["bounding_box"] = {
                "min": [min(v[i] for v in bb) for i in range(3)],
                "max": [max(v[i] for v in bb) for i in range(3)],
            }
        # Mesh data
        if obj.type == 'MESH' and obj.data:
            mesh = obj.data
            info["mesh"] = {
                "vertices": len(mesh.vertices),
                "edges": len(mesh.edges),
                "polygons": len(mesh.polygons),
                "uv_layers": [uv.name for uv in mesh.uv_layers],
            }
        # Light data
        if obj.type == 'LIGHT' and obj.data:
            light = obj.data
            info["light"] = {
                "type": light.type,
                "energy": light.energy,
                "color": list(light.color),
            }
        # Camera data
        if obj.type == 'CAMERA' and obj.data:
            cam = obj.data
            info["camera"] = {
                "type": cam.type,
                "focal_length": cam.lens,
                "sensor_width": cam.sensor_width,
                "clip_start": cam.clip_start,
                "clip_end": cam.clip_end,
            }
        return info

    def get_viewport_screenshot(filepath: str = "/tmp/viewport.png", max_size: int = 800, **_):
        # Find VIEW_3D area
        area = None
        for a in bpy.context.screen.areas:
            if a.type == 'VIEW_3D':
                area = a
                break
        if not area:
            raise RuntimeError("No 3D viewport found")

        # Use temp override to capture screenshot
        with bpy.context.temp_override(area=area):
            bpy.ops.screen.screenshot_area(filepath=filepath)

        # Resize if needed
        try:
            import os
            size = os.path.getsize(filepath)
        except Exception:
            size = 0

        return {
            "filepath": filepath,
            "file_size": size,
        }

    s._HANDLERS.update({
        "ping": ping,
        "get_blender_info": get_blender_info,
        "get_scene_info": get_scene_info,
        "get_object_info": get_object_info,
        "get_viewport_screenshot": get_viewport_screenshot,
    })
