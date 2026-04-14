"""
Camera handlers — create, set active, edit, DOF, look-at.
"""

import bpy
import math
from mathutils import Vector, Matrix


def register(server):
    """Register camera handlers."""
    s = server

    def create_camera(name: str = None, location: list = None,
                      rotation: list = None, focal_length: float = 50, **_):
        cam_data = bpy.data.cameras.new(name=name or "Camera")
        cam_data.lens = focal_length
        obj = bpy.data.objects.new(cam_data.name, cam_data)
        bpy.context.collection.objects.link(obj)
        if location:
            obj.location = location
        if rotation:
            obj.rotation_euler = [math.radians(r) if abs(r) > 2 * math.pi else r for r in rotation]
        return s.object_to_dict(obj)

    def set_active_camera(name: str, **_):
        obj = s.get_object_or_raise(name)
        if obj.type != 'CAMERA':
            raise RuntimeError(f"Object '{name}' is not a camera (type: {obj.type})")
        bpy.context.scene.camera = obj
        return {"active_camera": obj.name}

    def edit_camera(name: str, focal_length: float = None, sensor_width: float = None,
                    clip_start: float = None, clip_end: float = None,
                    type: str = None, **_):
        obj = s.get_object_or_raise(name)
        if obj.type != 'CAMERA':
            raise RuntimeError(f"Object '{name}' is not a camera")
        cam = obj.data
        if focal_length is not None:
            cam.lens = focal_length
        if sensor_width is not None:
            cam.sensor_width = sensor_width
        if clip_start is not None:
            cam.clip_start = clip_start
        if clip_end is not None:
            cam.clip_end = clip_end
        if type is not None:
            cam.type = type.upper()
        return {
            "name": name,
            "focal_length": cam.lens,
            "sensor_width": cam.sensor_width,
            "clip_start": cam.clip_start,
            "clip_end": cam.clip_end,
            "type": cam.type,
        }

    def set_camera_dof(name: str, enabled: bool = True, focus_object: str = None,
                       focus_distance: float = None, f_stop: float = 2.8, **_):
        obj = s.get_object_or_raise(name)
        if obj.type != 'CAMERA':
            raise RuntimeError(f"Object '{name}' is not a camera")
        cam = obj.data
        cam.dof.use_dof = enabled
        if focus_object:
            fo = bpy.data.objects.get(focus_object)
            if fo:
                cam.dof.focus_object = fo
        if focus_distance is not None:
            cam.dof.focus_distance = focus_distance
        cam.dof.aperture_fstop = f_stop
        return {
            "name": name,
            "dof_enabled": cam.dof.use_dof,
            "focus_object": cam.dof.focus_object.name if cam.dof.focus_object else None,
            "focus_distance": cam.dof.focus_distance,
            "f_stop": cam.dof.aperture_fstop,
        }

    def look_at(camera_name: str, target: list, **_):
        obj = s.get_object_or_raise(camera_name)
        if obj.type != 'CAMERA':
            raise RuntimeError(f"Object '{camera_name}' is not a camera")
        target_vec = Vector(target)
        direction = target_vec - obj.location
        rot_quat = direction.to_track_quat('-Z', 'Y')
        obj.rotation_euler = rot_quat.to_euler()
        return {
            "camera": camera_name,
            "target": target,
            "rotation": [round(math.degrees(r), 2) for r in obj.rotation_euler],
        }

    s._HANDLERS.update({
        "create_camera": create_camera,
        "set_active_camera": set_active_camera,
        "edit_camera": edit_camera,
        "set_camera_dof": set_camera_dof,
        "look_at": look_at,
    })
