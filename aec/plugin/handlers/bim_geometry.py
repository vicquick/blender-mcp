"""
BIM Geometry handlers — placement, openings, fillings, wall joins, alignment.
"""

import bpy


def register(server):
    """Register BIM geometry handlers."""
    s = server

    def bim_add_opening(element_name: str, location: list, width: float,
                        height: float, depth: float = 1.0, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        obj = s.get_object_or_raise(element_name)
        element = s.get_ifc_element(obj)

        opening = ifcopenshell.api.run("root.create_entity", ifc_file,
                                        ifc_class="IfcOpeningElement", name=f"Opening_{element_name}")
        # Create opening geometry
        hw, hd = width / 2, depth / 2
        verts = [
            (-hw, -hd, 0), (hw, -hd, 0), (hw, hd, 0), (-hw, hd, 0),
            (-hw, -hd, height), (hw, -hd, height), (hw, hd, height), (-hw, hd, height),
        ]
        faces = [(0,1,2,3), (4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]
        mesh = bpy.data.meshes.new("Opening")
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        op_obj = bpy.data.objects.new("Opening", mesh)
        bpy.context.collection.objects.link(op_obj)
        op_obj.location = location

        import bonsai.tool as tool
        tool.Ifc.link(opening, op_obj)

        ifcopenshell.api.run("void.add_opening", ifc_file,
                              opening=opening, element=element)
        return {"element": element_name, "opening_id": opening.id()}

    def bim_add_filling(opening_name: str, filling_name: str, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        op_obj = s.get_object_or_raise(opening_name)
        fill_obj = s.get_object_or_raise(filling_name)
        opening = s.get_ifc_element(op_obj)
        filling = s.get_ifc_element(fill_obj)
        ifcopenshell.api.run("void.add_filling", ifc_file,
                              opening=opening, element=filling)
        return {"opening": opening_name, "filling": filling_name}

    def bim_join_walls(wall_names: list, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        if len(wall_names) < 2:
            raise RuntimeError("Need at least 2 wall names to join")
        walls = []
        for name in wall_names:
            obj = s.get_object_or_raise(name)
            walls.append(s.get_ifc_element(obj))
        for i in range(len(walls) - 1):
            try:
                ifcopenshell.api.run("geometry.connect_wall", ifc_file,
                                      wall1=walls[i], wall2=walls[i + 1])
            except Exception as e:
                print(f"[MCP] Wall join warning: {e}")
        return {"joined": wall_names}

    def bim_align_element(name: str, target_name: str, axis: str = "Z", **_):
        obj = s.get_object_or_raise(name)
        target = s.get_object_or_raise(target_name)
        ax = axis.upper()
        idx = {"X": 0, "Y": 1, "Z": 2}.get(ax)
        if idx is None:
            raise RuntimeError(f"Invalid axis: {axis}. Use: X, Y, Z")
        obj.location[idx] = target.location[idx]
        return {"name": name, "target": target_name, "axis": ax,
                "new_position": round(obj.location[idx], 4)}

    def bim_edit_placement(name: str, location: list = None, rotation: list = None, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        obj = s.get_object_or_raise(name)
        element = s.get_ifc_element(obj)
        if location is not None:
            obj.location = location
        if rotation is not None:
            import math
            obj.rotation_euler = [math.radians(r) if abs(r) > 2 * math.pi else r
                                  for r in rotation]
        # Sync placement to IFC
        try:
            import mathutils
            ifcopenshell.api.run("geometry.edit_object_placement", ifc_file,
                                  product=element, matrix=obj.matrix_world)
        except Exception:
            pass  # Some elements may not support this
        return {"name": name, "location": [round(v, 4) for v in obj.location]}

    s._HANDLERS.update({
        "bim_add_opening": bim_add_opening,
        "bim_add_filling": bim_add_filling,
        "bim_join_walls": bim_join_walls,
        "bim_align_element": bim_align_element,
        "bim_edit_placement": bim_edit_placement,
    })
