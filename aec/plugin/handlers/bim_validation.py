"""
BIM Validation handlers — IFC validation, IDS checks, purge unused.
"""

import bpy


def register(server):
    """Register BIM validation handlers."""
    s = server

    def bim_validate_ifc(filepath: str = None, **_):
        import ifcopenshell.validate
        import io
        import logging

        if filepath:
            ifc_file = ifcopenshell.open(filepath)
        else:
            ifc_file = s.get_ifc_file()

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.WARNING)
        logger = logging.getLogger("ifcopenshell.validate")
        logger.addHandler(handler)

        try:
            ifcopenshell.validate.validate(ifc_file, logger)
        except Exception as e:
            return {"valid": False, "error": str(e)}
        finally:
            logger.removeHandler(handler)

        log_output = log_stream.getvalue()
        issues = [line for line in log_output.strip().split("\n") if line]
        return {
            "valid": len(issues) == 0,
            "issue_count": len(issues),
            "issues": issues[:50],  # Limit output
            "schema": ifc_file.schema,
        }

    def bim_run_ids_check(ids_filepath: str, **_):
        try:
            import ifctester
            import ifctester.ids
            import ifctester.reporter
        except ImportError:
            raise RuntimeError("ifctester not available")

        import os
        if not os.path.exists(ids_filepath):
            raise RuntimeError(f"IDS file not found: {ids_filepath}")

        ifc_file = s.get_ifc_file()
        ids = ifctester.ids.open(ids_filepath)
        ids.validate(ifc_file)

        results = []
        for spec in ids.specifications:
            results.append({
                "name": spec.name,
                "status": "pass" if spec.status else "fail",
                "applicable": spec.applicable_entities_count if hasattr(spec, 'applicable_entities_count') else None,
            })
        return {
            "ids_file": ids_filepath,
            "specifications": results,
            "passed": sum(1 for r in results if r["status"] == "pass"),
            "failed": sum(1 for r in results if r["status"] == "fail"),
        }

    def bim_purge_unused(**_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api

        # Count before
        before = len(list(ifc_file))

        # Purge unused types
        removed_types = 0
        for type_product in list(ifc_file.by_type("IfcTypeProduct")):
            if not ifc_file.get_inverse(type_product):
                try:
                    ifcopenshell.api.run("root.remove_product", ifc_file, product=type_product)
                    removed_types += 1
                except Exception:
                    pass

        after = len(list(ifc_file))
        return {
            "entities_before": before,
            "entities_after": after,
            "removed": before - after,
            "removed_types": removed_types,
        }

    s._HANDLERS.update({
        "bim_validate_ifc": bim_validate_ifc,
        "bim_run_ids_check": bim_run_ids_check,
        "bim_purge_unused": bim_purge_unused,
    })
