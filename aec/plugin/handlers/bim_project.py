"""
BIM Project handlers — IFC project create, open, save, info, units.
"""

import bpy


def register(server):
    """Register BIM project handlers."""
    s = server

    def bim_create_project(schema: str = "IFC4", **_):
        bpy.ops.bim.create_project()
        ifc_file = s.get_ifc_file()
        project = ifc_file.by_type("IfcProject")[0]
        return {
            "created": True,
            "schema": ifc_file.schema,
            "project_name": project.Name if project else None,
        }

    def bim_load_project(filepath: str, **_):
        import os
        if not os.path.exists(filepath):
            raise RuntimeError(f"File not found: {filepath}")
        bpy.ops.bim.load_project(filepath=filepath)
        ifc_file = s.get_ifc_file()
        return {
            "loaded": filepath,
            "schema": ifc_file.schema,
            "entity_count": len(list(ifc_file)),
        }

    def bim_save_project(filepath: str = None, **_):
        ifc_file = s.get_ifc_file()
        if filepath:
            ifc_file.write(filepath)
        else:
            import bonsai.tool as tool
            path = tool.Ifc.get_path()
            if not path:
                raise RuntimeError("No file path set. Provide a filepath parameter.")
            ifc_file.write(path)
            filepath = path
        return {"saved": filepath}

    def bim_get_project_info(**_):
        ifc_file = s.get_ifc_file()
        project = ifc_file.by_type("IfcProject")
        project = project[0] if project else None

        # Spatial summary
        sites = ifc_file.by_type("IfcSite")
        buildings = ifc_file.by_type("IfcBuilding")
        storeys = ifc_file.by_type("IfcBuildingStorey")
        spaces = ifc_file.by_type("IfcSpace")

        # Units
        units = []
        if project:
            units_assignment = project.UnitsInContext
            if units_assignment:
                for unit in units_assignment.Units:
                    unit_info = {"type": unit.is_a()}
                    if hasattr(unit, 'UnitType'):
                        unit_info["unit_type"] = str(unit.UnitType)
                    if hasattr(unit, 'Name'):
                        unit_info["name"] = str(unit.Name) if unit.Name else None
                    if hasattr(unit, 'Prefix') and unit.Prefix:
                        unit_info["prefix"] = str(unit.Prefix)
                    units.append(unit_info)

        return {
            "schema": ifc_file.schema,
            "project_name": project.Name if project else None,
            "description": project.Description if project and project.Description else None,
            "entity_count": len(list(ifc_file)),
            "sites": len(sites),
            "buildings": len(buildings),
            "storeys": len(storeys),
            "spaces": len(spaces),
            "units": units,
        }

    def bim_set_units(length: str = "MILLIMETRE", area: str = "SQUARE_METRE", **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        # Get or create unit assignment
        project = ifc_file.by_type("IfcProject")[0]
        if not project.UnitsInContext:
            ifcopenshell.api.run("unit.assign_unit", ifc_file)

        # Map friendly names to IFC
        length_map = {
            "METRE": ("LENGTHUNIT", None),
            "MILLIMETRE": ("LENGTHUNIT", "MILLI"),
            "CENTIMETRE": ("LENGTHUNIT", "CENTI"),
            "FOOT": None,  # conversion-based
        }
        if length.upper() in length_map and length_map[length.upper()]:
            unit_type, prefix = length_map[length.upper()]
            ifcopenshell.api.run("unit.add_si_unit", ifc_file,
                                 unit_type=unit_type, prefix=prefix)

        return {"length": length, "area": area}

    s._HANDLERS.update({
        "bim_create_project": bim_create_project,
        "bim_load_project": bim_load_project,
        "bim_save_project": bim_save_project,
        "bim_get_project_info": bim_get_project_info,
        "bim_set_units": bim_set_units,
    })
