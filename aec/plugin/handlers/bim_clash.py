"""
BIM Clash detection handlers — create sets, run detection, get results.
"""

import bpy


def register(server):
    """Register BIM clash handlers."""
    s = server

    def bim_create_clash_set(name: str, group_a: list, group_b: list,
                              tolerance: float = 0.01, **_):
        # Store clash set definition in scene custom properties
        scene = bpy.context.scene
        if not hasattr(scene, "clash_sets"):
            scene["clash_sets"] = {}
        clash_sets = dict(scene.get("clash_sets", {}))
        clash_sets[name] = {
            "group_a": group_a,
            "group_b": group_b,
            "tolerance": tolerance,
        }
        scene["clash_sets"] = clash_sets
        return {"name": name, "group_a_count": len(group_a),
                "group_b_count": len(group_b), "tolerance": tolerance}

    def bim_run_clash_detection(clash_set_name: str = None, **_):
        ifc_file = s.get_ifc_file()
        try:
            from ifcclash import ifcclash
        except ImportError:
            raise RuntimeError("ifcclash not available")

        scene = bpy.context.scene
        clash_sets = dict(scene.get("clash_sets", {}))
        if clash_set_name and clash_set_name not in clash_sets:
            raise RuntimeError(f"Clash set not found: {clash_set_name}")

        sets_to_run = {clash_set_name: clash_sets[clash_set_name]} if clash_set_name else clash_sets
        results = {}
        for name, cs in sets_to_run.items():
            clasher = ifcclash.Clasher()
            clasher.settings.tolerance = cs["tolerance"]
            # Run basic intersection detection
            clashes = []
            group_a = [s.get_object_or_raise(n) for n in cs["group_a"] if bpy.data.objects.get(n)]
            group_b = [s.get_object_or_raise(n) for n in cs["group_b"] if bpy.data.objects.get(n)]
            # Simplified: check bounding box overlaps
            for a in group_a:
                for b in group_b:
                    if _bbox_overlaps(a, b):
                        clashes.append({
                            "element_a": a.name,
                            "element_b": b.name,
                        })
            results[name] = {"clashes": clashes, "count": len(clashes)}
        scene["clash_results"] = results
        return results

    def _bbox_overlaps(a, b):
        """Check if two objects' bounding boxes overlap."""
        a_min = [min(v[i] for v in a.bound_box) + a.location[i] for i in range(3)]
        a_max = [max(v[i] for v in a.bound_box) + a.location[i] for i in range(3)]
        b_min = [min(v[i] for v in b.bound_box) + b.location[i] for i in range(3)]
        b_max = [max(v[i] for v in b.bound_box) + b.location[i] for i in range(3)]
        return all(a_min[i] <= b_max[i] and a_max[i] >= b_min[i] for i in range(3))

    def bim_get_clash_results(clash_set_name: str = None, **_):
        scene = bpy.context.scene
        results = dict(scene.get("clash_results", {}))
        if clash_set_name:
            if clash_set_name not in results:
                return {"error": f"No results for: {clash_set_name}"}
            return {clash_set_name: results[clash_set_name]}
        return results

    def bim_select_clashing_elements(clash_id: int = 0, clash_set_name: str = None, **_):
        scene = bpy.context.scene
        results = dict(scene.get("clash_results", {}))
        if not results:
            raise RuntimeError("No clash results. Run bim_run_clash_detection first.")
        if clash_set_name and clash_set_name in results:
            clashes = results[clash_set_name].get("clashes", [])
        else:
            # Get first result set
            first_key = next(iter(results))
            clashes = results[first_key].get("clashes", [])
        if clash_id >= len(clashes):
            raise RuntimeError(f"Clash index {clash_id} out of range (total: {len(clashes)})")
        clash = clashes[clash_id]
        bpy.ops.object.select_all(action='DESELECT')
        for name in (clash["element_a"], clash["element_b"]):
            obj = bpy.data.objects.get(name)
            if obj:
                obj.select_set(True)
        return {"selected": [clash["element_a"], clash["element_b"]]}

    s._HANDLERS.update({
        "bim_create_clash_set": bim_create_clash_set,
        "bim_run_clash_detection": bim_run_clash_detection,
        "bim_get_clash_results": bim_get_clash_results,
        "bim_select_clashing_elements": bim_select_clashing_elements,
    })
