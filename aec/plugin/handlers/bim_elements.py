"""
BIM Element handlers — wall, slab, column, beam, door, window, stair, remove.
"""

import bpy


def register(server):
    """Register BIM element handlers."""
    s = server

    def bim_add_wall(coords: list, height: float = 3.0, thickness: float = 0.2,
                     name: str = None, **_):
        """Create a wall. coords: [[x1,y1,z1], [x2,y2,z2]] for a simple wall."""
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        import mathutils

        if len(coords) < 2:
            raise RuntimeError("coords must have at least 2 points: [[x1,y1,z1], [x2,y2,z2]]")

        # Create wall entity
        wall = ifcopenshell.api.run("root.create_entity", ifc_file,
                                     ifc_class="IfcWall", name=name or "Wall")

        # Create mesh in Blender
        p1 = mathutils.Vector(coords[0][:3])
        p2 = mathutils.Vector(coords[1][:3])
        direction = (p2 - p1).normalized()
        length = (p2 - p1).length
        # Perpendicular for thickness
        perp = mathutils.Vector((-direction.y, direction.x, 0)) * (thickness / 2)

        verts = [
            p1 - perp, p1 + perp,
            p2 + perp, p2 - perp,
            p1 - perp + mathutils.Vector((0, 0, height)),
            p1 + perp + mathutils.Vector((0, 0, height)),
            p2 + perp + mathutils.Vector((0, 0, height)),
            p2 - perp + mathutils.Vector((0, 0, height)),
        ]
        faces = [
            (0, 1, 2, 3), (4, 5, 6, 7),  # bottom, top
            (0, 1, 5, 4), (2, 3, 7, 6),  # sides
            (0, 3, 7, 4), (1, 2, 6, 5),  # front, back
        ]

        mesh = bpy.data.meshes.new(wall.Name or "Wall")
        mesh.from_pydata([list(v) for v in verts], [], faces)
        mesh.update()

        obj = bpy.data.objects.new(wall.Name or "Wall", mesh)
        bpy.context.collection.objects.link(obj)

        # Link to IFC
        import bonsai.tool as tool
        tool.Ifc.link(wall, obj)

        return {
            "id": wall.id(),
            "name": wall.Name,
            "global_id": wall.GlobalId,
            "object": obj.name,
            "length": round(length, 4),
            "height": height,
            "thickness": thickness,
        }

    def bim_add_slab(coords: list, thickness: float = 0.2, name: str = None, **_):
        """Create a slab. coords: [[x1,y1], [x2,y2], [x3,y3], ...] outline points."""
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api

        if len(coords) < 3:
            raise RuntimeError("coords must have at least 3 points for the slab outline")

        slab = ifcopenshell.api.run("root.create_entity", ifc_file,
                                     ifc_class="IfcSlab", name=name or "Slab")

        # Create mesh
        verts_bottom = [list(c[:2]) + [c[2] if len(c) > 2 else 0] for c in coords]
        verts_top = [list(c[:2]) + [(c[2] if len(c) > 2 else 0) + thickness] for c in coords]
        verts = verts_bottom + verts_top
        n = len(coords)
        faces = [list(range(n)), list(range(2 * n - 1, n - 1, -1))]  # bottom, top
        for i in range(n):
            j = (i + 1) % n
            faces.append([i, j, j + n, i + n])  # sides

        mesh = bpy.data.meshes.new(slab.Name or "Slab")
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        obj = bpy.data.objects.new(slab.Name or "Slab", mesh)
        bpy.context.collection.objects.link(obj)

        import bonsai.tool as tool
        tool.Ifc.link(slab, obj)

        return {
            "id": slab.id(),
            "name": slab.Name,
            "global_id": slab.GlobalId,
            "object": obj.name,
        }

    def bim_add_column(location: list, height: float = 3.0, width: float = 0.3,
                       depth: float = 0.3, profile: str = None,
                       name: str = None, **_):
        """Create a column at location with given dimensions."""
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api

        column = ifcopenshell.api.run("root.create_entity", ifc_file,
                                       ifc_class="IfcColumn", name=name or "Column")

        # Create rectangular column mesh
        hw, hd = width / 2, depth / 2
        x, y, z = location[0], location[1], location[2] if len(location) > 2 else 0
        verts = [
            (x - hw, y - hd, z), (x + hw, y - hd, z),
            (x + hw, y + hd, z), (x - hw, y + hd, z),
            (x - hw, y - hd, z + height), (x + hw, y - hd, z + height),
            (x + hw, y + hd, z + height), (x - hw, y + hd, z + height),
        ]
        faces = [
            (0, 1, 2, 3), (4, 5, 6, 7),
            (0, 1, 5, 4), (1, 2, 6, 5),
            (2, 3, 7, 6), (3, 0, 4, 7),
        ]

        mesh = bpy.data.meshes.new(column.Name or "Column")
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        obj = bpy.data.objects.new(column.Name or "Column", mesh)
        bpy.context.collection.objects.link(obj)

        import bonsai.tool as tool
        tool.Ifc.link(column, obj)

        return {
            "id": column.id(),
            "name": column.Name,
            "global_id": column.GlobalId,
            "object": obj.name,
        }

    def bim_add_beam(start: list, end: list, width: float = 0.2,
                     depth: float = 0.4, profile: str = None,
                     name: str = None, **_):
        """Create a beam between two points."""
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        import mathutils

        beam = ifcopenshell.api.run("root.create_entity", ifc_file,
                                     ifc_class="IfcBeam", name=name or "Beam")

        p1 = mathutils.Vector(start[:3])
        p2 = mathutils.Vector(end[:3])
        direction = (p2 - p1).normalized()
        length = (p2 - p1).length

        # Create beam along X axis then orient
        hw, hd = width / 2, depth / 2
        verts = [
            (0, -hw, -hd), (length, -hw, -hd),
            (length, hw, -hd), (0, hw, -hd),
            (0, -hw, hd), (length, -hw, hd),
            (length, hw, hd), (0, hw, hd),
        ]
        faces = [
            (0, 1, 2, 3), (4, 5, 6, 7),
            (0, 1, 5, 4), (1, 2, 6, 5),
            (2, 3, 7, 6), (3, 0, 4, 7),
        ]

        mesh = bpy.data.meshes.new(beam.Name or "Beam")
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        obj = bpy.data.objects.new(beam.Name or "Beam", mesh)
        bpy.context.collection.objects.link(obj)
        obj.location = p1

        # Orient beam towards end point
        rot = direction.to_track_quat('X', 'Z')
        obj.rotation_euler = rot.to_euler()

        import bonsai.tool as tool
        tool.Ifc.link(beam, obj)

        return {
            "id": beam.id(),
            "name": beam.Name,
            "global_id": beam.GlobalId,
            "object": obj.name,
            "length": round(length, 4),
        }

    def bim_add_door(wall_name: str, width: float = 0.9, height: float = 2.1,
                     location: float = None, name: str = None, **_):
        """Add a door to a wall. location is distance along wall from start."""
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api

        door = ifcopenshell.api.run("root.create_entity", ifc_file,
                                     ifc_class="IfcDoor", name=name or "Door")
        if hasattr(door, 'OverallWidth'):
            door.OverallWidth = width
        if hasattr(door, 'OverallHeight'):
            door.OverallHeight = height

        # Create simple door mesh
        hw = width / 2
        verts = [
            (-hw, 0, 0), (hw, 0, 0),
            (hw, 0.05, 0), (-hw, 0.05, 0),
            (-hw, 0, height), (hw, 0, height),
            (hw, 0.05, height), (-hw, 0.05, height),
        ]
        faces = [
            (0, 1, 2, 3), (4, 5, 6, 7),
            (0, 1, 5, 4), (1, 2, 6, 5),
            (2, 3, 7, 6), (3, 0, 4, 7),
        ]

        mesh = bpy.data.meshes.new(door.Name or "Door")
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        obj = bpy.data.objects.new(door.Name or "Door", mesh)
        bpy.context.collection.objects.link(obj)

        # Position relative to wall if wall exists
        wall_obj = bpy.data.objects.get(wall_name)
        if wall_obj and location is not None:
            obj.location = wall_obj.location
            obj.location.x += location

        import bonsai.tool as tool
        tool.Ifc.link(door, obj)

        return {
            "id": door.id(),
            "name": door.Name,
            "global_id": door.GlobalId,
            "object": obj.name,
            "width": width,
            "height": height,
        }

    def bim_add_window(wall_name: str, width: float = 1.2, height: float = 1.5,
                       sill_height: float = 0.9, location: float = None,
                       name: str = None, **_):
        """Add a window to a wall."""
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api

        window = ifcopenshell.api.run("root.create_entity", ifc_file,
                                       ifc_class="IfcWindow", name=name or "Window")
        if hasattr(window, 'OverallWidth'):
            window.OverallWidth = width
        if hasattr(window, 'OverallHeight'):
            window.OverallHeight = height

        hw = width / 2
        verts = [
            (-hw, 0, sill_height), (hw, 0, sill_height),
            (hw, 0.05, sill_height), (-hw, 0.05, sill_height),
            (-hw, 0, sill_height + height), (hw, 0, sill_height + height),
            (hw, 0.05, sill_height + height), (-hw, 0.05, sill_height + height),
        ]
        faces = [
            (0, 1, 2, 3), (4, 5, 6, 7),
            (0, 1, 5, 4), (1, 2, 6, 5),
            (2, 3, 7, 6), (3, 0, 4, 7),
        ]

        mesh = bpy.data.meshes.new(window.Name or "Window")
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        obj = bpy.data.objects.new(window.Name or "Window", mesh)
        bpy.context.collection.objects.link(obj)

        wall_obj = bpy.data.objects.get(wall_name)
        if wall_obj and location is not None:
            obj.location = wall_obj.location
            obj.location.x += location

        import bonsai.tool as tool
        tool.Ifc.link(window, obj)

        return {
            "id": window.id(),
            "name": window.Name,
            "global_id": window.GlobalId,
            "object": obj.name,
        }

    def bim_add_stair(location: list = None, width: float = 1.2, height: float = 3.0,
                      treads: int = 16, depth: float = 0.25, name: str = None, **_):
        """Create a simple straight stair."""
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api

        stair = ifcopenshell.api.run("root.create_entity", ifc_file,
                                      ifc_class="IfcStair", name=name or "Stair")

        riser_height = height / treads
        verts = []
        faces = []
        for i in range(treads):
            x0, x1 = i * depth, (i + 1) * depth
            z0, z1 = i * riser_height, (i + 1) * riser_height
            base = len(verts)
            verts.extend([
                (x0, 0, z0), (x1, 0, z0), (x1, width, z0), (x0, width, z0),
                (x0, 0, z1), (x1, 0, z1), (x1, width, z1), (x0, width, z1),
            ])
            faces.extend([
                (base, base + 1, base + 2, base + 3),
                (base + 4, base + 5, base + 6, base + 7),
                (base, base + 1, base + 5, base + 4),
                (base + 1, base + 2, base + 6, base + 5),
                (base + 2, base + 3, base + 7, base + 6),
                (base + 3, base, base + 4, base + 7),
            ])

        mesh = bpy.data.meshes.new(stair.Name or "Stair")
        mesh.from_pydata(verts, [], faces)
        mesh.update()

        obj = bpy.data.objects.new(stair.Name or "Stair", mesh)
        bpy.context.collection.objects.link(obj)
        if location:
            obj.location = location

        import bonsai.tool as tool
        tool.Ifc.link(stair, obj)

        return {
            "id": stair.id(),
            "name": stair.Name,
            "global_id": stair.GlobalId,
            "object": obj.name,
            "treads": treads,
        }

    def bim_remove_element(name: str, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        obj = bpy.data.objects.get(name)
        if obj:
            element = s.get_ifc_element(obj)
            ifcopenshell.api.run("root.remove_product", ifc_file, product=element)
            bpy.data.objects.remove(obj, do_unlink=True)
        else:
            raise RuntimeError(f"Object not found: {name}")
        return {"removed": name}

    s._HANDLERS.update({
        "bim_add_wall": bim_add_wall,
        "bim_add_slab": bim_add_slab,
        "bim_add_column": bim_add_column,
        "bim_add_beam": bim_add_beam,
        "bim_add_door": bim_add_door,
        "bim_add_window": bim_add_window,
        "bim_add_stair": bim_add_stair,
        "bim_remove_element": bim_remove_element,
    })
