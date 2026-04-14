"""
BIM Classification handlers — add classification systems, classify elements.
"""

import bpy


def register(server):
    """Register BIM classification handlers."""
    s = server

    def bim_add_classification(source: str, name: str = None, edition: str = None, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        cls = ifcopenshell.api.run("classification.add_classification", ifc_file,
                                    classification=source)
        if name:
            cls.Name = name
        if edition:
            cls.Edition = edition
        return {"id": cls.id(), "source": source, "name": cls.Name}

    def bim_classify_element(object_name: str, reference: str,
                              classification: str = None, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        obj = s.get_object_or_raise(object_name)
        element = s.get_ifc_element(obj)
        # Find classification
        cls = None
        if classification:
            for c in ifc_file.by_type("IfcClassification"):
                if c.Name == classification or c.Source == classification:
                    cls = c
                    break
        else:
            classifications = ifc_file.by_type("IfcClassification")
            if classifications:
                cls = classifications[0]
        if not cls:
            raise RuntimeError("No classification system found. Use bim_add_classification first.")
        ifcopenshell.api.run("classification.add_reference", ifc_file,
                              products=[element], classification=cls,
                              identification=reference)
        return {"object": object_name, "reference": reference, "classification": cls.Name}

    def bim_list_classifications(**_):
        ifc_file = s.get_ifc_file()
        result = []
        for cls in ifc_file.by_type("IfcClassification"):
            refs = ifc_file.by_type("IfcClassificationReference")
            ref_count = sum(1 for r in refs
                          if hasattr(r, 'ReferencedSource') and r.ReferencedSource == cls)
            result.append({
                "id": cls.id(),
                "name": cls.Name,
                "source": cls.Source if hasattr(cls, 'Source') else None,
                "edition": cls.Edition if hasattr(cls, 'Edition') else None,
                "reference_count": ref_count,
            })
        return {"classifications": result}

    def bim_get_element_classifications(object_name: str, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.util.classification
        obj = s.get_object_or_raise(object_name)
        element = s.get_ifc_element(obj)
        refs = ifcopenshell.util.classification.get_references(element)
        result = []
        for ref in refs:
            info = {"identification": ref.Identification if hasattr(ref, 'Identification') else None,
                    "name": ref.Name if hasattr(ref, 'Name') else None}
            cls = ifcopenshell.util.classification.get_classification(ref)
            if cls:
                info["classification"] = cls.Name
            result.append(info)
        return {"object": object_name, "classifications": result}

    s._HANDLERS.update({
        "bim_add_classification": bim_add_classification,
        "bim_classify_element": bim_classify_element,
        "bim_list_classifications": bim_list_classifications,
        "bim_get_element_classifications": bim_get_element_classifications,
    })
