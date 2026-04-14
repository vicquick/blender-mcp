"""
BIM Schedule handlers — 4D work schedules, tasks, sequences, info.
"""

import bpy


def register(server):
    """Register BIM schedule handlers."""
    s = server

    def bim_add_work_schedule(name: str, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        schedule = ifcopenshell.api.run("sequence.add_work_schedule", ifc_file, name=name)
        return {"id": schedule.id(), "name": name}

    def bim_add_task(schedule_name: str, name: str, start: str = None,
                     finish: str = None, duration: str = None, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        schedule = None
        for ws in ifc_file.by_type("IfcWorkSchedule"):
            if ws.Name == schedule_name:
                schedule = ws
                break
        if not schedule:
            raise RuntimeError(f"Work schedule not found: {schedule_name}")
        task = ifcopenshell.api.run("sequence.add_task", ifc_file, work_schedule=schedule)
        task.Name = name
        if start or finish or duration:
            time = ifcopenshell.api.run("sequence.add_task_time", ifc_file, task=task)
            if start:
                time.ScheduleStart = start
            if finish:
                time.ScheduleFinish = finish
            if duration:
                time.ScheduleDuration = duration
        return {"id": task.id(), "name": name, "schedule": schedule_name}

    def bim_assign_task_to_element(task_id: int, object_names: list, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        task = ifc_file.by_id(task_id)
        if not task:
            raise RuntimeError(f"Task not found: {task_id}")
        assigned = []
        for name in object_names:
            obj = bpy.data.objects.get(name)
            if obj:
                element = s.get_ifc_element(obj)
                ifcopenshell.api.run("sequence.assign_product", ifc_file,
                                      relating_product=element, related_object=task)
                assigned.append(name)
        return {"task_id": task_id, "assigned": assigned}

    def bim_add_task_sequence(predecessor_id: int, successor_id: int,
                              type: str = "FINISH_START", **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        pred = ifc_file.by_id(predecessor_id)
        succ = ifc_file.by_id(successor_id)
        if not pred or not succ:
            raise RuntimeError("Predecessor or successor task not found")
        rel = ifcopenshell.api.run("sequence.assign_sequence", ifc_file,
                                    relating_process=pred, related_process=succ)
        if hasattr(rel, 'SequenceType'):
            rel.SequenceType = type
        return {"predecessor": predecessor_id, "successor": successor_id, "type": type}

    def bim_calculate_schedule(schedule_name: str, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        schedule = None
        for ws in ifc_file.by_type("IfcWorkSchedule"):
            if ws.Name == schedule_name:
                schedule = ws
                break
        if not schedule:
            raise RuntimeError(f"Work schedule not found: {schedule_name}")
        try:
            ifcopenshell.api.run("sequence.recalculate_schedule", ifc_file,
                                  work_schedule=schedule)
        except Exception as e:
            return {"schedule": schedule_name, "warning": str(e)}
        return {"schedule": schedule_name, "recalculated": True}

    def bim_get_schedule_info(schedule_name: str, **_):
        ifc_file = s.get_ifc_file()
        schedule = None
        for ws in ifc_file.by_type("IfcWorkSchedule"):
            if ws.Name == schedule_name:
                schedule = ws
                break
        if not schedule:
            raise RuntimeError(f"Work schedule not found: {schedule_name}")
        tasks = []
        for rel in ifc_file.by_type("IfcRelAssignsToControl"):
            if rel.RelatingControl == schedule:
                for obj in rel.RelatedObjects:
                    if obj.is_a("IfcTask"):
                        info = {"id": obj.id(), "name": obj.Name}
                        if obj.TaskTime:
                            tt = obj.TaskTime
                            info["start"] = str(tt.ScheduleStart) if tt.ScheduleStart else None
                            info["finish"] = str(tt.ScheduleFinish) if tt.ScheduleFinish else None
                            info["duration"] = str(tt.ScheduleDuration) if tt.ScheduleDuration else None
                        tasks.append(info)
        return {"schedule": schedule_name, "tasks": tasks, "count": len(tasks)}

    s._HANDLERS.update({
        "bim_add_work_schedule": bim_add_work_schedule,
        "bim_add_task": bim_add_task,
        "bim_assign_task_to_element": bim_assign_task_to_element,
        "bim_add_task_sequence": bim_add_task_sequence,
        "bim_calculate_schedule": bim_calculate_schedule,
        "bim_get_schedule_info": bim_get_schedule_info,
    })
