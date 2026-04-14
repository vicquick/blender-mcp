"""
File operation handlers — save, open, export, import, new file.
"""

import bpy
import os


def register(server):
    """Register file operation handlers."""
    s = server

    def save_file(filepath: str = None, **_):
        if filepath:
            bpy.ops.wm.save_as_mainfile(filepath=filepath)
        else:
            if not bpy.data.filepath:
                raise RuntimeError("No file path set. Provide a filepath parameter.")
            bpy.ops.wm.save_mainfile()
        return {"saved": bpy.data.filepath}

    def open_file(filepath: str, **_):
        if not os.path.exists(filepath):
            raise RuntimeError(f"File not found: {filepath}")
        bpy.ops.wm.open_mainfile(filepath=filepath)
        return {"opened": filepath, "object_count": len(bpy.data.objects)}

    def export_file(filepath: str, format: str = "GLTF", selected_only: bool = False, **_):
        fmt = format.upper()
        export_map = {
            "GLTF": lambda: bpy.ops.export_scene.gltf(
                filepath=filepath, use_selection=selected_only, export_format='GLTF_SEPARATE'),
            "GLB": lambda: bpy.ops.export_scene.gltf(
                filepath=filepath, use_selection=selected_only, export_format='GLB'),
            "FBX": lambda: bpy.ops.export_scene.fbx(
                filepath=filepath, use_selection=selected_only),
            "OBJ": lambda: bpy.ops.wm.obj_export(
                filepath=filepath, export_selected_objects=selected_only),
            "STL": lambda: bpy.ops.wm.stl_export(
                filepath=filepath, export_selected_objects=selected_only),
            "USD": lambda: bpy.ops.wm.usd_export(
                filepath=filepath, selected_objects_only=selected_only),
            "PLY": lambda: bpy.ops.wm.ply_export(
                filepath=filepath, export_selected_objects=selected_only),
        }
        if fmt not in export_map:
            raise RuntimeError(f"Unknown format: {format}. Use: {', '.join(export_map.keys())}")
        export_map[fmt]()
        size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
        return {"filepath": filepath, "format": fmt, "file_size": size}

    def import_file(filepath: str, format: str = None, **_):
        if not os.path.exists(filepath):
            raise RuntimeError(f"File not found: {filepath}")
        ext = os.path.splitext(filepath)[1].lower()
        if format:
            ext = f".{format.lower()}"
        import_map = {
            ".gltf": lambda: bpy.ops.import_scene.gltf(filepath=filepath),
            ".glb": lambda: bpy.ops.import_scene.gltf(filepath=filepath),
            ".fbx": lambda: bpy.ops.import_scene.fbx(filepath=filepath),
            ".obj": lambda: bpy.ops.wm.obj_import(filepath=filepath),
            ".stl": lambda: bpy.ops.wm.stl_import(filepath=filepath),
            ".usd": lambda: bpy.ops.wm.usd_import(filepath=filepath),
            ".usdc": lambda: bpy.ops.wm.usd_import(filepath=filepath),
            ".usda": lambda: bpy.ops.wm.usd_import(filepath=filepath),
            ".ply": lambda: bpy.ops.wm.ply_import(filepath=filepath),
            ".ifc": lambda: _import_ifc(filepath),
        }
        if ext not in import_map:
            raise RuntimeError(f"Unknown file extension: {ext}. Supported: {', '.join(import_map.keys())}")
        import_map[ext]()
        return {"imported": filepath, "object_count": len(bpy.data.objects)}

    def _import_ifc(filepath):
        try:
            bpy.ops.bim.load_project(filepath=filepath)
        except Exception:
            raise RuntimeError("IFC import requires the Bonsai BIM extension")

    def new_file(**_):
        bpy.ops.wm.read_homefile(use_empty=True)
        return {"new_file": True, "object_count": len(bpy.data.objects)}

    s._HANDLERS.update({
        "save_file": save_file,
        "open_file": open_file,
        "export_file": export_file,
        "import_file": import_file,
        "new_file": new_file,
    })
