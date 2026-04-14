"""
Animation handlers — keyframes, timeline, playback, interpolation.
"""

import bpy


def register(server):
    """Register animation handlers."""
    s = server

    def insert_keyframe(object_name: str, data_path: str, frame: int = None,
                        value=None, **_):
        obj = s.get_object_or_raise(object_name)
        if frame is not None:
            bpy.context.scene.frame_set(frame)
        if value is not None:
            # Set the value before inserting keyframe
            parts = data_path.split("[")
            if len(parts) == 2:
                attr = parts[0]
                idx = int(parts[1].rstrip("]"))
                getattr(obj, attr)[idx] = value
            else:
                setattr(obj, data_path, value)
        obj.keyframe_insert(data_path=data_path, frame=frame or bpy.context.scene.frame_current)
        return {
            "object": object_name,
            "data_path": data_path,
            "frame": frame or bpy.context.scene.frame_current,
        }

    def delete_keyframe(object_name: str, data_path: str, frame: int, **_):
        obj = s.get_object_or_raise(object_name)
        obj.keyframe_delete(data_path=data_path, frame=frame)
        return {"object": object_name, "data_path": data_path, "frame": frame}

    def set_frame(frame: int, **_):
        bpy.context.scene.frame_set(frame)
        return {"frame": frame}

    def set_frame_range(start: int, end: int, **_):
        scene = bpy.context.scene
        scene.frame_start = start
        scene.frame_end = end
        return {"frame_start": start, "frame_end": end}

    def get_keyframes(object_name: str, **_):
        obj = s.get_object_or_raise(object_name)
        if not obj.animation_data or not obj.animation_data.action:
            return {"object": object_name, "keyframes": [], "count": 0}
        keyframes = {}
        for fcurve in obj.animation_data.action.fcurves:
            path = fcurve.data_path
            idx = fcurve.array_index
            key = f"{path}[{idx}]" if idx > 0 else path
            frames = [{"frame": int(kp.co[0]), "value": round(kp.co[1], 4),
                       "interpolation": kp.interpolation}
                      for kp in fcurve.keyframe_points]
            keyframes[key] = frames
        return {"object": object_name, "keyframes": keyframes,
                "count": sum(len(v) for v in keyframes.values())}

    def set_interpolation(object_name: str, interpolation: str = "BEZIER", **_):
        obj = s.get_object_or_raise(object_name)
        interp = interpolation.upper()
        if interp not in ("BEZIER", "LINEAR", "CONSTANT"):
            raise RuntimeError(f"Unknown interpolation: {interpolation}. Use: BEZIER, LINEAR, CONSTANT")
        if not obj.animation_data or not obj.animation_data.action:
            raise RuntimeError(f"Object '{object_name}' has no animation data")
        count = 0
        for fcurve in obj.animation_data.action.fcurves:
            for kp in fcurve.keyframe_points:
                kp.interpolation = interp
                count += 1
        return {"object": object_name, "interpolation": interp, "keypoints_updated": count}

    s._HANDLERS.update({
        "insert_keyframe": insert_keyframe,
        "delete_keyframe": delete_keyframe,
        "set_frame": set_frame,
        "set_frame_range": set_frame_range,
        "get_keyframes": get_keyframes,
        "set_interpolation": set_interpolation,
    })
