"""
BIM Spatial handlers — site, building, storey, space, spatial tree, containers.
"""

import bpy


def register(server):
    """Register BIM spatial handlers."""
    s = server

    def bim_create_spatial_element(ifc_class: str, name: str = None,
                                   parent: str = None, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        valid = ("IfcSite", "IfcBuilding", "IfcBuildingStorey", "IfcSpace")
        if ifc_class not in valid:
            raise RuntimeError(f"Invalid class: {ifc_class}. Use: {', '.join(valid)}")
        element = ifcopenshell.api.run("root.create_entity", ifc_file,
                                        ifc_class=ifc_class, name=name)
        # Assign to parent aggregate
        if parent:
            parent_obj = bpy.data.objects.get(parent)
            if parent_obj:
                parent_element = s.get_ifc_element(parent_obj)
                ifcopenshell.api.run("aggregate.assign_object", ifc_file,
                                      products=[element], relating_object=parent_element)
            else:
                # Try finding by IFC name
                for p in ifc_file.by_type("IfcSpatialStructureElement"):
                    if p.Name == parent:
                        ifcopenshell.api.run("aggregate.assign_object", ifc_file,
                                              products=[element], relating_object=p)
                        break
        else:
            # Auto-assign to appropriate parent
            if ifc_class == "IfcSite":
                project = ifc_file.by_type("IfcProject")[0]
                ifcopenshell.api.run("aggregate.assign_object", ifc_file,
                                      products=[element], relating_object=project)
            elif ifc_class == "IfcBuilding":
                sites = ifc_file.by_type("IfcSite")
                if sites:
                    ifcopenshell.api.run("aggregate.assign_object", ifc_file,
                                          products=[element], relating_object=sites[0])
            elif ifc_class == "IfcBuildingStorey":
                buildings = ifc_file.by_type("IfcBuilding")
                if buildings:
                    ifcopenshell.api.run("aggregate.assign_object", ifc_file,
                                          products=[element], relating_object=buildings[0])

        return {
            "id": element.id(),
            "class": ifc_class,
            "name": element.Name,
            "global_id": element.GlobalId,
        }

    def bim_get_spatial_tree(**_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.util.element

        def build_tree(element, depth=0):
            node = {
                "id": element.id(),
                "class": element.is_a(),
                "name": element.Name,
                "depth": depth,
                "children": [],
            }
            decomposition = ifcopenshell.util.element.get_decomposition(element)
            for child in decomposition:
                if child.is_a("IfcSpatialStructureElement") or child.is_a("IfcProject"):
                    node["children"].append(build_tree(child, depth + 1))
            # Count contained elements
            if hasattr(element, 'ContainsElements'):
                contained = []
                for rel in element.ContainsElements:
                    for el in rel.RelatedElements:
                        contained.append({"id": el.id(), "class": el.is_a(), "name": el.Name})
                node["contained_elements"] = len(contained)
            return node

        project = ifc_file.by_type("IfcProject")
        if not project:
            return {"tree": None}
        return {"tree": build_tree(project[0])}

    def bim_assign_container(object_names: list, container_name: str, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        # Find container
        container = None
        for el in ifc_file.by_type("IfcSpatialStructureElement"):
            if el.Name == container_name:
                container = el
                break
        if not container:
            obj = bpy.data.objects.get(container_name)
            if obj:
                container = s.get_ifc_element(obj)
        if not container:
            raise RuntimeError(f"Container not found: {container_name}")

        assigned = []
        for name in object_names:
            obj = bpy.data.objects.get(name)
            if obj:
                element = s.get_ifc_element(obj)
                ifcopenshell.api.run("spatial.assign_container", ifc_file,
                                      products=[element], relating_structure=container)
                assigned.append(name)
        return {"container": container_name, "assigned": assigned}

    def bim_remove_container(name: str, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        obj = bpy.data.objects.get(name)
        if obj:
            element = s.get_ifc_element(obj)
        else:
            for el in ifc_file.by_type("IfcSpatialStructureElement"):
                if el.Name == name:
                    element = el
                    break
            else:
                raise RuntimeError(f"Spatial element not found: {name}")
        ifcopenshell.api.run("root.remove_product", ifc_file, product=element)
        return {"removed": name}

    def bim_set_default_container(name: str, **_):
        # Find the container object in the scene
        obj = bpy.data.objects.get(name)
        if not obj:
            # Try by IFC name
            ifc_file = s.get_ifc_file()
            for el in ifc_file.by_type("IfcBuildingStorey"):
                if el.Name == name:
                    import bonsai.tool as tool
                    obj = tool.Ifc.get_object(el)
                    break
        if not obj:
            raise RuntimeError(f"Container object not found: {name}")
        bpy.context.view_layer.objects.active = obj
        try:
            bpy.ops.bim.set_default_container()
        except Exception:
            pass  # May not be available in all contexts
        return {"default_container": name}

    def bim_get_container_elements(name: str, **_):
        ifc_file = s.get_ifc_file()
        container = None
        for el in ifc_file.by_type("IfcSpatialStructureElement"):
            if el.Name == name:
                container = el
                break
        if not container:
            raise RuntimeError(f"Container not found: {name}")

        elements = []
        if hasattr(container, 'ContainsElements'):
            for rel in container.ContainsElements:
                for el in rel.RelatedElements:
                    elements.append({
                        "id": el.id(),
                        "class": el.is_a(),
                        "name": el.Name,
                        "global_id": el.GlobalId,
                    })
        return {"container": name, "elements": elements, "count": len(elements)}

    s._HANDLERS.update({
        "bim_create_spatial_element": bim_create_spatial_element,
        "bim_get_spatial_tree": bim_get_spatial_tree,
        "bim_assign_container": bim_assign_container,
        "bim_remove_container": bim_remove_container,
        "bim_set_default_container": bim_set_default_container,
        "bim_get_container_elements": bim_get_container_elements,
    })
