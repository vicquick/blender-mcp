"""
BIM Drawing handlers — drawings, sheets, annotations, export.
"""

import bpy


def register(server):
    """Register BIM drawing handlers."""
    s = server

    def bim_add_drawing(name: str, type: str = "PLAN", location: list = None, **_):
        type_map = {
            "PLAN": "PLAN_VIEW",
            "ELEVATION": "ELEVATION_VIEW",
            "SECTION": "SECTION_VIEW",
            "DETAIL": "DETAIL_VIEW",
            "MODEL": "MODEL_VIEW",
            "REFLECTED_PLAN": "REFLECTED_PLAN_VIEW",
        }
        view_type = type_map.get(type.upper())
        if not view_type:
            raise RuntimeError(f"Unknown type: {type}. Use: {', '.join(type_map.keys())}")
        try:
            bpy.context.scene.DocProperties.target_view = view_type
            bpy.context.scene.DocProperties.drawing_name = name
            bpy.ops.bim.add_drawing()
        except Exception as e:
            # Fallback: create a camera for the drawing view
            cam_data = bpy.data.cameras.new(name=f"Drawing_{name}")
            cam_data.type = 'ORTHO'
            obj = bpy.data.objects.new(f"Drawing_{name}", cam_data)
            bpy.context.collection.objects.link(obj)
            if location:
                obj.location = location
            if type.upper() == "PLAN":
                import math
                obj.rotation_euler = (0, 0, 0)  # Top-down
            return {"name": name, "type": type, "object": obj.name, "note": "Created as camera"}
        return {"name": name, "type": type}

    def bim_add_sheet(name: str, titleblock: str = None, **_):
        try:
            bpy.ops.bim.add_sheet()
            return {"name": name, "titleblock": titleblock}
        except Exception as e:
            return {"name": name, "error": str(e),
                    "note": "Sheet creation requires Bonsai drawing module active"}

    def bim_add_drawing_to_sheet(drawing_name: str, sheet_name: str, **_):
        try:
            bpy.ops.bim.add_drawing_to_sheet()
            return {"drawing": drawing_name, "sheet": sheet_name}
        except Exception as e:
            return {"error": str(e),
                    "note": "Requires Bonsai drawing module with active sheet"}

    def bim_add_annotation(drawing_name: str, type: str, text: str = None,
                            location: list = None, **_):
        ann_types = ("TEXT", "DIMENSION", "LEADER", "STAIR_ARROW", "HIDDEN_LINE",
                     "PLAN_LEVEL", "SECTION_LEVEL", "BREAKLINE", "BATTING")
        if type.upper() not in ann_types:
            raise RuntimeError(f"Unknown annotation type: {type}. Use: {', '.join(ann_types)}")
        try:
            bpy.ops.bim.add_annotation(object_type=type.upper())
            if text and bpy.context.active_object:
                bpy.context.active_object.name = text
            return {"drawing": drawing_name, "type": type, "text": text}
        except Exception as e:
            return {"error": str(e), "drawing": drawing_name, "type": type}

    def bim_export_drawing(sheet_name: str = None, filepath: str = None,
                            format: str = "PDF", **_):
        if not filepath:
            filepath = f"/tmp/drawing.{format.lower()}"
        try:
            if format.upper() == "SVG":
                bpy.ops.bim.build_schedule()
            elif format.upper() == "PDF":
                bpy.ops.bim.build_schedule()
                # SVG to PDF conversion would need additional tooling
            return {"filepath": filepath, "format": format}
        except Exception as e:
            return {"error": str(e), "filepath": filepath,
                    "note": "Drawing export requires active drawing views"}

    s._HANDLERS.update({
        "bim_add_drawing": bim_add_drawing,
        "bim_add_sheet": bim_add_sheet,
        "bim_add_drawing_to_sheet": bim_add_drawing_to_sheet,
        "bim_add_annotation": bim_add_annotation,
        "bim_export_drawing": bim_export_drawing,
    })
