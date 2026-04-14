"""
BIM Type handlers — create, assign, list, info.
"""

import bpy


def register(server):
    """Register BIM type handlers."""
    s = server

    def bim_create_type(ifc_class: str, name: str = None, predefined_type: str = None, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        element_type = ifcopenshell.api.run("root.create_entity", ifc_file,
                                             ifc_class=ifc_class, name=name,
                                             predefined_type=predefined_type)
        return {"id": element_type.id(), "class": ifc_class, "name": element_type.Name}

    def bim_assign_type(object_name: str, type_name: str, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        obj = s.get_object_or_raise(object_name)
        element = s.get_ifc_element(obj)
        # Find type by name
        element_type = None
        for t in ifc_file.by_type("IfcTypeProduct"):
            if t.Name == type_name:
                element_type = t
                break
        if not element_type:
            raise RuntimeError(f"Type not found: {type_name}")
        ifcopenshell.api.run("type.assign_type", ifc_file,
                              related_objects=[element], relating_type=element_type)
        return {"object": object_name, "type": type_name}

    def bim_list_types(ifc_class: str = None, **_):
        ifc_file = s.get_ifc_file()
        if ifc_class:
            types = ifc_file.by_type(ifc_class)
        else:
            types = ifc_file.by_type("IfcTypeProduct")
        result = []
        for t in types:
            result.append({
                "id": t.id(),
                "class": t.is_a(),
                "name": t.Name,
                "predefined_type": t.PredefinedType if hasattr(t, 'PredefinedType') else None,
            })
        return {"types": result, "count": len(result)}

    def bim_get_type_info(name: str, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.util.element
        element_type = None
        for t in ifc_file.by_type("IfcTypeProduct"):
            if t.Name == name:
                element_type = t
                break
        if not element_type:
            raise RuntimeError(f"Type not found: {name}")
        psets = ifcopenshell.util.element.get_psets(element_type)
        mat = ifcopenshell.util.element.get_material(element_type)
        return {
            "id": element_type.id(),
            "class": element_type.is_a(),
            "name": element_type.Name,
            "psets": {k: {pk: pv for pk, pv in v.items() if pk != "id"}
                      for k, v in psets.items()},
            "material": mat.Name if mat and hasattr(mat, 'Name') else str(mat) if mat else None,
        }

    s._HANDLERS.update({
        "bim_create_type": bim_create_type,
        "bim_assign_type": bim_assign_type,
        "bim_list_types": bim_list_types,
        "bim_get_type_info": bim_get_type_info,
    })
