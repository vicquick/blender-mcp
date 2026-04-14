"""
BIM Property handlers — property sets, quantities, attributes, element queries.
"""

import bpy


def register(server):
    """Register BIM property handlers."""
    s = server

    def bim_add_pset(object_name: str, pset_name: str, properties: dict, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        obj = s.get_object_or_raise(object_name)
        element = s.get_ifc_element(obj)
        pset = ifcopenshell.api.run("pset.add_pset", ifc_file,
                                     product=element, name=pset_name)
        ifcopenshell.api.run("pset.edit_pset", ifc_file, pset=pset, properties=properties)
        return {"object": object_name, "pset": pset_name, "properties": properties}

    def bim_get_psets(object_name: str, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.util.element
        obj = s.get_object_or_raise(object_name)
        element = s.get_ifc_element(obj)
        psets = ifcopenshell.util.element.get_psets(element)
        # Convert to JSON-safe
        result = {}
        for pset_name, props in psets.items():
            safe_props = {}
            for k, v in props.items():
                if k == "id":
                    continue
                if isinstance(v, (str, int, float, bool, type(None))):
                    safe_props[k] = v
                else:
                    safe_props[k] = str(v)
            result[pset_name] = safe_props
        return {"object": object_name, "psets": result}

    def bim_add_qto(object_name: str, qto_name: str, quantities: dict, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        obj = s.get_object_or_raise(object_name)
        element = s.get_ifc_element(obj)
        qto = ifcopenshell.api.run("pset.add_qto", ifc_file,
                                    product=element, name=qto_name)
        ifcopenshell.api.run("pset.edit_qto", ifc_file, qto=qto, properties=quantities)
        return {"object": object_name, "qto": qto_name, "quantities": quantities}

    def bim_get_attributes(object_name: str, **_):
        obj = s.get_object_or_raise(object_name)
        element = s.get_ifc_element(obj)
        attrs = {}
        for attr in element.wrapped_data.get_attribute_names():
            val = getattr(element, attr, None)
            if isinstance(val, (str, int, float, bool, type(None))):
                attrs[attr] = val
            else:
                attrs[attr] = str(val) if val is not None else None
        return {"object": object_name, "class": element.is_a(), "attributes": attrs}

    def bim_edit_attribute(object_name: str, attribute: str, value: str, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        obj = s.get_object_or_raise(object_name)
        element = s.get_ifc_element(obj)
        ifcopenshell.api.run("attribute.edit_attributes", ifc_file,
                              product=element, attributes={attribute: value})
        return {"object": object_name, "attribute": attribute, "value": value}

    def bim_query_elements(ifc_class: str = None, pset_filter: str = None,
                           container: str = None, limit: int = 50, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.util.element

        if ifc_class:
            elements = ifc_file.by_type(ifc_class)
        else:
            elements = ifc_file.by_type("IfcProduct")

        results = []
        for el in elements:
            if len(results) >= limit:
                break
            # Container filter
            if container:
                el_container = ifcopenshell.util.element.get_container(el)
                if not el_container or el_container.Name != container:
                    continue
            # Pset filter (format: "PsetName.PropertyName=Value")
            if pset_filter:
                psets = ifcopenshell.util.element.get_psets(el)
                parts = pset_filter.split("=", 1)
                if len(parts) == 2:
                    path, expected = parts[0], parts[1]
                    pset_parts = path.split(".", 1)
                    if len(pset_parts) == 2:
                        pset_name, prop_name = pset_parts
                        pset = psets.get(pset_name, {})
                        actual = str(pset.get(prop_name, ""))
                        if actual != expected:
                            continue

            info = {
                "id": el.id(),
                "class": el.is_a(),
                "name": el.Name,
                "global_id": el.GlobalId,
            }
            c = ifcopenshell.util.element.get_container(el)
            if c:
                info["container"] = c.Name
            t = ifcopenshell.util.element.get_type(el)
            if t:
                info["type"] = t.Name
            results.append(info)

        return {"elements": results, "count": len(results)}

    s._HANDLERS.update({
        "bim_add_pset": bim_add_pset,
        "bim_get_psets": bim_get_psets,
        "bim_add_qto": bim_add_qto,
        "bim_get_attributes": bim_get_attributes,
        "bim_edit_attribute": bim_edit_attribute,
        "bim_query_elements": bim_query_elements,
    })
