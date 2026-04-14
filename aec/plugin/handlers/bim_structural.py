"""
BIM Structural handlers — analysis models, loads, load cases, boundary conditions.
"""


def register(server):
    """Register BIM structural handlers."""
    s = server

    def bim_add_structural_model(name: str, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        model = ifcopenshell.api.run("structural.add_structural_analysis_model", ifc_file)
        model.Name = name
        return {"id": model.id(), "name": name}

    def bim_add_structural_load(name: str, load_type: str, values: dict = None, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        load = ifcopenshell.api.run("structural.add_structural_load", ifc_file,
                                     name=name, ifc_class=f"IfcStructuralLoad{load_type}")
        if values:
            for attr, val in values.items():
                if hasattr(load, attr):
                    setattr(load, attr, val)
        return {"id": load.id(), "name": name, "type": load_type}

    def bim_add_load_case(name: str, load_type: str = "DEAD_LOAD_G", **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        load_case = ifcopenshell.api.run("structural.add_structural_load_case", ifc_file,
                                          name=name, action_type="PERMANENT_G")
        return {"id": load_case.id(), "name": name, "type": load_type}

    def bim_add_boundary_condition(element_name: str, condition_type: str = "FIXED", **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        import bpy
        obj = s.get_object_or_raise(element_name)
        condition = ifcopenshell.api.run("structural.add_structural_boundary_condition",
                                          ifc_file, name=f"BC_{element_name}",
                                          ifc_class="IfcBoundaryNodeCondition")
        # Set condition based on type
        if condition_type.upper() == "FIXED":
            for attr in ("TranslationalStiffnessX", "TranslationalStiffnessY",
                        "TranslationalStiffnessZ", "RotationalStiffnessX",
                        "RotationalStiffnessY", "RotationalStiffnessZ"):
                if hasattr(condition, attr):
                    setattr(condition, attr, True)  # Fixed = infinite stiffness
        elif condition_type.upper() == "PINNED":
            for attr in ("TranslationalStiffnessX", "TranslationalStiffnessY",
                        "TranslationalStiffnessZ"):
                if hasattr(condition, attr):
                    setattr(condition, attr, True)
        return {"element": element_name, "condition": condition_type, "id": condition.id()}

    s._HANDLERS.update({
        "bim_add_structural_model": bim_add_structural_model,
        "bim_add_structural_load": bim_add_structural_load,
        "bim_add_load_case": bim_add_load_case,
        "bim_add_boundary_condition": bim_add_boundary_condition,
    })
