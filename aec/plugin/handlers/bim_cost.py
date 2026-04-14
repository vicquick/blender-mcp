"""
BIM Cost handlers — 5D cost schedules, items, assignment, calculation, export.
"""

import bpy


def register(server):
    """Register BIM cost handlers."""
    s = server

    def bim_add_cost_schedule(name: str, predefined_type: str = "BUDGET", **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        schedule = ifcopenshell.api.run("cost.add_cost_schedule", ifc_file, name=name,
                                         predefined_type=predefined_type)
        return {"id": schedule.id(), "name": name, "type": predefined_type}

    def bim_add_cost_item(schedule_name: str, name: str, quantity: float = None,
                          unit_cost: float = None, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        schedule = None
        for cs in ifc_file.by_type("IfcCostSchedule"):
            if cs.Name == schedule_name:
                schedule = cs
                break
        if not schedule:
            raise RuntimeError(f"Cost schedule not found: {schedule_name}")
        item = ifcopenshell.api.run("cost.add_cost_item", ifc_file, cost_schedule=schedule)
        item.Name = name
        if unit_cost is not None:
            value = ifcopenshell.api.run("cost.add_cost_value", ifc_file, parent=item)
            value.AppliedValue = ifc_file.createIfcMonetaryMeasure(unit_cost)
        return {"id": item.id(), "name": name, "schedule": schedule_name}

    def bim_assign_cost_to_element(cost_item_id: int, object_names: list, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        cost_item = ifc_file.by_id(cost_item_id)
        if not cost_item:
            raise RuntimeError(f"Cost item not found: {cost_item_id}")
        assigned = []
        for name in object_names:
            obj = bpy.data.objects.get(name)
            if obj:
                element = s.get_ifc_element(obj)
                ifcopenshell.api.run("cost.assign_cost_item_quantity", ifc_file,
                                      cost_item=cost_item, products=[element])
                assigned.append(name)
        return {"cost_item_id": cost_item_id, "assigned": assigned}

    def bim_calculate_costs(schedule_name: str, **_):
        ifc_file = s.get_ifc_file()
        schedule = None
        for cs in ifc_file.by_type("IfcCostSchedule"):
            if cs.Name == schedule_name:
                schedule = cs
                break
        if not schedule:
            raise RuntimeError(f"Cost schedule not found: {schedule_name}")
        # Collect cost items
        items = []
        for rel in ifc_file.by_type("IfcRelAssignsToControl"):
            if rel.RelatingControl == schedule:
                for obj in rel.RelatedObjects:
                    if obj.is_a("IfcCostItem"):
                        items.append({
                            "id": obj.id(),
                            "name": obj.Name,
                        })
        return {"schedule": schedule_name, "items": items, "count": len(items)}

    def bim_export_cost_schedule(schedule_name: str, filepath: str,
                                 format: str = "CSV", **_):
        ifc_file = s.get_ifc_file()
        schedule = None
        for cs in ifc_file.by_type("IfcCostSchedule"):
            if cs.Name == schedule_name:
                schedule = cs
                break
        if not schedule:
            raise RuntimeError(f"Cost schedule not found: {schedule_name}")
        import os
        dirpath = os.path.dirname(filepath)
        if dirpath and not os.path.exists(dirpath):
            os.makedirs(dirpath, exist_ok=True)
        try:
            import ifccsv
            ifc_csv = ifccsv.IfcCsv()
            ifc_csv.export(ifc_file, [schedule], filepath)
        except ImportError:
            raise RuntimeError("ifccsv not available for cost export")
        return {"exported": filepath, "format": format}

    s._HANDLERS.update({
        "bim_add_cost_schedule": bim_add_cost_schedule,
        "bim_add_cost_item": bim_add_cost_item,
        "bim_assign_cost_to_element": bim_assign_cost_to_element,
        "bim_calculate_costs": bim_calculate_costs,
        "bim_export_cost_schedule": bim_export_cost_schedule,
    })
