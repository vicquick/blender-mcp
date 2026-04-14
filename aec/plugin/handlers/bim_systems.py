"""
BIM Systems handlers — MEP systems, ports, connections.
"""

import bpy


def register(server):
    """Register BIM systems handlers."""
    s = server

    def bim_add_system(name: str, ifc_class: str = "IfcDistributionSystem", **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        system = ifcopenshell.api.run("system.add_system", ifc_file, ifc_class=ifc_class)
        system.Name = name
        return {"id": system.id(), "name": name, "class": ifc_class}

    def bim_assign_to_system(object_names: list, system_name: str, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        system = None
        for sys in ifc_file.by_type("IfcSystem"):
            if sys.Name == system_name:
                system = sys
                break
        if not system:
            raise RuntimeError(f"System not found: {system_name}")
        assigned = []
        for name in object_names:
            obj = bpy.data.objects.get(name)
            if obj:
                element = s.get_ifc_element(obj)
                ifcopenshell.api.run("system.assign_system", ifc_file,
                                      products=[element], system=system)
                assigned.append(name)
        return {"system": system_name, "assigned": assigned}

    def bim_connect_ports(element_a: str, element_b: str,
                          port_a: int = 0, port_b: int = 0, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        import ifcopenshell.util.system
        obj_a = s.get_object_or_raise(element_a)
        obj_b = s.get_object_or_raise(element_b)
        el_a = s.get_ifc_element(obj_a)
        el_b = s.get_ifc_element(obj_b)
        ports_a = ifcopenshell.util.system.get_ports(el_a)
        ports_b = ifcopenshell.util.system.get_ports(el_b)
        if port_a >= len(ports_a):
            # Create port if needed
            p = ifcopenshell.api.run("system.add_port", ifc_file, element=el_a)
            ports_a = ifcopenshell.util.system.get_ports(el_a)
        if port_b >= len(ports_b):
            p = ifcopenshell.api.run("system.add_port", ifc_file, element=el_b)
            ports_b = ifcopenshell.util.system.get_ports(el_b)
        ifcopenshell.api.run("system.connect_port", ifc_file,
                              port1=ports_a[port_a], port2=ports_b[port_b])
        return {"element_a": element_a, "element_b": element_b}

    def bim_list_systems(**_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.util.system
        systems = []
        for sys in ifc_file.by_type("IfcSystem"):
            elements = ifcopenshell.util.system.get_system_elements(sys)
            systems.append({
                "id": sys.id(),
                "name": sys.Name,
                "class": sys.is_a(),
                "element_count": len(elements),
            })
        return {"systems": systems, "count": len(systems)}

    s._HANDLERS.update({
        "bim_add_system": bim_add_system,
        "bim_assign_to_system": bim_assign_to_system,
        "bim_connect_ports": bim_connect_ports,
        "bim_list_systems": bim_list_systems,
    })
