"""
BIM Material handlers — IFC materials, layer sets, profile sets, assign, list.
"""

import bpy


def register(server):
    """Register BIM material handlers."""
    s = server

    def bim_add_material(name: str, category: str = None, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        mat = ifcopenshell.api.run("material.add_material", ifc_file,
                                    name=name, category=category)
        return {"id": mat.id(), "name": mat.Name, "category": category}

    def bim_assign_material(object_name: str, material_name: str, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        obj = s.get_object_or_raise(object_name)
        element = s.get_ifc_element(obj)
        # Find material by name
        mat = None
        for m in ifc_file.by_type("IfcMaterial"):
            if m.Name == material_name:
                mat = m
                break
        if not mat:
            raise RuntimeError(f"IFC material not found: {material_name}")
        ifcopenshell.api.run("material.assign_material", ifc_file,
                              products=[element], material=mat)
        return {"object": object_name, "material": material_name}

    def bim_add_material_layer_set(name: str, layers: list, **_):
        """Create layered material. layers: [{"material": "name", "thickness": 0.1}, ...]"""
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        mat_set = ifcopenshell.api.run("material.add_material_set", ifc_file,
                                        name=name, set_type="IfcMaterialLayerSet")
        for layer_def in layers:
            mat_name = layer_def.get("material")
            thickness = layer_def.get("thickness", 0.1)
            mat = None
            if mat_name:
                for m in ifc_file.by_type("IfcMaterial"):
                    if m.Name == mat_name:
                        mat = m
                        break
                if not mat:
                    mat = ifcopenshell.api.run("material.add_material", ifc_file, name=mat_name)
            layer = ifcopenshell.api.run("material.add_layer", ifc_file,
                                          layer_set=mat_set, material=mat)
            layer.LayerThickness = thickness
        return {"name": name, "layer_count": len(layers)}

    def bim_add_material_profile_set(name: str, profiles: list, **_):
        """Create profile material. profiles: [{"material": "name", "profile": "name"}, ...]"""
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        mat_set = ifcopenshell.api.run("material.add_material_set", ifc_file,
                                        name=name, set_type="IfcMaterialProfileSet")
        for prof_def in profiles:
            mat_name = prof_def.get("material")
            mat = None
            if mat_name:
                for m in ifc_file.by_type("IfcMaterial"):
                    if m.Name == mat_name:
                        mat = m
                        break
                if not mat:
                    mat = ifcopenshell.api.run("material.add_material", ifc_file, name=mat_name)
            ifcopenshell.api.run("material.add_profile", ifc_file,
                                  profile_set=mat_set, material=mat)
        return {"name": name, "profile_count": len(profiles)}

    def bim_list_materials(**_):
        ifc_file = s.get_ifc_file()
        materials = []
        for mat in ifc_file.by_type("IfcMaterial"):
            materials.append({
                "id": mat.id(),
                "name": mat.Name,
                "category": mat.Category if hasattr(mat, 'Category') and mat.Category else None,
            })
        # Also list material sets
        sets = []
        for ms in ifc_file.by_type("IfcMaterialLayerSet"):
            sets.append({"id": ms.id(), "name": ms.LayerSetName, "type": "LayerSet"})
        for ms in ifc_file.by_type("IfcMaterialProfileSet"):
            sets.append({"id": ms.id(), "name": ms.Name, "type": "ProfileSet"})
        return {"materials": materials, "material_sets": sets}

    s._HANDLERS.update({
        "bim_add_material": bim_add_material,
        "bim_assign_material": bim_assign_material,
        "bim_add_material_layer_set": bim_add_material_layer_set,
        "bim_add_material_profile_set": bim_add_material_profile_set,
        "bim_list_materials": bim_list_materials,
    })
