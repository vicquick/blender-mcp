"""
BIM Georeference handlers — CRS, coordinate transforms, true north.
"""


def register(server):
    """Register BIM georeference handlers."""
    s = server

    def bim_set_georeferencing(crs: str, eastings: float = 0, northings: float = 0,
                                height: float = 0, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        ifcopenshell.api.run("georeference.add_georeferencing", ifc_file)
        ifcopenshell.api.run("georeference.edit_georeferencing", ifc_file,
                              map_conversion={
                                  "Eastings": eastings,
                                  "Northings": northings,
                                  "OrthogonalHeight": height,
                              },
                              projected_crs={"Name": crs})
        return {"crs": crs, "eastings": eastings, "northings": northings, "height": height}

    def bim_set_true_north(angle: float, **_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.api
        import math
        # True north as direction ratios
        rad = math.radians(angle)
        ifcopenshell.api.run("georeference.edit_true_north", ifc_file,
                              true_north=[math.cos(rad), math.sin(rad)])
        return {"true_north_angle": angle}

    def bim_get_georeferencing(**_):
        ifc_file = s.get_ifc_file()
        import ifcopenshell.util.geolocation
        result = {"has_georeferencing": False}
        try:
            wcs = ifcopenshell.util.geolocation.get_wcs(ifc_file)
            if wcs is not None:
                result["wcs"] = [list(row) for row in wcs] if hasattr(wcs, '__iter__') else str(wcs)
            tn = ifcopenshell.util.geolocation.get_true_north(ifc_file)
            if tn is not None:
                import math
                result["true_north"] = list(tn) if hasattr(tn, '__iter__') else tn
                result["true_north_angle"] = round(math.degrees(math.atan2(tn[0], tn[1])), 2) if hasattr(tn, '__iter__') else None
            # Check for map conversion
            for mc in ifc_file.by_type("IfcMapConversion"):
                result["has_georeferencing"] = True
                result["eastings"] = mc.Eastings
                result["northings"] = mc.Northings
                result["height"] = mc.OrthogonalHeight
            # Check for projected CRS
            for crs in ifc_file.by_type("IfcProjectedCRS"):
                result["crs_name"] = crs.Name
        except Exception:
            pass
        return result

    s._HANDLERS.update({
        "bim_set_georeferencing": bim_set_georeferencing,
        "bim_set_true_north": bim_set_true_north,
        "bim_get_georeferencing": bim_get_georeferencing,
    })
